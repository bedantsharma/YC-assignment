"""Score the photo-tier bake-off against the LiDAR and ARKit of the same recordings.

Input: outputs/photo_bakeoff/<capture>__<model>__k<K>.npz from the Kaggle job
(kaggle/photo_bakeoff): voxel-thinned points, camera poses and the photo names in input
order. Each photo's time comes from data/home_c/photos_sim/<capture>/k8/manifest.json.

Per run: camera error and scale vs ARKit after a similarity fit (evaluation only); rooms
found; then per LiDAR room the paired photo room (floor overlap, cloud moved into the LiDAR
frame by the fit's rotation only, so lengths keep the model's own scale): sqrt(area) and
ceiling ratios, raw (before the scale correction, which was fitted on video). Rooms are paired
after levelling the cloud as the tier does and turning it onto ARKit in the floor plane.

Usage: uv run scripts/score_photos.py [--dir outputs/photo_bakeoff]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from video_scale import overlap, place, world  # noqa: E402

from floorplan.capture import load_lidar  # noqa: E402
from floorplan.chunks import umeyama  # noqa: E402
from floorplan.lidar import build_plan  # noqa: E402
from floorplan.pipeline import run  # noqa: E402
from floorplan.plan2d import ENCLOSED_FRACTION_SPARSE  # noqa: E402

FPS = 60
SIM = Path("data/home_c/photos_sim")


def photo_times(cap: str, k: str, names) -> np.ndarray:
    folder = k.split("e")[0]  # k8, k8p; a trailing "e2" = every other photo
    folder = "k8" if folder == "k4" else folder  # the Kaggle k4 sets are every other k8 photo
    man = json.loads((SIM / cap / folder / "manifest.json").read_text())
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
        cap, _, only = cap.partition("@")  # <capture>@<room>: one folder reconstructed alone
        src = Path("data/home_c/lidar") / cap
        if cap not in lidar:
            lidar[cap] = run(src, "lidar")
        d = np.load(f)
        pts, poses = d["points"].astype(float), d["poses"]
        ref = load_lidar(src).poses
        idx = np.clip((photo_times(cap, k, d["names"]) * FPS).round().astype(int), 0, len(ref) - 1)
        c, c_ref = poses[:, :3, 3], ref[idx, :3, 3]
        s, r, t = umeyama(c, c_ref)
        ate = np.linalg.norm(s * c @ r.T + t - c_ref, axis=1)
        plan = build_plan(place(pts, poses, c_ref), ENCLOSED_FRACTION_SPARSE)  # as the tier
        ref_plan = lidar[cap]
        video = [(vr, world(vr, plan.rotation_deg)) for vr in plan.rooms]
        side, ceil = [], []
        ref_rooms = ref_plan.rooms
        if only:  # one room: score it against the LiDAR room it overlaps most
            pairs = [(lr, world(lr, ref_plan.plan_rotation_deg)) for lr in ref_rooms]
            vp = [w for _, w in video]
            ref_rooms = [
                max(pairs, key=lambda q: max((overlap(v, q[1]) for v in vp), default=0))[0]
            ]
            model = f"{model} {only}"
        for lr in ref_rooms:
            lp = world(lr, ref_plan.plan_rotation_deg)
            if not video:
                break
            best, bp = max(video, key=lambda v, lp=lp: overlap(v[1], lp))
            if overlap(bp, lp) < 0.3 * min(best.floor_area.value, lr.floor_area.value):
                per_room.append((cap, model, k, lr.id, None, None))
                continue
            a = (best.floor_area.value / lr.floor_area.value) ** 0.5
            h = None  # a ceiling no photo saw has no height
            if best.ceiling_height and lr.ceiling_height:
                h = best.ceiling_height.value / lr.ceiling_height.value
                ceil.append(h)
            side.append(a)
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
                len(ref_rooms),
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
