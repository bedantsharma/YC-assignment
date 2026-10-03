"""Score the photo-tier bake-off against the LiDAR and ARKit of the same recordings.

Input: outputs/photo_bakeoff/<capture>__<model>__k<K>.npz from the Kaggle job
(kaggle/photo_bakeoff): voxel-thinned points, camera poses and the photo names in input
order. Each photo's time comes from data/home_c/photos_sim/<capture>/k8/manifest.json.

Per run: camera error and scale vs ARKit after a similarity fit (evaluation only); rooms
found; then per LiDAR room the paired photo room (floor overlap, cloud moved into the LiDAR
frame by the fit's rotation only, so lengths keep the model's own scale): sqrt(area) and
ceiling ratios, raw (before the scale correction, which was fitted on video).

Usage: uv run scripts/score_photos.py [--dir outputs/photo_bakeoff]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from video_scale import overlap, world  # noqa: E402

from floorplan.capture import load_lidar  # noqa: E402
from floorplan.chunks import umeyama  # noqa: E402
from floorplan.lidar import build_plan  # noqa: E402
from floorplan.pipeline import run  # noqa: E402
from floorplan.plan2d import ENCLOSED_FRACTION_SPARSE  # noqa: E402

FPS = 60
SIM = Path("data/home_c/photos_sim")


def photo_times(cap: str, names) -> np.ndarray:
    man = json.loads((SIM / cap / "k8" / "manifest.json").read_text())
    out = []
    for n in names:
        room, f = str(n).split("/")
        out.append(man["rooms"][room]["times"][int(Path(f).stem)])
    return np.array(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=Path("outputs/photo_bakeoff"))
    args = ap.parse_args()
    lidar, rows, per_room = {}, [], []
    for f in sorted(args.dir.glob("*.npz")):
        cap, model, k = f.stem.split("__")
        src = Path("data/home_c/lidar") / cap
        if cap not in lidar:
            lidar[cap] = run(src, "lidar")
        d = np.load(f)
        pts, poses = d["points"].astype(float), d["poses"]
        ref = load_lidar(src).poses
        idx = np.clip((photo_times(cap, d["names"]) * FPS).round().astype(int), 0, len(ref) - 1)
        c, c_ref = poses[:, :3, 3], ref[idx, :3, 3]
        s, r, t = umeyama(c, c_ref)
        ate = np.linalg.norm(s * c @ r.T + t - c_ref, axis=1)
        tt = c_ref.mean(0) - r @ c.mean(0)
        plan = build_plan(pts @ r.T + tt, ENCLOSED_FRACTION_SPARSE)  # as the photo tier
        ref_plan = lidar[cap]
        video = [(vr, world(vr, plan.rotation_deg)) for vr in plan.rooms]
        side, ceil = [], []
        for lr in ref_plan.rooms:
            lp = world(lr, ref_plan.plan_rotation_deg)
            if not video:
                break
            best, bp = max(video, key=lambda v, lp=lp: overlap(v[1], lp))
            if overlap(bp, lp) < 0.3 * min(best.floor_area.value, lr.floor_area.value):
                per_room.append((cap, model, k, lr.id, None, None))
                continue
            a = (best.floor_area.value / lr.floor_area.value) ** 0.5
            h = best.ceiling_height.value / lr.ceiling_height.value
            side.append(a)
            ceil.append(h)
            per_room.append((cap, model, k, lr.id, a, h))
        rows.append(
            (
                cap,
                model,
                k,
                len(poses),
                s,
                float(np.median(ate)),
                len(plan.rooms),
                len(ref_plan.rooms),
                sum(x.floor_area.value for x in plan.rooms),
                sum(x.floor_area.value for x in ref_plan.rooms),
                side,
                ceil,
            )
        )

    cols = ["capture", "model", "photos", "scale vs ARKit", "camera error", "rooms (LiDAR)"]
    cols += ["area m2 (LiDAR)", "sqrt(area) ratio", "ceiling ratio"]
    print("| " + " | ".join(cols) + " |")
    print("|---|---|---|---|---|---|---|---|---|")
    for cap, model, k, n, s, ate, nr, lnr, area, larea, side, ceil in rows:
        sa = f"{np.mean(side):.3f}" if side else "-"
        ce = f"{np.mean(ceil):.3f}" if ceil else "-"
        print(
            f"| {cap} | {model} | {n} ({k}) | {s:.3f} | {100 * ate:.0f} cm | {nr} ({lnr}) | "
            f"{area:.1f} ({larea:.1f}) | {sa} | {ce} |"
        )
    print("\nper room (sqrt(area), ceiling; None = not found):")
    for row in per_room:
        print("  ", *[f"{x:.3f}" if isinstance(x, float) else x for x in row])


if __name__ == "__main__":
    main()
