"""Synthetic fused point clouds of simple apartments, for geometry tests (z up, metres)."""

import numpy as np

rng = np.random.default_rng(1)
STEP = 0.02  # sample spacing on every surface


def wall(a, b, z0=0.0, z1=2.5, gap=None):
    """Vertical wall from 2D point a to b; gap=(start, end) metres along it is left open."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    length = np.linalg.norm(b - a)
    s = np.arange(0, length, STEP)
    if gap:
        s = s[(s < gap[0]) | (s > gap[1])]
    z = np.arange(z0, z1, STEP)
    s, z = np.meshgrid(s, z)
    xy = a + np.outer(s.ravel(), (b - a) / length)
    return np.column_stack([xy, z.ravel()])


def slab(x0, x1, y0, y1, z):
    x, y = np.meshgrid(np.arange(x0, x1, STEP), np.arange(y0, y1, STEP))
    return np.column_stack([x.ravel(), y.ravel(), np.full(x.size, z)])


def two_rooms(angle_deg=30.0, noise=0.004, ceiling=2.5):
    """Room A [0,4]x[0,3] and room B [4,7]x[0,3], 0.9 m door in the shared wall at y 1-1.9.

    Also a 1.2 x 0.8 table (top at 0.75 m) in room A, and floor seen through an open
    window beyond room B's east wall (x 7.2-9), which must not become a room.
    """
    parts = [
        wall((0, 0), (7, 0), z1=ceiling),
        wall((7, 0), (7, 3), z1=ceiling, gap=(1.0, 2.0)),  # open window, floor to ceiling
        wall((7, 3), (0, 3), z1=ceiling),
        wall((0, 3), (0, 0), z1=ceiling),
        wall((4, 0), (4, 3), z1=ceiling, gap=(1.0, 1.9)),
        slab(0, 7, 0, 3, 0.0),
        slab(0, 7, 0, 3, ceiling),
        slab(1.0, 2.2, 1.0, 1.8, 0.75),
        slab(7.2, 9.0, 0.8, 2.2, 0.0),
    ]
    pts = np.concatenate(parts)
    pts += rng.normal(0, noise, pts.shape)
    t = np.radians(angle_deg)
    rot = np.array([[np.cos(t), -np.sin(t), 0], [np.sin(t), np.cos(t), 0], [0, 0, 1]])
    return pts @ rot.T
