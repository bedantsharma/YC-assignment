"""Measure ARKit pose drift in a LiDAR capture from the walls themselves (no ground truth).

The capture is fused in time chunks. Per chunk: the wall orientation (yaw drift shows as a
changing angle) and the position of each major wall plane seen in it (translation drift
shows as the same wall at different positions when it is revisited later).

Usage: uv run scripts/drift_probe.py data/home_c/lidar/c_home_01 [--chunks 10]
"""

import argparse
import dataclasses
import math
from pathlib import Path

import numpy as np

from floorplan.capture import load_lidar
from floorplan.cloud import fuse
from floorplan.levels import floor_level
from floorplan.plan2d import WALL_BAND_M, dominant_angle, make_grid

MIN_WALL_POINTS = 2000  # a chunk must see this many points of a wall to place it
PEAK_WINDOW_M = 0.1  # drift larger than this per chunk would be missed (none seen)
ISOLATION_M = 0.25  # walls with another wall this close are skipped (faces of one partition)


def wall_peaks(x: np.ndarray, bin_m: float = 0.02, top: int = 8) -> np.ndarray:
    counts, edges = np.histogram(x, bins=np.arange(x.min(), x.max() + bin_m, bin_m))
    counts = np.convolve(counts, np.ones(3) / 3, mode="same")
    pad = np.pad(counts, 1)
    idx = np.flatnonzero((counts >= pad[:-2]) & (counts > pad[2:]))
    idx = idx[np.argsort(counts[idx])[::-1][:top]]
    return np.sort(edges[idx] + bin_m / 2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("capture", type=Path)
    ap.add_argument("--chunks", type=int, default=10)
    args = ap.parse_args()

    n = len(load_lidar(args.capture).depth_paths)
    cap = load_lidar(args.capture, stride=max(1, math.ceil(n / 1500)))
    m = len(cap.depth_paths)
    bounds = np.linspace(0, m, args.chunks + 1).astype(int)
    clouds = []
    for a, b in zip(bounds[:-1], bounds[1:], strict=True):
        part = dataclasses.replace(
            cap,
            depth_paths=cap.depth_paths[a:b],
            confidence_paths=cap.confidence_paths[a:b],
            poses=cap.poses[a:b],
            intrinsics=cap.intrinsics[a:b],
        )
        clouds.append(fuse(part, voxel=0.02))
    pts = np.concatenate(clouds)
    floor = floor_level(pts[:, 2]).z

    def band(p: np.ndarray) -> np.ndarray:
        h = p[:, 2] - floor
        return p[(h > WALL_BAND_M[0]) & (h < WALL_BAND_M[1])]

    angle = dominant_angle(band(pts))
    grid = make_grid(pts, angle, 0.03)
    uv_all = grid.to_plan(band(pts)[:, :2])
    peaks = []
    for k in (0, 1):
        pk = wall_peaks(uv_all[:, k], top=12)
        gaps = np.diff(pk)
        isolated = np.r_[np.inf, gaps] > ISOLATION_M
        isolated &= np.r_[gaps, np.inf] > ISOLATION_M
        peaks.append(pk[isolated])
    print(f"{args.capture.name}: {m} frames in {args.chunks} chunks; plan angle {angle:.2f} deg")
    print("walls u:", " ".join(f"{p:.2f}" for p in peaks[0]))
    print("walls v:", " ".join(f"{p:.2f}" for p in peaks[1]))

    print("\nchunk | yaw vs whole (deg) | wall offsets vs whole (cm), u walls | v walls")
    spreads = {(k, p): [] for k in (0, 1) for p in peaks[k]}
    for c, cloud in enumerate(clouds):
        b = band(cloud)
        if len(b) < 5000:
            print(f"{c:5d} | too few wall points")
            continue
        yaw = (dominant_angle(b) - angle + 45) % 90 - 45
        uv = grid.to_plan(b[:, :2])
        cols = []
        for k in (0, 1):
            row = []
            for p in peaks[k]:
                near = uv[np.abs(uv[:, k] - p) < PEAK_WINDOW_M, k]
                if len(near) < MIN_WALL_POINTS:
                    row.append("    .")
                    continue
                local = float(np.median(near))
                spreads[(k, p)].append(local - p)
                row.append(f"{100 * (local - p):+5.1f}")
            cols.append(" ".join(row))
        print(f"{c:5d} | {yaw:+6.2f} | {cols[0]} | {cols[1]}")

    seen = [(k, p, np.ptp(v)) for (k, p), v in spreads.items() if len(v) >= 2]
    print("\nwalls seen in >= 2 chunks: max spread of position between chunks")
    for k, p, s in sorted(seen, key=lambda t: -t[2]):
        print(f"  {'uv'[k]} = {p:+.2f} m: {100 * s:.1f} cm")


if __name__ == "__main__":
    main()
