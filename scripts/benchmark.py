"""Benchmark report: every gate of the brief at every tier, from the plans on disk.

Writes docs/benchmark_report.md (do not edit by hand). Inputs are the plans the pipeline
wrote (regenerate them first: `scripts/reproduce.sh`), home C's ground truth
(data/gt/home_c.json) and the comparison tables of scripts/gt_table.py and
scripts/calibration.py.

Usage: uv run scripts/benchmark.py
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import calibration  # noqa: E402
import gt_table as gt  # noqa: E402

OUT = Path("docs/benchmark_report.md")
TIER_GATE = {"video": 0.03, "photo": 0.08}  # brief: wall lengths +-3% (video), +-8% (photo)
CEILING_GATE_M = 0.015
REPEAT_GATE = (0.01, 0.005)  # 1 cm or 0.5%, whichever is larger
GT_DOOR = gt.GT["rooms"]["bedroom"]["measured"]["door"]


def plan(path: str) -> dict | None:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def extents(room: dict) -> tuple[float, float]:
    d = np.ptp(np.asarray(room["polygon"]), axis=0)
    return float(d.max()), float(d.min())


def tier_of(method: str) -> str | None:
    for t in ("LiDAR", "video", "photo"):
        if method.startswith(f"ours: {t}") and "known failure" not in method:
            return t.lower()
    return None


def accuracy() -> list[str]:
    by_tier: dict[str, list] = {}
    for r in gt.rows:
        t = tier_of(r["method"])
        if t is None or np.isnan(r["long"]):
            continue
        g = gt.GT["rooms"][r["room"]]
        gl, gs = max(g["width_m"], g["depth_m"]), min(g["width_m"], g["depth_m"])
        stale = "pre-fix" in r["note"]
        for got, truth in ((r["long"], gl), (r["short"], gs)):
            by_tier.setdefault(t, []).append((got - truth, (got - truth) / truth, stale))
    lines = ["| Tier | Room dimensions | Median abs. error | Within the tier's gate | Note |",
             "|---|---|---|---|---|"]  # fmt: skip
    for t, errs in by_tier.items():
        fresh = [e for e in errs if not e[2]]
        med = np.median([abs(e[0]) for e in fresh]) * 100 if fresh else np.nan
        gate = TIER_GATE.get(t)
        within = "no wall gate (LiDAR: repeatability)"
        if gate:
            ok = sum(abs(e[1]) <= gate for e in fresh)
            within = f"{ok} of {len(fresh)} within ±{100 * gate:.0f}%"
        stale = sum(e[2] for e in errs)
        note = f"{stale} dimensions from pre-fix plans excluded" if stale else ""
        lines.append(f"| {t} | {len(fresh)} | {med:.0f} cm | {within} | {note} |")
    return lines


def ceilings() -> list[str]:
    lines = ["| Tier | Room | Source | Ceiling (m) | Truth (m) | Error (cm) | ≤ 1.5 cm |",
             "|---|---|---|---|---|---|---|"]  # fmt: skip
    for r in gt.rows:
        t = tier_of(r["method"])
        c = gt.GT["rooms"][r["room"]].get("measured", {}).get("ceiling_height_m")
        if t and c and r["ceiling"] is not None and "pre-fix" not in r["note"]:
            e = 100 * (r["ceiling"] - c)
            ok = "yes" if abs(e) <= 100 * CEILING_GATE_M else "no"
            lines.append(f"| {t} | {r['room']} | {r['source']} | {r['ceiling']:.3f} | {c:.3f} | "
                         f"{e:+.1f} | {ok} |")  # fmt: skip
    return lines


def repeat_pairs() -> list[tuple[str, str, dict, dict]]:
    """Captures of the same room: (name, which, room a, room b)."""
    out = []
    a, b = plan("outputs/c_damage_01_lidar/plan.json"), plan("outputs/c_damage_02_lidar/plan.json")
    home = plan("outputs/c_home_01_lidar/plan.json")
    if a and b:
        out.append(("C bedroom", "LiDAR c_damage_01 vs c_damage_02", a["rooms"][0], b["rooms"][0]))
    if a and home:
        bed = [r for r in home["rooms"] if gt.box_room(np.asarray(r["polygon"])) == "bedroom"]
        if bed:
            out.append(("C bedroom", "LiDAR c_damage_01 vs c_home_01", a["rooms"][0], bed[0]))
    bs = [plan(f"outputs/{c}_lidar/plan.json") for c in ("42444946", "42444949", "42444950")]
    names = ("42444946", "42444949", "42444950")
    for i in range(3):
        for j in range(i + 1, 3):
            if bs[i] and bs[j]:
                out.append(("B room", f"LiDAR {names[i]} vs {names[j]}", bs[i]["rooms"][0],
                            bs[j]["rooms"][0]))  # fmt: skip
    v1 = plan("outputs/video_c/f60/c_damage_v1_video/plan.json")
    v2 = plan("outputs/video_c/f60/c_damage_v2_video/plan.json")
    if v1 and v2:
        out.append(("C bedroom", "video v1 vs v2 (60 frames)", v1["rooms"][0], v2["rooms"][0]))
    return out


def repeatability() -> list[str]:
    lines = ["| Room | Captures | Long side (m) | Short side (m) | Ceiling (m) | Δ long / short / "
             "ceiling (cm) | Pass (1 cm or 0.5%) |", "|---|---|---|---|---|---|---|"]  # fmt: skip
    for name, which, ra, rb in repeat_pairs():
        (la, sa), (lb, sb) = extents(ra), extents(rb)
        ca = ra["ceiling_height"]["value"] if ra["ceiling_height"] else None
        cb = rb["ceiling_height"]["value"] if rb["ceiling_height"] else None
        pairs = ((la, lb), (sa, sb))
        ok = all(abs(x - y) <= max(REPEAT_GATE[0], REPEAT_GATE[1] * x) for x, y in pairs)
        dc = f"{100 * abs(ca - cb):.1f}" if ca and cb else "–"
        ceil = f"{ca:.2f} / {cb:.2f}" if ca and cb else "–"
        lines.append(f"| {name} | {which} | {la:.2f} / {lb:.2f} | {sa:.2f} / {sb:.2f} | {ceil} | "
                     f"{100 * abs(la - lb):.1f} / {100 * abs(sa - sb):.1f} / {dc} | "
                     f"{'yes' if ok else 'no'} |")  # fmt: skip
    return lines


def openings() -> list[str]:
    lines = ["| Capture | Openings found | Bedroom door width (truth "
             f"{GT_DOOR['width_m']:.2f} m) | Head (truth {GT_DOOR['height_m']:.2f} m) | "
             "Windows (truth: 1) |", "|---|---|---|---|---|"]  # fmt: skip
    for c in ("c_damage_01", "c_damage_02"):
        p = plan(f"outputs/{c}_lidar/plan.json")
        if not p:
            continue
        ops = p["rooms"][0]["openings"]
        doors = [o for o in ops if o["kind"] == "door"]
        d = max(doors, key=lambda o: o["width"]["value"]) if doors else None
        w = h = "missed"
        if d:
            wv = d["width"]["value"]
            w = f"{wv:.2f} ({100 * (wv - GT_DOOR['width_m']):+.0f} cm)"
        if d and d["height"]:
            hv = d["height"]["value"]
            h = f"{hv:.2f} ({100 * (hv - GT_DOOR['height_m']):+.0f} cm)"
        n_win = sum(o["kind"] == "window" for o in ops)
        lines.append(f"| {c} | {len(ops)} | {w} | {h} | {n_win} found |")
    return lines


def timing() -> list[str]:
    lines = ["| Capture | Tier | Stages (s) | Total (s) |", "|---|---|---|---|"]
    for path in ("outputs/c_home_01_lidar/plan.json", "outputs/c_damage_01_lidar/plan.json",
                 "outputs/42444946_lidar/plan.json", "outputs/c7d28f72c6_lidar/plan.json",
                 "outputs/video_c/f60/c_damage_v1_video/plan.json",
                 "outputs/video_c/f90/c_home_v1_video/plan.json"):  # fmt: skip
        p = plan(path)
        if p:
            t = p["timing_s"]
            stages = ", ".join(f"{k} {v:.1f}" for k, v in t.items())
            lines.append(f"| {p['capture']['id']} | {p['capture']['tier']} | {stages} | "
                         f"{sum(t.values()):.1f} |")  # fmt: skip
    kag = Path("outputs/kaggle_video_runs/summary.json")
    if kag.exists():
        for r in json.loads(kag.read_text()):
            lines.append(f"| {r['video']} ({r['frames']} frames) | video, live on a Kaggle T4 | "
                         f"model + geometry | {r['seconds']:.0f} |")  # fmt: skip
    return lines


def main() -> None:
    gt.collect()
    per_tier, misses = calibration.coverage()
    text = "\n".join([
        "# Benchmark report", "",
        "Generated by `uv run scripts/benchmark.py` (do not edit by hand) from the plans in "
        "`outputs/` (`scripts/reproduce.sh` regenerates them) and home C's ground truth "
        "(`data/gt/home_c.json`: the architect's drawing for room sizes, the friend's tape for "
        "ceilings, doors, windows). Datasets: A (Cozmo's apartment, 3 Stray Scanner "
        "captures, no ground truth), B (ARKitScenes 421337, 3 scans, laser measurements "
        "pending), C (a friend's home: LiDAR whole-home + 2 room scans, Camera-app videos, "
        "photo stills, Polycam, ground truth). Every room, method and run: "
        "[gt_comparison.md](gt_comparison.md).", "",
        "## Accuracy vs ground truth, per tier (home C)", "", *accuracy(), "",
        "Video and photo rows in-sample for the damage room: the video scale bias was "
        "re-measured on it ([fix_declaration.md](fix_declaration.md) §6).", "",
        "## Ceiling height (gate: ≤ 1.5 cm per room)", "", *ceilings(), "",
        "Bias or noise: the LiDAR ceilings of the same room agree within 1 cm across three "
        "scans and sit within 1-2 cm of the tape, so the remaining LiDAR error is noise at "
        "the cm level, not a bias; the video and photo tiers carry a model bias (corrected "
        "by `intervals.SCALE_BIAS`) and room-to-room noise of 5-15 cm.", "",
        "## Repeatability (gate: two captures agree within 1 cm or 0.5% per wall)", "",
        *repeatability(), "",
        "Sides are the room's extent; B's scans differ in coverage before any snapping "
        "(fix map 02b).", "",
        "## Openings (gate: widths ≤ 2 cm on ≥ 85% of openings)", "", *openings(), "",
        "Not met: the door is found but narrow; windows are not detected "
        "([openings.md](openings.md)).", "",
        "## Drift", "",
        "Method and on/off ablation: [drift_ablation.md](drift_ablation.md). Correction is "
        "built (chunked 2D ICP on walls) and **off by default**: it made A `c00a170fe1` and "
        "the `c_home_01` kitchen worse. The wall estimate itself absorbs drift since fix 09 "
        "(centre of the drift smear).", "",
        "## Calibration of the 90% intervals (home C)", "", calibration.table(per_tier), "",
        "Areas are checked against the drawing's nominal rectangles (the bedroom's closet and "
        "the drawing room's niche are not subtracted), so area misses overstate the problem. "
        "Misses on sides and ceilings:", "", "```", *(misses or ["none"]), "```", "",
        gt.head_to_head(), "",
        "## Timing (seconds)", "",
        "LiDAR rows: live on this laptop (M4, 16 GB). Video rows on this laptop replay the "
        "model output from the cache (the model runs on Kaggle, user's rule); the Kaggle rows "
        "are the live model + geometry time on one T4.", "", *timing(), "",
    ])  # fmt: skip
    OUT.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
