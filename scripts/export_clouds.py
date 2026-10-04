"""Export a Stray Scanner capture as a coloured, fused point cloud (binary PLY) for
pretrained point-cloud models run on Kaggle (docs/lidar_model_research.md).

Same fusion as the LiDAR tier (cloud.fuse: confidence 2, 0.1-4 m, OpenCV back-projection),
plus the colour of each depth pixel from the RGB frame with the same index (Stray's rgb.mp4
has one frame per depth frame, same sensor orientation; scaled to depth resolution).
Points are averaged per 2 cm voxel, colours too. Frame: common frame, metres, z up.

Usage: uv run scripts/export_clouds.py data/home_c/lidar/c_damage_01 [...] [--stride 4]
       -> outputs/lidar_clouds/<id>.ply
"""

import argparse
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from floorplan.capture import load_lidar
from floorplan.cloud import MIN_DEPTH_M

VOXEL = 0.02
MAX_DEPTH = 4.0
OUT = Path("outputs/lidar_clouds")


def rgb_frames(video: Path, w: int, h: int, stride: int):
    """Every stride-th frame of the video at w x h, as uint8 arrays, in order."""
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-noautorotate", "-i", str(video), "-vf",
         f"select='not(mod(n\\,{stride}))',scale={w}:{h}", "-vsync", "0",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE,
    )  # fmt: skip
    size = w * h * 3
    while chunk := proc.stdout.read(size):
        if len(chunk) < size:
            break
        yield np.frombuffer(chunk, np.uint8).reshape(h, w, 3)
    proc.wait()


def export(capture: Path, stride: int) -> Path:
    cap = load_lidar(capture, stride=stride)
    first = np.asarray(Image.open(cap.depth_paths[0]))
    h, w = first.shape
    pts, cols = [], []
    frames = rgb_frames(capture / "rgb.mp4", w, h, stride)
    for depth_path, conf_path, pose, K, rgb in zip(
        cap.depth_paths, cap.confidence_paths, cap.poses, cap.intrinsics, frames, strict=False
    ):
        z = np.asarray(Image.open(depth_path), dtype=np.float32) / 1000.0
        conf = np.asarray(Image.open(conf_path))
        v, u = np.nonzero((conf >= 2) & (z > MIN_DEPTH_M) & (z < MAX_DEPTH))
        zm = z[v, u]
        cam = np.stack([(u - K[0, 2]) * zm / K[0, 0], (v - K[1, 2]) * zm / K[1, 1], zm], 1)
        pts.append(cam @ pose[:3, :3].T + pose[:3, 3])
        cols.append(rgb[v, u])
    p, c = np.concatenate(pts), np.concatenate(cols).astype(np.float64)
    cells = np.floor(p / VOXEL).astype(np.int64)
    _, inv, counts = np.unique(cells, axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    mean = lambda x: np.stack([np.bincount(inv, x[:, i]) for i in range(3)], 1) / counts[:, None]  # noqa: E731
    p, c = mean(p), np.clip(mean(c), 0, 255).astype(np.uint8)

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{capture.name}.ply"
    rec = np.empty(len(p), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                  ("red", "u1"), ("green", "u1"), ("blue", "u1")])  # fmt: skip
    for k, a in zip(("x", "y", "z"), p.T, strict=True):
        rec[k] = a
    for k, a in zip(("red", "green", "blue"), c.T, strict=True):
        rec[k] = a
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {len(p)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n"
    )
    out.write_bytes(header.encode() + rec.tobytes())
    print(f"{capture.name}: {len(cap.depth_paths)} frames -> {len(p)} points -> {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("captures", type=Path, nargs="+")
    ap.add_argument("--stride", type=int, default=4)
    args = ap.parse_args()
    for c in args.captures:
        export(c, args.stride)


if __name__ == "__main__":
    main()
