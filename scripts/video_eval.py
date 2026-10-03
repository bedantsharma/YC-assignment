"""Run the video tier's reconstruction locally and save it for scoring.

Same stages as `floorplan run --tier video` up to the reconstruction (upright frames, one
pass or chained windows), saved as outputs/video_eval/<capture>__<model>__<n>.npz in the
bake-off format (voxel-thinned points, camera poses), so `scripts/score_bakeoff.py --dir
outputs/video_eval` scores it against the LiDAR and ARKit of the same recording.

Usage: uv run scripts/video_eval.py data/home_c/lidar/c_home_01 --model pi3x --frames 90
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from floorplan.capture import load_video
from floorplan.chunks import chain
from floorplan.cloud import voxel_downsample
from floorplan.mvs import reconstruct
from floorplan.pipeline import VIDEO_OVERLAP, VIDEO_WINDOW
from floorplan.video import orientation, sample_frames


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("capture", type=Path)
    ap.add_argument("--model", default="pi3x", choices=["pi3x", "mapanything"])
    ap.add_argument("--frames", type=int, default=30)
    ap.add_argument("--window", type=int, default=VIDEO_WINDOW)
    ap.add_argument("--overlap", type=int, default=VIDEO_OVERLAP)
    ap.add_argument("--out", type=Path, default=Path("outputs/video_eval"))
    args = ap.parse_args()

    video = load_video(args.capture).path
    frames = sample_frames(video, args.frames, orientation(video).up_side)
    start = time.perf_counter()
    links = []
    if len(frames) <= args.window:
        rec = reconstruct(frames, args.model)
    else:
        rec, links = chain(
            len(frames),
            lambda idx: reconstruct([frames[i] for i in idx], args.model),
            args.window,
            args.overlap,
        )
    seconds = time.perf_counter() - start

    args.out.mkdir(parents=True, exist_ok=True)
    tag = f"{args.capture.name}__{args.model}__{len(frames)}"
    pts = voxel_downsample(rec.points.astype(float), 0.02)
    np.savez_compressed(args.out / f"{tag}.npz", points=pts.astype(np.float32), poses=rec.cam_poses)
    info = {
        "tag": tag,
        "seconds": round(seconds, 1),
        "window": args.window,
        "overlap": args.overlap,
        "links": [vars(k) for k in links],
    }
    (args.out / f"{tag}.json").write_text(json.dumps(info, indent=2))
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
