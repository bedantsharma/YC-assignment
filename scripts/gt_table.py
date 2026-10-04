"""Every method we have tested on home C vs the ground truth, in one table.

Ground truth: data/gt/home_c.json (architect's drawing for room sizes; ceilings 11 ft,
measured in the bedroom and the dining & living room only). Rows:

- Polycam (data/gt/home_c_polycam.json)
- our LiDAR tier (outputs/<capture>_lidar)
- our video tier (Pi3X + our scale correction): the LiDAR recording's own video and the
  Camera-app videos (multi-room video plans are placed onto the LiDAR plan first)
- our photo tier: stills taken from the videos (no real photo folders yet)
- third-party models as they come (no correction of ours): Pi3X, MapAnything (video
  bake-off, 30 frames), Pi3X, MapAnything, Depth Anything 3 (photo bake-off), SpatialLM
  (on our LiDAR clouds)

Room size = the room polygon's extent (long x short). Errors are signed: + = too big.
Writes docs/gt_comparison.md and prints it.

Usage: uv run scripts/gt_table.py
"""

import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from score_spatiallm import parse, room_dims  # noqa: E402
from score_video_c import place  # noqa: E402

from floorplan.lidar import build_plan  # noqa: E402
from floorplan.photos import main_room  # noqa: E402
from floorplan.plan2d import ENCLOSED_FRACTION_SPARSE, Sightlines  # noqa: E402
from floorplan.video import estimate_up, z_up  # noqa: E402

GT = json.loads(Path("data/gt/home_c.json").read_text())
POLY = json.loads(Path("data/gt/home_c_polycam.json").read_text())["rooms"]
BOXES = json.loads(Path("data/gt/home_c_rooms.json").read_text())["rooms"]
BY_LABEL = {r["our_label"]: k for k, r in GT["rooms"].items()}
LIDAR_HOME = json.loads(Path("outputs/c_home_01_lidar/plan.json").read_text())
OUT = Path("docs/gt_comparison.md")

rows: list[dict] = []


def add(room: str, method: str, group: str, source: str, long_: float, short: float,
        area: float | None = None, ceiling: float | None = None,
        note: str = "") -> None:  # fmt: skip
    rows.append(dict(room=room, method=method, group=group, source=source, long=long_,
                     short=short, area=area, ceiling=ceiling, note=note))  # fmt: skip


def extent(poly) -> tuple[float, float]:
    d = np.ptp(np.asarray(poly), axis=0)
    return float(d.max()), float(d.min())


def box_room(poly: np.ndarray) -> str | None:
    c = poly.mean(0)
    for name, (x0, y0, x1, y1) in BOXES.items():
        if x0 <= c[0] <= x1 and y0 <= c[1] <= y1:
            return BY_LABEL.get(name)
    return None


def plan_rows(path: str, method: str, group: str, source: str, how: str, note: str = "") -> None:
    p = Path(path)
    if not p.exists():
        return
    plan = json.loads(p.read_text())
    rooms = plan["rooms"]
    if how == "single":  # one room: the damage room
        pairs = [("bedroom", r) for r in rooms[:1]]
    elif how == "folders":  # photo tier: rooms named after their folder
        pairs = [(BY_LABEL.get(r["label"]), r) for r in rooms]
    elif how == "lidar":
        pairs = [(box_room(np.asarray(r["polygon"])), r) for r in rooms]
    else:  # "place": own frame, moved onto the LiDAR plan first
        lid = [np.asarray(r["polygon"]) for r in LIDAR_HOME["rooms"]]
        placed, _ = place([np.asarray(r["polygon"]) for r in rooms], lid)
        pairs = [(box_room(q), r) for q, r in zip(placed, rooms, strict=True)]
    seen = set()
    for key, r in pairs:
        if key is None or key in seen:
            continue
        seen.add(key)
        c = r["ceiling_height"]
        add(key, method, group, source, *extent(r["polygon"]), r["floor_area"]["value"],
            c["value"] if c else None, note)  # fmt: skip
    for key in GT["rooms"]:
        if how in ("lidar", "place", "folders") and key not in seen:
            add(key, method, group, source, np.nan, np.nan, note="room not found")


def raw_model_rows(npz: Path, method: str, group: str, source: str) -> None:
    """Third-party model output as is: its points through our plan builder, main room."""
    d = np.load(npz)
    pts, poses = d["points"].astype(float), d["poses"]
    up = estimate_up(pts, poses)
    p, cams = z_up(pts, up), z_up(poses[:, :3, 3], up)
    sight = Sightlines(cams[:, :2], p, d["view"]) if "view" in d.files else None
    plan = build_plan(p, ENCLOSED_FRACTION_SPARSE, sight) if sight else build_plan(p)
    if not plan.rooms:
        add("bedroom", method, group, source, np.nan, np.nan, note="no room found")
        return
    r = plan.rooms[main_room(plan.rooms, plan.rotation_deg, cams[:, :2])]
    c = r.ceiling_height
    add("bedroom", method, group, source, *extent(r.polygon), r.floor_area.value,
        c.value if c else None)  # fmt: skip


def collect() -> None:
    for key, g in GT["rooms"].items():
        pc = POLY[g["polycam"]]
        w, d = pc["width"], pc["depth"]
        add(key, "Polycam (RoomPlan)", "competitor", "Polycam scan", max(w, d), min(w, d),
            pc["area_m2"])  # fmt: skip

    lid = "ours: LiDAR tier"
    plan_rows("outputs/c_home_01_lidar/plan.json", lid, "ours", "whole-home scan", "lidar")
    for c in ("c_damage_01", "c_damage_02"):
        plan_rows(f"outputs/{c}_lidar/plan.json", lid, "ours", f"{c} scan", "single")

    vid = "ours: video tier (Pi3X)"
    plan_rows("outputs/c_home_01_video/plan.json", vid, "ours",
              "LiDAR recording's video, 90 fr", "place")  # fmt: skip
    for v in ("c_damage_v1", "c_damage_v2"):
        for n in (30, 60):
            plan_rows(f"outputs/video_c/f{n}/{v}_video/plan.json", vid, "ours",
                      f"Camera-app {v[-2:]}, {n} fr", "single")  # fmt: skip
    plan_rows("outputs/video_c/f90/c_home_v1_video/plan.json",
              "ours: video tier, 5-min house clip (known failure)", "ours",
              "Camera-app house, 90 fr", "place")  # fmt: skip

    pho = "ours: photo tier (Pi3X)"
    for cap, how in (("c_home_01", "folders"), ("c_damage_01", "single"),
                     ("c_damage_02", "single")):  # fmt: skip
        for k in ("k8", "k8p"):
            plan_rows(f"outputs/photo_runs/{cap}_{k}/{k}_photo/plan.json", pho, "ours",
                      f"{cap} stills {k}", how)  # fmt: skip

    names = {"pi3x": "Pi3X", "mapanything": "MapAnything", "da3_nested": "Depth Anything 3"}
    for f in sorted(Path("outputs/bakeoff").glob("c_damage_*.npz")):
        cap, model, n = f.stem.split("__")
        raw_model_rows(f, f"{names[model]} (raw, video)", "third-party",
                       f"{cap} rgb, {n} fr")  # fmt: skip
    for f in sorted(Path("outputs/photo_bakeoff").glob("c_damage_*.npz")):
        cap, model, k = f.stem.split("__")
        raw_model_rows(f, f"{names[model]} (raw, photos)", "third-party",
                       f"{cap} stills {k}")  # fmt: skip

    for f in sorted(Path("outputs/kaggle_lidar_bakeoff").glob("c_damage_*.txt")):
        cap, model, seed = f.stem.split("__")
        dims = room_dims(parse(f)["wall"])
        m = re.sub(r"SpatialLM1\.1-", "", model)
        if dims is None:
            add("bedroom", f"SpatialLM {m}", "third-party", f"{cap} LiDAR, {seed}", np.nan,
                np.nan, note="broken outline")  # fmt: skip
            continue
        x, y, h = dims
        add("bedroom", f"SpatialLM {m}", "third-party", f"{cap} LiDAR, {seed}", max(x, y),
            min(x, y), x * y, h, "area = rectangle")  # fmt: skip


def fmt(v, spec=".2f", none="–") -> str:
    return none if v is None or (isinstance(v, float) and np.isnan(v)) else format(v, spec)


def table() -> str:
    lines = ["# Home C: every method vs the ground truth", "",
             "Generated by `uv run scripts/gt_table.py` (do not edit by hand). Ground truth: "
             "`data/gt/home_c.json` (architect's drawing; ceilings 11 ft = 3.35 m, measured in "
             "the bedroom and the dining & living room). Signed errors: + = too big. Photo "
             "tier rows use stills taken from the videos (real photo folders not run yet). "
             "Third-party rows are the model's own output through our plan builder, without "
             "our scale correction.", ""]  # fmt: skip
    errs: dict[str, list] = {}
    for key, g in GT["rooms"].items():
        gl, gs = max(g["width_m"], g["depth_m"]), min(g["width_m"], g["depth_m"])
        gc = g.get("measured", {}).get("ceiling_height_m")
        lines += [f"## {key.replace('_', ' ').title()}: {gl:.2f} x {gs:.2f} m, "
                  f"{g['area_m2']:.1f} m²" + (f", ceiling {gc:.2f} m" if gc else ""), "",
                  "| Method | Source | Long x short (m) | Error long / short (cm) | "
                  "Area m² (error) | Ceiling (error) | Note |",
                  "|---|---|---|---|---|---|---|"]  # fmt: skip
        for r in [r for r in rows if r["room"] == key]:
            el, es = 100 * (r["long"] - gl), 100 * (r["short"] - gs)
            ea = None if r["area"] is None else 100 * (r["area"] / g["area_m2"] - 1)
            ec = None if r["ceiling"] is None or gc is None else 100 * (r["ceiling"] - gc)
            e = errs.setdefault(r["method"], {"dims": [], "area": [], "ceil": [], "n": 0,
                                              "fail": 0, "group": r["group"]})  # fmt: skip
            e["n"] += 1
            if np.isnan(r["long"]):
                e["fail"] += 1
            else:
                e["dims"] += [el, es]
                if ea is not None:
                    e["area"].append(ea)
                if ec is not None:
                    e["ceil"].append(ec)
            dims = "–" if np.isnan(r["long"]) else f"{r['long']:.2f} x {r['short']:.2f}"
            derr = "–" if np.isnan(r["long"]) else f"{el:+.0f} / {es:+.0f}"
            area = "–" if r["area"] is None else f"{r['area']:.1f} ({ea:+.0f}%)"
            ceil = fmt(r["ceiling"]) + (f" ({ec:+.0f} cm)" if ec is not None else "")
            lines.append(f"| {r['method']} | {r['source']} | {dims} | {derr} | {area} | "
                         f"{ceil} | {r['note']} |")  # fmt: skip
        lines.append("")
    lines += ["## Summary per method (all rooms and runs above)", "",
              "| Method | Group | Rooms measured | Failed | Mean abs. wall error (cm) | "
              "Median abs. wall error (cm) | Worst wall error (cm) | Mean area error | "
              "Mean abs. ceiling error (cm) |",
              "|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    order = {"competitor": 0, "ours": 1, "third-party": 2}
    for m, e in sorted(errs.items(), key=lambda kv: (order[kv[1]["group"]], kv[0])):
        d = np.abs(e["dims"])
        lines.append(
            f"| {m} | {e['group']} | {e['n']} | {e['fail']} | "
            f"{fmt(d.mean() if len(d) else None, '.0f')} | "
            f"{fmt(np.median(d) if len(d) else None, '.0f')} | "
            f"{fmt(e['dims'][int(np.argmax(d))] if len(d) else None, '+.0f')} | "
            f"{fmt(np.mean(e['area']) if e['area'] else None, '+.0f')}% | "
            f"{fmt(np.mean(np.abs(e['ceil'])) if e['ceil'] else None, '.0f')} |"
        )
    return "\n".join(lines) + "\n"


def head_to_head() -> str:
    """H1/H3: our whole-home LiDAR scan vs Polycam, dimension by dimension. Closer to the
    truth wins; a tie is equal error at Polycam's precision (1 cm)."""
    ours = {r["room"]: r for r in rows if r["source"] == "whole-home scan"}
    poly = {r["room"]: r for r in rows if r["group"] == "competitor"}
    lines = ["## Head-to-head: our LiDAR tier (whole-home scan) vs Polycam", "",
             "Each room dimension: whose error vs the ground truth is smaller. Tie = equal "
             "at Polycam's precision (1 cm). Brief target: beat or tie on >= 70%.", "",
             "| Room | Dimension | Truth (m) | Ours (m) | Polycam (m) | Our error (cm) | "
             "Polycam error (cm) | Result |", "|---|---|---|---|---|---|---|---|"]  # fmt: skip
    score = []
    for key, g in GT["rooms"].items():
        if key not in ours or np.isnan(ours[key]["long"]):
            continue
        truth = {"long": max(g["width_m"], g["depth_m"]), "short": min(g["width_m"], g["depth_m"])}
        for dim, t in truth.items():
            o, p = round(ours[key][dim], 2), poly[key][dim]
            eo, ep = round(100 * abs(o - t)), round(100 * abs(p - t))
            res = "win" if eo < ep else "tie" if eo == ep else "loss"
            score.append(res)
            lines.append(f"| {key.replace('_', ' ')} | {dim} | {t:.2f} | {o:.2f} | {p:.2f} | "
                         f"{eo} | {ep} | {res} |")  # fmt: skip
    ok = sum(r != "loss" for r in score)
    lines += ["", f"**Beat or tie: {ok} of {len(score)} ({100 * ok / len(score):.0f}%)** "
              f"({score.count('win')} wins, {score.count('tie')} ties).", ""]  # fmt: skip
    return "\n".join(lines)


def main() -> None:
    collect()
    text = table() + "\n" + head_to_head()
    OUT.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
