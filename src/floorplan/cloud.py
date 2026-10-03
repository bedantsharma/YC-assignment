"""Fuse LiDAR depth frames into one world-frame point cloud (metres, z up)."""

import numpy as np
from PIL import Image

from floorplan.capture import LidarCapture

MIN_DEPTH_M = 0.1


def fuse(
    cap: LidarCapture, max_depth: float = 4.0, voxel: float = 0.02, min_conf: int = 2
) -> np.ndarray:
    """Back-project every frame's confident depth through its pose; voxel=0 keeps all points."""
    chunks = []
    grid = None
    for depth_path, conf_path, pose, K in zip(
        cap.depth_paths, cap.confidence_paths, cap.poses, cap.intrinsics, strict=True
    ):
        z = np.asarray(Image.open(depth_path), dtype=np.float32) / 1000.0
        conf = np.asarray(Image.open(conf_path))
        if grid is None or grid[0].shape != z.shape:
            grid = np.meshgrid(np.arange(z.shape[1]), np.arange(z.shape[0]))
        u, v = grid
        m = (conf >= min_conf) & (z > MIN_DEPTH_M) & (z < max_depth)
        zm = z[m]
        cam = np.stack([(u[m] - K[0, 2]) * zm / K[0, 0], (v[m] - K[1, 2]) * zm / K[1, 1], zm], 1)
        chunks.append(cam @ pose[:3, :3].T + pose[:3, 3])
        if voxel > 0 and sum(map(len, chunks)) > 5_000_000:
            chunks = [voxel_downsample(np.concatenate(chunks), voxel)]
    points = np.concatenate(chunks) if chunks else np.empty((0, 3))
    return voxel_downsample(points, voxel) if voxel > 0 else points


def voxel_downsample(points: np.ndarray, voxel: float) -> np.ndarray:
    """Replace the points in each voxel by their mean."""
    if len(points) == 0:
        return points
    cells = np.floor(points / voxel).astype(np.int64)
    cells -= cells.min(axis=0)
    span = cells.max(axis=0) + 1
    keys = (cells[:, 0] * span[1] + cells[:, 1]) * span[2] + cells[:, 2]  # one int per voxel
    _, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    sums = np.zeros((len(counts), 3))
    np.add.at(sums, inverse.ravel(), points)
    return sums / counts[:, None]
