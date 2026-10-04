"""Graded-fix diagnostic (NEXT-SESSION §1): per wall, every surface behind our snapped edge.

For each room edge, all points within the edge's span (corners trimmed) are binned by
signed outward offset from the edge we output (0 = our wall; + = outside the room). Each
peak is printed with its point count, its height range (5th-95th percentile above the
floor) and the fraction of the edge's length it covers, so a full-height wall, a drift
copy of it, a cabinet (ends below the ceiling) and the neighbour room's face (behind a
wall's thickness) can be told apart. Per room: the deficit per axis vs the ground truth.

Usage: uv run scripts/diag_walls.py [--upper] [c_damage_01 c_damage_02 c_home_01 | capture dir]
"""

import json
import sys
from pathlib import Path

import numpy as np
from diag_repeat import cloud

from floorplan.levels import floor_level
from floorplan.lidar import GRID_RES_M
from floorplan.plan2d import (
    dominant_angle,
    floor_mask,
    lintel_mask,
    make_grid,
    observed_mask,
    segment_rooms,
    wall_mask,
)
from floorplan.rooms import CORNER_TRIM_M, measure_room

GT = json.loads(Path("data/gt/home_c.json").read_text())["rooms"]
BOXES = json.loads(Path("data/gt/home_c_rooms.json").read_text())["rooms"]
BY_LABEL = {r["our_label"]: k for k, r in GT.items()}
LIDAR = Path("data/home_c/lidar")
LO, HI, BIN = -0.3, 0.9, 0.02
UPPER = False  # --upper: only points above 2.3 m (above furniture and door heads)


def gt_key(cap: str, poly: np.ndarray) -> str | None:
    if cap != "c_home_01":
        return "bedroom"
    c = poly.mean(0)
    for name, (x0, y0, x1, y1) in BOXES.items():
        if x0 <= c[0] <= x1 and y0 <= c[1] <= y1:
            return BY_LABEL.get(name)
    return None


def surfaces(off: np.ndarray, h: np.ndarray, along: np.ndarray, span: float) -> list[str]:
    counts, edges = np.histogram(off, bins=np.arange(LO, HI + BIN, BIN))
    sm = np.convolve(counts, np.ones(3) / 3, mode="same")
    pad = np.pad(sm, 1)
    idx = np.flatnonzero((sm >= pad[:-2]) & (sm > pad[2:]) & (sm >= 0.08 * sm.max()))
    out = []
    for i in idx:
        c = edges[i] + BIN / 2
        sel = np.abs(off - c) < BIN * 1.5
        z = np.percentile(h[sel], [5, 95])
        cover = len(np.unique(np.floor(along[sel] / 0.1))) * 0.1 / span
        out.append(f"{c:+.2f}m n={sm[i]:.0f} h={z[0]:.1f}-{z[1]:.1f} cov={min(cover, 1):.0%}")
    return out


def main() -> None:
    global UPPER
    UPPER = "--upper" in sys.argv
    caps = [a for a in sys.argv[1:] if a != "--upper"]
    caps = caps or ["c_damage_01", "c_damage_02", "c_home_01"]
    for cap in caps:
        path = Path(cap) if "/" in cap else LIDAR / cap
        pts = cloud(path)
        cap = path.name
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
        uv = grid.to_plan(pts[:, :2])
        print(f"\n===== {cap}")
        for k in range(1, labels.max() + 1):
            shape = measure_room(labels == k, pts, grid, walls, floor.z)
            poly = shape.polygon
            key = gt_key(cap, poly)
            ext = np.ptp(poly, axis=0)
            ceil = shape.ceiling.z - shape.floor.z if shape.ceiling else 3.3
            line = f"-- room {k} ({key}): extent u {ext[0]:.2f} x v {ext[1]:.2f}"
            line += f", {shape.area:.1f} m2"
            if key:
                g = GT[key]
                gl, gs = max(g["width_m"], g["depth_m"]), min(g["width_m"], g["depth_m"])
                ol, os_ = max(ext), min(ext)
                line += f"; GT {gl:.2f} x {gs:.2f} -> short by {gl - ol:+.2f} (long)"
                line += f" / {gs - os_:+.2f} (short)"
            print(line)
            n = len(shape.edges)
            for e, edge in enumerate(shape.edges):
                p, q = poly[e], poly[(e + 1) % n]
                al = 1 - edge.axis
                lo, hi = sorted((p[al], q[al]))
                direction = np.sign(q[al] - p[al])
                outward = direction if edge.axis == 0 else -direction
                off = (uv[:, edge.axis] - edge.coord) * outward
                sel = (
                    (uv[:, al] > lo + CORNER_TRIM_M)
                    & (uv[:, al] < hi - CORNER_TRIM_M)
                    & (off > LO)
                    & (off < HI)
                    & (h > (2.3 if UPPER else 0.1))
                    & (h < ceil - 0.15)
                )
                span = hi - lo - 2 * CORNER_TRIM_M
                side = ("u" if edge.axis == 0 else "v") + ("+" if outward > 0 else "-")
                print(
                    f"   e{e} {side} at {edge.coord:+.2f}, len {edge.length:.2f}"
                    f"{'' if edge.supported else ' (unsupported)'}"
                )
                if span < 0.2 or sel.sum() < 50:
                    print("      (too few points)")
                    continue
                for s in surfaces(off[sel], h[sel], uv[sel, al] - lo, span):
                    print("     ", s)


if __name__ == "__main__":
    main()
