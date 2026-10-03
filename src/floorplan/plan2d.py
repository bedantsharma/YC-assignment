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
COUNTER_TOP_M = (0.82, 1.05)  # kitchen counter top heights
COUNTER_HOLLOW_M = (0.1, 0.7)  # a counter top hides what is under it
COUNTER_FRONT_MAX_TOP_M = 1.2  # a counter front ends at the top; a wall goes on above
FLOOR_TOL_M = 0.05
LINTEL_BAND_M = (1.95, 2.3)  # underside of a door head
LINTEL_CLEAR_M = (0.5, 1.8)  # a doorway is empty at body height
ENCLOSED_FRACTION = 0.75
# Photos see only parts of each wall (2-8 stills per room): rooms are enclosed by fewer
# observed walls, so the image tiers accept half the rays hitting a wall (docs/photo_tier.md)
ENCLOSED_FRACTION_SPARSE = 0.5
DOOR_HALF_WIDTH_M = 0.45  # free space narrower than 2x this does not seed a room
OPEN_BOUNDARY_M = 2.0  # wider than any doorway or open passage: longer contact = one space
MIN_LOW_CONF_AREA_M2 = 0.3
LOW_CONF_MAX_DEPTH_M = 1.0  # a low-confidence zone reaches at most this past its room
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
    """Cells whose points span at least WALL_MIN_EXTENT_M of height: walls, not tabletops.

    Counter fronts are also tall enough, so a tall cell is dropped when it stops at counter
    height right next to a counter top. The rule uses the counter's shape, not a minimum
    wall height: walls scanned only up to chest height must survive.
    """
    h = points[:, 2] - floor_z
    band = (h > WALL_BAND_M[0]) & (h < WALL_BAND_M[1])
    ij = grid.cells(points[band, :2])
    k = ((h[band] - WALL_BAND_M[0]) / WALL_SLICE_M).astype(int)
    n_slices = int(np.ceil((WALL_BAND_M[1] - WALL_BAND_M[0]) / WALL_SLICE_M))
    occupied = np.zeros((*grid.shape, n_slices), bool)
    occupied[ij[:, 0], ij[:, 1], k] = True
    tall = occupied.sum(axis=2) >= round(WALL_MIN_EXTENT_M / WALL_SLICE_M)
    top = n_slices - 1 - np.argmax(occupied[:, :, ::-1], axis=2)  # highest occupied slice
    low_top = top < round((COUNTER_FRONT_MAX_TOP_M - WALL_BAND_M[0]) / WALL_SLICE_M)
    front = tall & low_top & ndi.binary_dilation(_counter_tops(h, points, grid), iterations=3)
    return tall & ~front


def _counter_tops(h: np.ndarray, points: np.ndarray, grid: Grid) -> np.ndarray:
    """Cells with a surface at counter height and nothing visible below it."""
    top = np.zeros(grid.shape, bool)
    hollow = np.ones(grid.shape, bool)
    ij = grid.cells(points[(h > COUNTER_TOP_M[0]) & (h < COUNTER_TOP_M[1]), :2])
    top[ij[:, 0], ij[:, 1]] = True
    ij = grid.cells(points[(h > COUNTER_HOLLOW_M[0]) & (h < COUNTER_HOLLOW_M[1]), :2])
    hollow[ij[:, 0], ij[:, 1]] = False
    return top & hollow


def floor_mask(points: np.ndarray, grid: Grid, floor_z: float) -> np.ndarray:
    """Cells where the floor itself was seen (small gaps closed)."""
    h = points[:, 2] - floor_z
    ij = grid.cells(points[np.abs(h) < FLOOR_TOL_M, :2])
    seen = np.zeros(grid.shape, bool)
    seen[ij[:, 0], ij[:, 1]] = True
    return ndi.binary_closing(seen, iterations=3)


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


@dataclass
class Sightlines:
    """What each camera saw: free space lies between a camera and every point it saw."""

    cams: np.ndarray  # (V, 2) camera positions, world xy
    points: np.ndarray  # (M, 3) a sample of the points the cameras saw, world
    view: np.ndarray  # (M,) index of the camera that saw each point


SIGHT_STEPS = 64  # samples along each camera-to-point segment


def carved_mask(sight: Sightlines, grid: Grid, floor_z: float) -> np.ndarray:
    """Cells crossed by a line of sight to a point between floor and wall-top height.

    Sparse photos leave most of a room's floor unseen; the observed mask then depends on
    whether a one-cell gap happens to close (c_damage_01, 7 photos: 7.3 vs 11.1 m2 for the
    same cloud turned 180 deg). The space a camera looked across is free and observed
    whatever the grid: with carving, 10.9 vs 11.1 m2.
    """
    h = sight.points[:, 2] - floor_z
    keep = (h > -0.08) & (h < WALL_BAND_M[1])
    pts, view = sight.points[keep, :2], sight.view[keep]
    t = np.linspace(0.0, 1.0, SIGHT_STEPS)[:, None, None]
    seg = sight.cams[view][None] * (1 - t) + pts[None] * t
    ij = grid.cells(seg.reshape(-1, 2))
    ok = (ij[:, 0] >= 0) & (ij[:, 0] < grid.shape[0]) & (ij[:, 1] >= 0) & (ij[:, 1] < grid.shape[1])
    seen = np.zeros(grid.shape, bool)
    seen[ij[ok, 0], ij[ok, 1]] = True
    return seen


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
    walls: np.ndarray,
    observed: np.ndarray,
    res: float,
    lintels: np.ndarray | None = None,
    floor_seen: np.ndarray | None = None,
    enclosed_fraction: float = ENCLOSED_FRACTION,
) -> tuple[np.ndarray, np.ndarray]:
    """Label enclosed free space by room (0 = not a room), split at doorway constrictions
    and under door lintels. Also returns the low-confidence cells: seen floor that fails
    the enclosure test (a wall was never scanned) but borders a room."""
    near_wall = ndi.binary_dilation(walls)
    if lintels is not None:
        near_wall |= ndi.binary_dilation(lintels)
    open_space = observed & ~near_wall
    enclosed = enclosure(walls, res) >= enclosed_fraction  # lintels play no part here
    free = open_space & enclosed
    dist = ndi.distance_transform_edt(free) * res
    seeds, n = ndi.label(dist > DOOR_HALF_WIDTH_M)
    seed_area = ndi.sum(np.ones_like(dist), seeds, np.arange(1, n + 1)) * res**2
    seeds[~np.isin(seeds, np.flatnonzero(seed_area >= MIN_SEED_AREA_M2) + 1)] = 0
    labels = watershed(-dist, seeds, mask=free)
    area = np.bincount(labels.ravel()) * res**2
    labels[area[labels] < MIN_ROOM_AREA_M2] = 0
    candidates = open_space & ~enclosed
    if floor_seen is not None:
        candidates &= floor_seen
    labels, low = attach_unenclosed(labels, candidates, res)
    return merge_open_boundaries(labels, res), low  # after attaching: a zone can join rooms


def merge_open_boundaries(labels: np.ndarray, res: float) -> np.ndarray:
    """Merge rooms that touch along more than OPEN_BOUNDARY_M. Rooms never touch across a
    wall or lintel (those cells are not free), so a long contact is a watershed split of
    one open space; a doorway gives a contact no longer than its width."""
    contact: dict[tuple[int, int], int] = {}
    for a, b in ((labels[1:], labels[:-1]), (labels[:, 1:], labels[:, :-1])):
        touch = (a != b) & (a > 0) & (b > 0)
        for x, y in zip(a[touch], b[touch], strict=True):
            key = (min(x, y), max(x, y))
            contact[key] = contact.get(key, 0) + 1
    parent = np.arange(labels.max() + 1)

    def root(k: int) -> int:
        while parent[k] != k:
            k = parent[k]
        return k

    for (x, y), n in contact.items():
        if n * res > OPEN_BOUNDARY_M:
            parent[max(root(x), root(y))] = min(root(x), root(y))
    merged = np.array([root(k) for k in range(len(parent))])[labels]
    ids = np.unique(merged[merged > 0])
    renumber = np.zeros(len(parent), int)
    renumber[ids] = np.arange(1, len(ids) + 1)  # 1..n, 0 stays 0
    return renumber[merged]


def attach_unenclosed(
    labels: np.ndarray, unenclosed: np.ndarray, res: float
) -> tuple[np.ndarray, np.ndarray]:
    """Give each patch of observed-but-unenclosed floor within LOW_CONF_MAX_DEPTH_M of a
    room to the room it borders most, and mark it low confidence. Patches touching no room
    stay outside every room."""
    labels = labels.copy()
    low = np.zeros(labels.shape, bool)
    reach = ndi.distance_transform_edt(labels == 0) * res <= LOW_CONF_MAX_DEPTH_M
    patches, n = ndi.label(unenclosed & (labels == 0) & reach)
    for k in range(1, n + 1):
        patch = patches == k
        if patch.sum() * res**2 < MIN_LOW_CONF_AREA_M2:
            continue
        rim = labels[ndi.binary_dilation(patch) & ~patch]
        rim = rim[rim > 0]
        if rim.size:
            labels[patch] = np.bincount(rim).argmax()
            low |= patch
    return labels, low
