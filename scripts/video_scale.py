"""Scale bias of the video tier, per model and per room, against the LiDAR of the same recording.

Per room, video / LiDAR: the longest wall, the square root of the floor area (a linear
measure) and the ceiling height. Not the bounding box: a spurious spur in one plan
stretches it (Pi3X on c_damage_02: 1.16).

Matching rooms (evaluation only): the video cloud is moved into the LiDAR frame by the
rotation of a similarity fit of its camera centres to ARKit's, and a translation that puts
the camera centroids together. The fit's scale is NOT applied, so every length keeps the
model's own metric scale. Each LiDAR room is then paired with the video room whose floor
overlaps it most. C has no ground truth yet, so LiDAR is the reference.

Inputs: video reconstructions as .npz (outputs/bakeoff/ or outputs/video_eval/,
<capture>__<model>__<n>.npz).

Usage: uv run scripts/video_scale.py [npz ...]
"""

import sys
from pathlib import Path

import numpy as np
from matplotlib.path import Path as Poly

from floorplan.capture import load_lidar
from floorplan.chunks import umeyama
from floorplan.lidar import build_plan
from floorplan.pipeline import run
from floorplan.plan2d import Grid
from floorplan.video import duration

FPS = 60  # Stray rgb.mp4: frame index = time * 60 = pose index
CELL = 0.05


def longest(room) -> float:
    return max(w.length.value for w in room.walls)


def world(room, angle_deg: float) -> np.ndarray:
    """Room polygon in world xy. Plans are axis-aligned to the dominant wall direction,
    which is only defined up to 90 deg (c_damage_01: 89.65 on the T4 run, 0.05 on the M4)."""
    return Grid(angle_deg, np.zeros(2), 1.0, (1, 1)).to_world(np.asarray(room.polygon))


def overlap(pa: np.ndarray, pb: np.ndarray) -> float:
    """Shared floor area of two world polygons (m2), by sampling a grid over them."""
    lo, hi = np.minimum(pa.min(0), pb.min(0)), np.maximum(pa.max(0), pb.max(0))
    xs, ys = np.arange(lo[0], hi[0], CELL), np.arange(lo[1], hi[1], CELL)
    g = np.stack(np.meshgrid(xs, ys), -1).reshape(-1, 2)
    return float((Poly(pa).contains_points(g) & Poly(pb).contains_points(g)).sum() * CELL**2)


def aligned_plan(path: Path, src: Path):
    d = np.load(path)
    pts, poses = d["points"].astype(float), d["poses"]
    n = len(poses)
    times = np.linspace(0.5, duration(src / "rgb.mp4") - 0.5, n)
    ref = load_lidar(src).poses
    idx = np.clip((times * FPS).round().astype(int), 0, len(ref) - 1)
    c, c_ref = poses[:, :3, 3], ref[idx, :3, 3]
    _, r, _ = umeyama(c, c_ref)
    t = c_ref.mean(0) - r @ c.mean(0)  # no scale: lengths stay the model's own
    return build_plan(pts @ r.T + t)


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]] or sorted(Path("outputs/bakeoff").glob("*.npz"))
    lidar, rows = {}, []
    for path in paths:
        cap, model, n = path.stem.split("__")
        src = Path("data/home_c/lidar") / cap
        if cap not in lidar:
            lidar[cap] = run(src, "lidar")
        plan = aligned_plan(path, src)
        ref = lidar[cap]
        video = [(vr, world(vr, plan.rotation_deg)) for vr in plan.rooms]
        for lr in ref.rooms:
            if not video:
                break
            lp = world(lr, ref.plan_rotation_deg)
            best, bp = max(video, key=lambda v, lp=lp: overlap(v[1], lp))
            shared = overlap(bp, lp)
            if shared < 0.3 * min(best.floor_area.value, lr.floor_area.value):
                rows.append((cap, f"{model} {n}", lr, None, shared))
                continue
            rows.append((cap, f"{model} {n}", lr, best, shared))

    print("| capture | model | LiDAR room | m2 | video m2 | longest wall | sqrt(area) | ceiling |")
    print("|---|---|---|---|---|---|---|---|")
    stats = {}
    for cap, label, lr, vr, _ in rows:
        if vr is None:
            print(f"| {cap} | {label} | {lr.id} | {lr.floor_area.value:.1f} | not found | | | |")
            continue
        a = longest(vr) / longest(lr)
        b = (vr.floor_area.value / lr.floor_area.value) ** 0.5
        c = vr.ceiling_height.value / lr.ceiling_height.value
        stats.setdefault(label.split()[0], []).append((a, b, c))
        print(
            f"| {cap} | {label} | {lr.id} | {lr.floor_area.value:.1f} | "
            f"{vr.floor_area.value:.1f} | {a:.3f} | {b:.3f} | {c:.3f} |"
        )
    print("\nper model: horizontal ratio mean (range), vertical ratio mean (range), rooms")
    for m, v in stats.items():
        h, c = np.array([x[:2] for x in v]).ravel(), np.array([x[2] for x in v])
        print(
            f"  {m}: {h.mean():.3f} ({h.min():.3f}-{h.max():.3f}), "
            f"{c.mean():.3f} ({c.min():.3f}-{c.max():.3f}), n={len(v)}"
        )


if __name__ == "__main__":
    main()
