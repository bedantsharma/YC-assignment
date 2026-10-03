"""Scale bias of the video tier, per model, against the LiDAR of the same recording.

For single-room recordings (C's damage room), video / LiDAR: the longest wall, the square
root of the floor area (a linear measure) and the ceiling height. Not the bounding box: a
spurious spur in one plan stretches it (Pi3X on c_damage_02: 1.16). Inputs are video
reconstructions as bake-off .npz files (outputs/bakeoff/<capture>__<model>__<n>.npz) and/or
video-tier plan.json files (outputs/<dir>/<capture>_video/plan.json). LiDAR is the
reference here because C has no ground truth yet; it is used for evaluation only.

Usage: uv run scripts/video_scale.py [npz or plan.json ...]
"""

import json
import sys
from pathlib import Path

import numpy as np

from floorplan.lidar import build_plan
from floorplan.pipeline import run
from floorplan.video import estimate_up, z_up


def longest(room) -> float:
    return max(w["length"]["value"] for w in room["walls"])


def side(room) -> float:
    return room["floor_area"]["value"] ** 0.5


def largest(rooms):
    return max(rooms, key=lambda r: r["floor_area"]["value"])


def as_dict(result) -> dict:
    return json.loads(json.dumps(result, default=lambda o: o.__dict__))


def video_room(path: Path) -> tuple[str, str, dict]:
    if path.suffix == ".npz":
        cap, model, n = path.stem.split("__")
        d = np.load(path)
        pts = d["points"].astype(float)
        plan = build_plan(z_up(pts, estimate_up(pts, d["poses"])))
        rooms = [as_dict(r) for r in plan.rooms]
        return cap, f"{model} ({n}, T4)", largest(rooms)
    d = json.loads(path.read_text())
    model = next((w.split(",")[0] for w in d["warnings"] if w.startswith("reconstruction:")), "?")
    model = model.removeprefix("reconstruction: ").split(" (")[0]
    cap = d["capture"]["id"]
    return cap, f"{model} ({path.parent.parent.name})", largest(d["rooms"])


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]] or sorted(Path("outputs/bakeoff").glob("c_damage*.npz"))
    lidar = {}
    rows = []
    for path in paths:
        cap, label, room = video_room(path)
        if cap not in lidar:
            res = run(Path("data/home_c/lidar") / cap, "lidar")
            lidar[cap] = largest([as_dict(r) for r in res.rooms])
        ref = lidar[cap]
        vl, ll, vs, ls = longest(room), longest(ref), side(room), side(ref)
        vc = room["ceiling_height"]["value"] if room.get("ceiling_height") else float("nan")
        lc = ref["ceiling_height"]["value"]
        rows.append((cap, label, vl / ll, vs / ls, vc / lc))
    print("| capture | model | longest wall | sqrt(area) | ceiling |")
    print("|---|---|---|---|---|")
    for cap, label, a, b, c in rows:
        print(f"| {cap} | {label} | {a:.3f} | {b:.3f} | {c:.3f} |")
    by_model = {}
    for _, label, a, b, c in rows:
        by_model.setdefault(label.split(" (")[0], []).append((a, b, c))
    print("\nper model: mean horizontal ratio (spread), mean vertical ratio (spread)")
    for m, v in by_model.items():
        h = np.array([x[:2] for x in v]).ravel()
        c = np.array([x[2] for x in v])
        print(
            f"  {m}: {h.mean():.3f} ({h.min():.3f}-{h.max():.3f}), "
            f"{np.nanmean(c):.3f} ({np.nanmin(c):.3f}-{np.nanmax(c):.3f}), n={len(v)}"
        )


if __name__ == "__main__":
    main()
