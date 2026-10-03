"""Run the photo tier's reconstruction locally and save it for scoring / diagnosis.

Same stages as `floorplan run <photo folders>` up to the reconstruction, saved as
<out>/<capture>__<model>__k<K>.npz in the Kaggle photo bake-off format (voxel-thinned
points, per-point view index, camera poses, photo names), so scripts/score_photos.py
scores it the same way.

Usage: uv run scripts/photo_eval.py data/home_c/photos_sim/c_damage_01/k8 [--every 2]
"""

import argparse
from pathlib import Path

import numpy as np

from floorplan.capture import load_photos
from floorplan.chunks import chain
from floorplan.cloud import voxel_downsample
from floorplan.mvs import reconstruct
from floorplan.photos import load_images
from floorplan.pipeline import VIDEO_OVERLAP, VIDEO_WINDOW


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--model", default="pi3x", choices=["pi3x", "mapanything"])
    ap.add_argument("--every", type=int, default=1, help="keep every n-th photo per room")
    ap.add_argument("--room", help="reconstruct only this room folder")
    ap.add_argument("--out", type=Path, default=Path("outputs/photo_eval"))
    args = ap.parse_args()

    rooms = load_photos(args.folder).rooms
    if args.room:
        rooms = {args.room: rooms[args.room]}
    paths = [p for photos in rooms.values() for p in photos[:: args.every]]
    images = load_images(paths)
    if len(images) <= VIDEO_WINDOW:
        rec = reconstruct(images, args.model)
    else:
        n = len(images)
        rec, _ = chain(
            n,
            lambda i: reconstruct([images[j] for j in i], args.model),
            VIDEO_WINDOW,
            VIDEO_OVERLAP,
        )
    pts, view = [], []
    for i in range(len(images)):
        p = voxel_downsample(rec.view_points[i][rec.view_keep[i]].astype(float), 0.02)
        pts.append(p)
        view.append(np.full(len(p), i, np.int16))
    cap = args.folder.parent.name + (f"@{args.room}" if args.room else "")
    k = args.folder.name.removeprefix("k") + (f"e{args.every}" if args.every > 1 else "")
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / f"{cap}__{args.model}__k{k}.npz"
    names = np.array([f"{p.parent.name}/{p.name}" for p in paths])
    np.savez_compressed(
        out,
        points=np.concatenate(pts).astype(np.float32),
        view=np.concatenate(view),
        poses=rec.cam_poses,
        names=names,
    )
    print(out, len(images), "photos", f"{rec.seconds:.0f} s")


if __name__ == "__main__":
    main()
