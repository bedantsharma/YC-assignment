"""Score SpatialLM layouts (Kaggle bake-off round 3) on the damage room against our LiDAR
plan and Polycam: room width and depth from the walls longer than 2 m (wall lines are
rotated to the dominant wall direction), wall height, doors and windows.

Usage: uv run scripts/score_spatiallm.py [outputs/kaggle_lidar_bakeoff]
"""

import json
import re
import sys
from pathlib import Path

import numpy as np

MIN_WALL_M = 2.0


def parse(path: Path) -> dict:
    out = {"wall": [], "door": [], "window": []}
    for line in path.read_text().splitlines():
        m = re.match(r"(wall|door|window)_\d+=\w+\((.*)\)", line)
        if m:
            out[m[1]].append(m[2].split(","))
    return out


def room_dims(walls: list) -> tuple[float, float, float] | None:
    """Width, depth (between the outermost long walls) and wall height; None when the
    outline has fewer than two long walls in a direction (broken layout)."""
    w = np.array([[float(v) for v in x] for x in walls])
    a, b = w[:, [0, 1]], w[:, [3, 4]]
    d = b - a
    length = np.hypot(d[:, 0], d[:, 1])
    ang = np.arctan2(d[:, 1], d[:, 0]) % (np.pi / 2)
    theta = np.median(ang[length > MIN_WALL_M])
    r = np.array([[np.cos(-theta), -np.sin(-theta)], [np.sin(-theta), np.cos(-theta)]])
    a, b = a @ r.T, b @ r.T
    long = length > MIN_WALL_M
    along_x = np.abs(b[:, 0] - a[:, 0]) > np.abs(b[:, 1] - a[:, 1])
    ys = a[long & along_x, 1]
    xs = a[long & ~along_x, 0]
    if len(xs) < 2 or len(ys) < 2:
        return None
    return float(np.ptp(xs)), float(np.ptp(ys)), float(np.median(w[:, 6]))


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "outputs/kaggle_lidar_bakeoff")
    poly = json.loads(Path("data/gt/home_c_polycam.json").read_text())["rooms"]["bedroom_2"]
    print(f"Polycam bedroom 2 (damage room): {poly['width']} x {poly['depth']} m")
    for cap in ("c_damage_01", "c_damage_02"):
        plan = json.loads(Path(f"outputs/{cap}_lidar/plan.json").read_text())["rooms"][0]
        p = np.asarray(plan["polygon"])
        ours = sorted(np.ptp(p, axis=0).round(2).tolist(), reverse=True)
        print(f"{cap}: our LiDAR {ours[0]:.2f} x {ours[1]:.2f}, "
              f"ceiling {plan['ceiling_height']['value']:.2f}")  # fmt: skip
        for f in sorted(root.glob(f"{cap}__*.txt")):
            lay = parse(f)
            dims = room_dims(lay["wall"])
            tag = f.stem.split("__", 1)[1]
            if dims is None:
                print(f"  {tag:28} broken outline: fewer than 2 walls > {MIN_WALL_M} m "
                      f"in one direction ({len(lay['wall'])} walls)")  # fmt: skip
                continue
            x, y, h = dims
            long_, short = max(x, y), min(x, y)
            print(f"  {tag:28} {long_:.2f} x {short:.2f} (vs ours "
                  f"{long_ - ours[0]:+.2f} / {short - ours[1]:+.2f}, vs Polycam "
                  f"{long_ - poly['width']:+.2f} / {short - poly['depth']:+.2f}), "
                  f"wall height {h:.2f}, {len(lay['door'])} doors, "
                  f"{len(lay['window'])} windows")  # fmt: skip


if __name__ == "__main__":
    main()
