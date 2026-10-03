"""Top-down 2D plan: wall orientation, occupancy grids and room segmentation.

Plan frame: the world rotated about z by -angle so the dominant walls run along u and v.
Grid cells index plan coordinates as (i, j) = floor((u, v) - origin) / res.
"""

from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi
from skimage.segmentation import watershed

WALL_BAND_M = (0.1, 2.3)  # heights above floor that count as wall evidence
WALL_SLICE_M = 0.1
WALL_MIN_EXTENT_M = 0.8  # a wall cell has points across at least this much height
WALL_MIN_TOP_M = 1.5  # ...and some above this: counters, sofa backs and desks stop lower
LINTEL_BAND_M = (1.95, 2.3)  # underside of a door head
LINTEL_CLEAR_M = (0.5, 1.8)  # a doorway is empty at body height
ENCLOSED_FRACTION = 0.75
DOOR_HALF_WIDTH_M = 0.45  # free space narrower than 2x this does not seed a room
MIN_SEED_AREA_M2 = 0.2
MIN_ROOM_AREA_M2 = 1.0
ANGLE_SAMPLE = 200_000


@dataclass
class Grid:
    angle_deg: float
    origin: np.ndarray  # plan coordinates of cell (0, 0)'s corner
    res: float
    shape: tuple[int, int]

    def to_plan(self, xy: np.ndarray) -> np.ndarray:
        t = np.radians(self.angle_deg)
        c, s = np.cos(t), np.sin(t)
        return np.column_stack([xy[:, 0] * c + xy[:, 1] * s, -xy[:, 0] * s + xy[:, 1] * c])

    def to_world(self, uv: np.ndarray) -> np.ndarray:
        t = np.radians(self.angle_deg)
        c, s = np.cos(t), np.sin(t)
        return np.column_stack([uv[:, 0] * c - uv[:, 1] * s, uv[:, 0] * s + uv[:, 1] * c])

    def cells(self, xy: np.ndarray) -> np.ndarray:
        ij = np.floor((self.to_plan(xy) - self.origin) / self.res).astype(int)
        return np.clip(ij, 0, np.array(self.shape) - 1)


def dominant_angle(points: np.ndarray) -> float:
    """Rotation in [0, 90) degrees that makes the walls' x and y histograms sharpest."""
    rng = np.random.default_rng(0)
    xy = points[rng.choice(len(points), min(len(points), ANGLE_SAMPLE), replace=False), :2]

    def sharpness(deg: float) -> float:
        t = np.radians(deg)
        u = xy[:, 0] * np.cos(t) + xy[:, 1] * np.sin(t)
        v = -xy[:, 0] * np.sin(t) + xy[:, 1] * np.cos(t)
        return sum(
            float((np.bincount(np.floor((w - w.min()) / 0.02).astype(int)) ** 2.0).sum())
            for w in (u, v)
        )

    coarse = max(np.arange(0, 90, 0.5), key=sharpness)
    fine = max(np.arange(coarse - 0.5, coarse + 0.5, 0.05), key=sharpness)
    return float(fine % 90)


def make_grid(points: np.ndarray, angle_deg: float, res: float, margin: float = 0.3) -> Grid:
    probe = Grid(angle_deg, np.zeros(2), res, (1, 1))
    uv = probe.to_plan(points[:, :2])
    origin = uv.min(axis=0) - margin
    shape = np.ceil((uv.max(axis=0) + margin - origin) / res).astype(int)
    return Grid(angle_deg, origin, res, (int(shape[0]), int(shape[1])))


def wall_mask(points: np.ndarray, grid: Grid, floor_z: float) -> np.ndarray:
    """Cells whose points span at least WALL_MIN_EXTENT_M of height and reach above
    WALL_MIN_TOP_M: walls, not tabletops or counter fronts (a window wall passes on the
    wall above its head)."""
    h = points[:, 2] - floor_z
    band = (h > WALL_BAND_M[0]) & (h < WALL_BAND_M[1])
    ij = grid.cells(points[band, :2])
    k = ((h[band] - WALL_BAND_M[0]) / WALL_SLICE_M).astype(int)
    n_slices = int(np.ceil((WALL_BAND_M[1] - WALL_BAND_M[0]) / WALL_SLICE_M))
    occupied = np.zeros((*grid.shape, n_slices), bool)
    occupied[ij[:, 0], ij[:, 1], k] = True
    high = round((WALL_MIN_TOP_M - WALL_BAND_M[0]) / WALL_SLICE_M)
    tall = occupied.sum(axis=2) >= round(WALL_MIN_EXTENT_M / WALL_SLICE_M)
    return tall & occupied[:, :, high:].any(axis=2)


def lintel_mask(points: np.ndarray, grid: Grid, floor_z: float) -> np.ndarray:
    """Cells with points at door-head height but none at body height: the lintel over a
    doorway. Rooms are split there whatever the door's width; open-plan junctions have no
    lintel and stay joined."""
    h = points[:, 2] - floor_z
    head = np.zeros(grid.shape, bool)
    clear = np.ones(grid.shape, bool)
    ij = grid.cells(points[(h > LINTEL_BAND_M[0]) & (h < LINTEL_BAND_M[1]), :2])
    head[ij[:, 0], ij[:, 1]] = True
    ij = grid.cells(points[(h > LINTEL_CLEAR_M[0]) & (h < LINTEL_CLEAR_M[1]), :2])
    clear[ij[:, 0], ij[:, 1]] = False
    return head & clear


def observed_mask(points: np.ndarray, grid: Grid, floor_z: float) -> np.ndarray:
    """Cells where anything was seen between the floor and wall-top height, holes filled."""
    h = points[:, 2] - floor_z
    ij = grid.cells(points[(h > -0.08) & (h < WALL_BAND_M[1]), :2])
    seen = np.zeros(grid.shape, bool)
    seen[ij[:, 0], ij[:, 1]] = True
    return ndi.binary_fill_holes(ndi.binary_closing(seen, iterations=5))


def enclosure(walls: np.ndarray, res: float, rays: int = 16, max_range: float = 8.0) -> np.ndarray:
    """Fraction of rays from each cell that hit a wall within max_range."""
    gi, gj = np.indices(walls.shape)
    hits = np.zeros(walls.shape)
    for a in np.arange(rays) * 2 * np.pi / rays:
        di, dj = np.cos(a), np.sin(a)
        alive = np.ones(walls.shape, bool)
        for step in range(1, int(max_range / res)):
            pi = np.rint(gi + di * step).astype(int)
            pj = np.rint(gj + dj * step).astype(int)
            alive &= (pi >= 0) & (pi < walls.shape[0]) & (pj >= 0) & (pj < walls.shape[1])
            hit = np.zeros(walls.shape, bool)
            hit[alive] = walls[pi[alive], pj[alive]]
            hits += hit
            alive &= ~hit
            if not alive.any():
                break
    return hits / rays


def segment_rooms(
    walls: np.ndarray, observed: np.ndarray, res: float, lintels: np.ndarray | None = None
) -> np.ndarray:
    """Label enclosed free space by room (0 = not a room), split at doorway constrictions
    and under door lintels."""
    free = observed & ~ndi.binary_dilation(walls)
    free &= enclosure(walls, res) >= ENCLOSED_FRACTION  # lintels play no part in enclosure
    if lintels is not None:
        free &= ~ndi.binary_dilation(lintels)
    dist = ndi.distance_transform_edt(free) * res
    seeds, n = ndi.label(dist > DOOR_HALF_WIDTH_M)
    seed_area = ndi.sum(np.ones_like(dist), seeds, np.arange(1, n + 1)) * res**2
    seeds[~np.isin(seeds, np.flatnonzero(seed_area >= MIN_SEED_AREA_M2) + 1)] = 0
    labels = watershed(-dist, seeds, mask=free)
    area = np.bincount(labels.ravel()) * res**2
    labels[area[labels] < MIN_ROOM_AREA_M2] = 0
    _, labels = np.unique(labels, return_inverse=True)  # renumber 1..n, 0 stays 0
    return labels.reshape(walls.shape)
