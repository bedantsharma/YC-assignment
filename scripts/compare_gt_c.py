"""Compare home C plans with the ground truth (data/gt/home_c.json, the architect's drawing)
and with Polycam (data/gt/home_c_polycam.json).

Multi-room plans must be in c_home_01's LiDAR plan frame: they are matched to rooms through
the hand-drawn boxes in data/gt/home_c_rooms.json (a video plan has its own frame: place
it with scripts/score_video_c.py instead; it is skipped here). Single-room plans (the
damage-room scans and videos) are compared with the bedroom. Room width/depth = the room
polygon's extent, sorted long/short, so the comparison does not depend on the axes.

Usage: uv run scripts/compare_gt_c.py [plan.json ...]
       default: the LiDAR plans of c_home_01, c_damage_01, c_damage_02
"""

import json
import sys
from pathlib import Path

import numpy as np

GT = json.loads(Path("data/gt/home_c.json").read_text())
POLYCAM = json.loads(Path("data/gt/home_c_polycam.json").read_text())["rooms"]
BOXES = json.loads(Path("data/gt/home_c_rooms.json").read_text())["rooms"]
DEFAULT = [f"outputs/{c}_lidar/plan.json" for c in ("c_home_01", "c_damage_01", "c_damage_02")]


def sides(width: float, depth: float) -> tuple[float, float]:
    return max(width, depth), min(width, depth)


def matched(plan: dict, report: bool = False) -> dict[str, dict]:
    """GT room key -> plan room."""
    by_label = {r["our_label"]: k for k, r in GT["rooms"].items()}
    if len(plan["rooms"]) == 1:
        return {"bedroom": plan["rooms"][0]}
    if plan["capture"]["tier"] != "lidar":
        if report:
            cap = plan["capture"]
            print(f"skipped {cap['id']} {cap['tier']}: multi-room plan not in the LiDAR frame")
        return {}
    out = {}
    for r in plan["rooms"]:
        c = np.asarray(r["polygon"]).mean(0)
        for name, (x0, y0, x1, y1) in BOXES.items():
            if x0 <= c[0] <= x1 and y0 <= c[1] <= y1 and name in by_label:
                out[by_label[name]] = r
    return out


def main() -> None:
    plans = sys.argv[1:] or DEFAULT
    for path in plans:  # report skipped plans once, up front
        matched(json.loads(Path(path).read_text()), report=True)
    print("room           | source              | long x short (m) | err long / short (cm) "
          "| area m2 (err %)  | ceiling")  # fmt: skip
    for key, g in GT["rooms"].items():
        gl, gs = sides(g["width_m"], g["depth_m"])
        gc = g.get("measured", {}).get("ceiling_height_m")
        print(f"{key:14} | ground truth        | {gl:.2f} x {gs:.2f}      |               "
              f"        | {g['area_m2']:5.1f}            | "
              f"{f'{gc:.2f} (tape)' if gc else '-'}")  # fmt: skip
        pc = POLYCAM[g["polycam"]]
        pl, ps = sides(pc["width"], pc["depth"])
        print(f"{'':14} | Polycam             | {pl:.2f} x {ps:.2f}      | "
              f"{100 * (pl - gl):+5.0f} / {100 * (ps - gs):+5.0f}         | "
              f"{pc['area_m2']:5.1f} ({100 * (pc['area_m2'] / g['area_m2'] - 1):+4.0f}%)"
              "   |")  # fmt: skip
        for path in plans:
            plan = json.loads(Path(path).read_text())
            r = matched(plan).get(key)
            if r is None:
                continue
            p = np.asarray(r["polygon"])
            rl, rs = sides(*np.ptp(p, axis=0))
            a = r["floor_area"]
            inside = "in" if a["lo"] <= g["area_m2"] <= a["hi"] else "OUT"
            c = r["ceiling_height"]
            name = f"{plan['capture']['id']} {plan['capture']['tier']}"
            print(f"{'':14} | {name:19} | {rl:.2f} x {rs:.2f}      | "
                  f"{100 * (rl - gl):+5.0f} / {100 * (rs - gs):+5.0f}         | "
                  f"{a['value']:5.1f} ({100 * (a['value'] / g['area_m2'] - 1):+4.0f}%) "
                  f"{inside:3} | "
                  f"{c['value'] if c else float('nan'):.2f}"
                  f"{f' ({100 * (c["value"] - gc):+.0f} cm)' if c and gc else ''}")  # fmt: skip


if __name__ == "__main__":
    main()
