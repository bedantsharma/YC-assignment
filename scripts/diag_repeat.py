"""Diagnostics for fix map 02 (repeatability): per wall, the surfaces behind each room edge;
per room, the height peaks the floor and ceiling are picked from.

Usage: uv run scripts/diag_repeat.py data/home_c/lidar/c_damage_01 [more captures]
"""

import math
import sys
from pathlib import Path

import numpy as np

from floorplan.capture import load_lidar
from floorplan.cloud import fuse
from floorplan.levels import floor_level
from floorplan.lidar import GRID_RES_M
from floorplan.plan2d import (
    WALL_BAND_M,
    dominant_angle,
    floor_mask,
    lintel_mask,
    make_grid,
    observed_mask,
    segment_rooms,
    wall_mask,
)
from floorplan.rooms import CORNER_TRIM_M, measure_room, rectilinear_outline

CACHE = Path("outputs/cache")


def cloud(cap: Path) -> np.ndarray:
    f = CACHE / f"{cap.name}.npy"
    if not f.exists():
        n = len(load_lidar(cap).depth_paths)
        np.save(f, fuse(load_lidar(cap, stride=max(1, math.ceil(n / 3000)))))
    return np.load(f)


def peaks(values: np.ndarray, lo: float, hi: float, bin_m: float = 0.01, top: int = 4) -> str:
    counts, edges = np.histogram(values, bins=np.arange(lo, hi + bin_m, bin_m))
    counts = np.convolve(counts, np.ones(3) / 3, mode="same")
    pad = np.pad(counts, 1)
    idx = np.flatnonzero((counts >= pad[:-2]) & (counts >= pad[2:]) & (counts > 0))
    idx = idx[np.argsort(counts[idx])[::-1][:top]]
    return " ".join(f"{edges[i] + bin_m / 2:+.2f}({counts[i]:.0f})" for i in sorted(idx))


def main() -> None:
    for cap in map(Path, sys.argv[1:]):
        pts = cloud(cap)
        floor = floor_level(pts[:, 2])
        h = pts[:, 2] - floor.z
        band = pts[(h > 0.3) & (h < 2.0)]
        grid = make_grid(pts, dominant_angle(band), GRID_RES_M)
        walls = wall_mask(pts, grid, floor.z)
        labels, _ = segment_rooms(
            walls,
            observed_mask(pts, grid, floor.z),
            GRID_RES_M,
            lintel_mask(pts, grid, floor.z),
            floor_mask(pts, grid, floor.z),
        )
        print(f"\n== {cap.name}: {len(pts)} pts, global floor z={floor.z:.3f} ±{floor.spread:.3f}")
        print("  height peaks (m above floor, count):", peaks(h, -0.2, 4.0, top=8))
        ij = grid.cells(pts[:, :2])
        on_wall = walls[ij[:, 0], ij[:, 1]] & (h > WALL_BAND_M[0]) & (h < WALL_BAND_M[1])
        wall_uv = grid.to_plan(pts[on_wall, :2])
        for k in range(1, labels.max() + 1):
            mask = labels == k
            raw = rectilinear_outline(mask, grid)
            snapped = measure_room(mask, pts, grid, walls, floor.z)
            print(
                f"  room {k}: floor {snapped.floor.z - floor.z:+.3f}, ceiling "
                f"{snapped.ceiling.z - snapped.floor.z if snapped.ceiling else None}"
            )
            zr = pts[mask[ij[:, 0], ij[:, 1]], 2] - snapped.floor.z
            print("    room height peaks >2 m:", peaks(zr, 2.0, 4.0, top=6))
            n = len(raw.edges)
            for e, (edge, sn) in enumerate(zip(raw.edges, snapped.edges, strict=True)):
                p, q = raw.polygon[e], raw.polygon[(e + 1) % n]
                along = 1 - edge.axis
                lo, hi = sorted((p[along], q[along]))
                direction = np.sign(q[along] - p[along])
                outward = direction if edge.axis == 0 else -direction
                off = (wall_uv[:, edge.axis] - edge.coord) * outward
                near = (
                    (wall_uv[:, along] > lo + CORNER_TRIM_M)
                    & (wall_uv[:, along] < hi - CORNER_TRIM_M)
                    & (off > -0.15)
                    & (off < 0.6)
                )
                print(
                    f"    edge {e} axis {edge.axis} len {hi - lo:.2f} snap "
                    f"{(sn.coord - edge.coord) * outward:+.3f} sigma {sn.sigma:.3f} "
                    f"| surfaces: {peaks(off[near], -0.15, 0.6)}"
                )


if __name__ == "__main__":
    main()
