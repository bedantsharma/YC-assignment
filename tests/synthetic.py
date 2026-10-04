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


def two_rooms(angle_deg=30.0, noise=0.004, ceiling=2.5, door=(1.0, 1.9), lintel=None):
    """Room A [0,3.95]x[0,3] and room B [4.05,7]x[0,3]: a 10 cm partition with a door at
    y in `door`, open to the ceiling, or under a lintel at height `lintel` if given.

    Also a 1.2 x 0.8 table (top at 0.75 m) in room A, and floor seen through an open
    window beyond room B's east wall (x 7.2-9), which must not become a room.
    """
    top = lintel or ceiling
    partition = [
        wall((3.95, 0), (3.95, 3), z1=top, gap=door),  # room A face
        wall((4.05, 0), (4.05, 3), z1=top, gap=door),  # room B face
    ]
    if lintel:
        partition += [
            wall((3.95, 0), (3.95, 3), z0=lintel, z1=ceiling),
            wall((4.05, 0), (4.05, 3), z0=lintel, z1=ceiling),
            slab(3.95, 4.05, door[0], door[1], lintel),  # lintel underside
        ]
    parts = [
        *partition,
        wall((0, 0), (7, 0), z1=ceiling),
        wall((7, 0), (7, 3), z1=0.9),  # window: sill below 0.9 m, head above 2.1 m
        wall((7, 0), (7, 3), z0=0.9, z1=2.1, gap=(1.0, 2.0)),
        wall((7, 0), (7, 3), z0=2.1, z1=ceiling),
        wall((7, 3), (0, 3), z1=ceiling),
        wall((0, 3), (0, 0), z1=ceiling),
        slab(0, 3.95, 0, 3, 0.0),
        slab(4.05, 7, 0, 3, 0.0),
        slab(0, 3.95, 0, 3, ceiling),
        slab(4.05, 7, 0, 3, ceiling),
        slab(1.0, 2.2, 1.0, 1.8, 0.75),
        slab(7.2, 9.0, 0.8, 2.2, 0.0),
    ]
    pts = np.concatenate(parts)
    pts += rng.normal(0, noise, pts.shape)
    t = np.radians(angle_deg)
    rot = np.array([[np.cos(t), -np.sin(t), 0], [np.sin(t), np.cos(t), 0], [0, 0, 1]])
    return pts @ rot.T


def kitchen(noise=0.004, ceiling=2.7):
    """Room [0,4]x[0,3] with a base cabinet along the east wall: front face at x = 3.4
    (0-0.9 m), top at 0.9 m from x 3.4 to 4. The room's east wall is at x = 4, not 3.4.
    """
    parts = [
        wall((0, 0), (4, 0), z1=ceiling),
        wall((4, 0), (4, 3), z0=0.9, z1=ceiling),  # tiled wall above the counter
        wall((4, 3), (0, 3), z1=ceiling),
        wall((0, 3), (0, 0), z1=ceiling),
        wall((3.4, 0), (3.4, 3), z1=0.9),  # cabinet front
        slab(3.4, 4, 0, 3, 0.9),  # counter top
        slab(0, 3.4, 0, 3, 0.0),
        slab(0, 4, 0, 3, ceiling),
    ]
    pts = np.concatenate(parts)
    return pts + rng.normal(0, noise, pts.shape)


def smeared_room(noise=0.004, ceiling=3.0):
    """Room [0,4]x[0,3] as a drifting scan sees it: the east wall appears three times, at
    x = 3.9, 4.0 and 4.1 (true wall: the middle), and a wardrobe stands against the north
    wall (front face at y = 2.6 up to 2.1 m, top at 2.1 m; the wall is at y = 3).
    """
    parts = [
        wall((0, 0), (3.9, 0), z1=ceiling),
        *[wall((x, 0), (x, 3), z1=ceiling) for x in (3.9, 4.0, 4.1)],
        wall((4.1, 3), (0, 3), z1=ceiling),
        wall((0, 3), (0, 0), z1=ceiling),
        wall((0.2, 2.6), (2.2, 2.6), z1=2.1),  # wardrobe front
        slab(0.2, 2.2, 2.6, 3.0, 2.1),  # wardrobe top
        wall((0.2, 2.6), (0.2, 3.0), z1=2.1),  # wardrobe sides
        wall((2.2, 2.6), (2.2, 3.0), z1=2.1),
        slab(0, 3.9, 0, 3, 0.0),
        slab(0, 4.1, 0, 3, ceiling),
    ]
    pts = np.concatenate(parts)
    return pts + rng.normal(0, noise, pts.shape)
