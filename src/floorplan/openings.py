"""Doors and open passages in a room's walls, from gaps in the wall's points.

Each wall is unrolled into an elevation (position along the wall x height) from the points
in a band around its measured face (the face +- the drift smear). A column is open when
almost none of its cells at body height (BODY_M) hold points. A run of open columns
OPENING_WIDTH_M wide is an opening only if the scan saw through it (points beyond the wall
at body height, or the floor past it): an unscanned stretch of wall is empty too, but has
nothing behind it. With wall above it (a lintel under the ceiling) it is a door, open to
the ceiling a passage.

Windows are not detected: on home C's LiDAR the window wall returns points across the
glass (grilles, frame, deep reveal), so a window leaves no gap (docs/openings.md).
"""

from dataclasses import dataclass

import numpy as np

from floorplan.plan2d import Grid
from floorplan.rooms import RoomShape

BAND_M = (-0.25, 0.35)  # around the measured face: the wall and its drift smear
BEYOND_M = (0.4, 4.0)  # where the scan sees through an opening
BODY_M = (0.3, 1.8)  # a doorway is empty at these heights
COL_M = 0.05
CELL_Z_M = 0.05
OPEN_MAX_FILL = 0.1  # a column is open if under 10% of its body-height cells hold points
OPENING_WIDTH_M = (0.6, 3.0)
MIN_SEEN_THROUGH = 30  # points behind the opening that prove the scan saw through it
CEILING_GAP_M = 0.15  # a head this close to the ceiling is no lintel: a passage
WIDTH_SIGMA_M = 0.03  # half a column on each jamb, as a 1-sigma


@dataclass
class Found:
    edge: int
    kind: str  # "door" | "passage"
    width: float
    width_sigma: float
    height: float | None  # head height above the floor; None for a passage
    centre: np.ndarray  # plan coordinates of the opening's centre on the wall
    connects_to: int | None  # room label on the other side


def find_openings(
    shape: RoomShape,
    points: np.ndarray,
    grid: Grid,
    labels: np.ndarray,
    room: int,
) -> list[Found]:
    if shape.floor is None:
        return []
    uv = grid.to_plan(points[:, :2])
    h = points[:, 2] - shape.floor.z
    top = shape.ceiling.z - shape.floor.z if shape.ceiling else None
    out = []
    n = len(shape.edges)
    for k, edge in enumerate(shape.edges):
        p, q = shape.polygon[k], shape.polygon[(k + 1) % n]
        along = 1 - edge.axis
        d = np.sign(q[along] - p[along])
        outward = d if edge.axis == 0 else -d
        off = (uv[:, edge.axis] - edge.coord) * outward
        s = (uv[:, along] - p[along]) * d
        on = (s > 0) & (s < edge.length)
        out += _edge_openings(k, edge.length, s, off, h, on, top, p, d, along, outward, edge)
    for f in out:
        f.connects_to = _other_room(f, labels, grid, room, shape.edges[f.edge], shape.polygon)
    return out


def _edge_openings(k, length, s, off, h, on, top, p, d, along, outward, edge) -> list[Found]:
    if length < OPENING_WIDTH_M[0]:
        return []
    ncol = int(length / COL_M)
    nz = int((BODY_M[1] - BODY_M[0]) / CELL_Z_M)
    wall = on & (off > BAND_M[0]) & (off < BAND_M[1])
    body = wall & (h > BODY_M[0]) & (h < BODY_M[1])
    occ = np.zeros((ncol, nz), bool)
    ci = np.clip((s[body] / COL_M).astype(int), 0, ncol - 1)
    zi = np.clip(((h[body] - BODY_M[0]) / CELL_Z_M).astype(int), 0, nz - 1)
    occ[ci, zi] = True
    is_open = occ.mean(axis=1) < OPEN_MAX_FILL
    found = []
    for a, b in _runs(is_open):
        width = (b - a) * COL_M
        if not OPENING_WIDTH_M[0] <= width <= OPENING_WIDTH_M[1]:
            continue
        s0, s1 = a * COL_M, b * COL_M
        span = on & (s > s0) & (s < s1)
        beyond = span & (off > BEYOND_M[0]) & (off < BEYOND_M[1])
        through = beyond & (h > BODY_M[0]) & (h < BODY_M[1])
        seen = through.sum() + (beyond & (np.abs(h) < 0.05)).sum()  # or the floor past it
        if seen < MIN_SEEN_THROUGH:
            continue  # nothing behind: an unscanned stretch of wall, not an opening
        above = span & (off > BAND_M[0]) & (off < BAND_M[1]) & (h > BODY_M[1])
        if top is not None:
            above &= h < top - CEILING_GAP_M
        head = float(np.percentile(h[above], 5)) if above.sum() >= MIN_SEEN_THROUGH else None
        centre = np.zeros(2)
        centre[edge.axis] = edge.coord
        centre[along] = p[along] + d * (s0 + s1) / 2
        found.append(Found(k, "door" if head else "passage", width, WIDTH_SIGMA_M * np.sqrt(2),
                           head, centre, None))  # fmt: skip
    return found


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) index pairs of the True runs."""
    m = np.concatenate([[False], mask, [False]]).astype(int)
    edges = np.flatnonzero(np.diff(m))
    return list(zip(edges[::2], edges[1::2], strict=True))


def _other_room(f: Found, labels: np.ndarray, grid: Grid, room: int, edge, poly) -> int | None:
    """Room label 0.6 m past the opening's centre, if another room is there."""
    k = f.edge
    n = len(poly)
    p, q = poly[k], poly[(k + 1) % n]
    along = 1 - edge.axis
    d = np.sign(q[along] - p[along])
    outward = d if edge.axis == 0 else -d
    for step in (0.4, 0.6, 0.9):
        uv = f.centre.copy()
        uv[edge.axis] += outward * step
        ij = np.floor((uv - grid.origin) / grid.res).astype(int)
        if (ij < 0).any() or (ij >= np.array(grid.shape)).any():
            return None
        lab = int(labels[ij[0], ij[1]])
        if lab and lab != room:
            return lab
    return None
