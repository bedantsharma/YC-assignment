"""Scale bias of the video tier, per model and per room, against the LiDAR of the same recording.

Per room, video / LiDAR: the longest wall, the square root of the floor area (a linear
measure) and the ceiling height. Not the bounding box: a spurious spur in one plan
stretches it (Pi3X on c_damage_02: 1.16).

Matching rooms (evaluation only): the video cloud is levelled as the tier does it (wall
normals), then turned and shifted in the floor plane onto ARKit's camera positions. No
scale is applied, so every length keeps the model's own metric scale. Each LiDAR room is
then paired with the video room whose floor overlaps it most. C has no ground truth yet,
so LiDAR is the reference.

Inputs: video reconstructions as .npz (outputs/bakeoff/ or outputs/video_eval/,
<capture>__<model>__<n>.npz).

Usage: uv run scripts/video_scale.py [npz ...]
"""

import sys
from pathlib import Path

import numpy as np
from matplotlib.path import Path as Poly

from floorplan.capture import load_lidar
from floorplan.lidar import build_plan
from floorplan.pipeline import run
from floorplan.plan2d import Grid
from floorplan.video import duration, estimate_up, z_up

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


def place(pts: np.ndarray, poses: np.ndarray, c_ref: np.ndarray) -> np.ndarray:
    """Level the cloud the way the tier does (vertical from wall normals), then turn and
    shift it in the floor plane onto the reference cameras (ARKit, evaluation only). No
    scale and no tilt from the reference: a 3D fit to a few cameras at one height can tilt
    the floor (8 photos of c_damage_02: no room found after a 3D fit, one room without)."""
    up = estimate_up(pts, poses)
    p, c = z_up(pts, up), z_up(poses[:, :3, 3], up)
    a, b = c[:, :2] - c[:, :2].mean(0), c_ref[:, :2] - c_ref[:, :2].mean(0)
    u, _, vt = np.linalg.svd(b.T @ a)
    r = u @ np.diag([1.0, np.sign(np.linalg.det(u @ vt))]) @ vt
    out = p.copy()
    out[:, :2] = (p[:, :2] - c[:, :2].mean(0)) @ r.T + c_ref[:, :2].mean(0)
    return out


def aligned_plan(path: Path, src: Path):
    d = np.load(path)
    pts, poses = d["points"].astype(float), d["poses"]
    n = len(poses)
    times = np.linspace(0.5, duration(src / "rgb.mp4") - 0.5, n)
    ref = load_lidar(src).poses
    idx = np.clip((times * FPS).round().astype(int), 0, len(ref) - 1)
    return build_plan(place(pts, poses, ref[idx, :3, 3]))


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
