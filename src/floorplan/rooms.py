"""One room's geometry: rectilinear outline snapped to the measured wall surfaces.

Works in plan coordinates (see plan2d). A room's outline comes from its free-space mask,
which stops a cell or two short of the walls; each edge is then moved onto the wall
surface measured from the points behind it, and the wall's sigma is that surface's spread.

Where the room's ceiling was captured, a wall is measured only above furniture and door
heads (UPPER_WALL_M up to just under the ceiling), at the median of its points: pose drift
smears a wall into a band 10-40 cm thick, and the free-space edge stops at the band's inner
side (fix declaration, docs/fix_declaration.md). Elsewhere the nearest face is taken.
"""

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import distance_transform_edt
from skimage.measure import approximate_polygon, find_contours

from floorplan.levels import Level, ceiling_level, floor_level
from floorplan.plan2d import WALL_BAND_M, Grid

MIN_EDGE_M = 0.25  # outline steps shorter than this are noise, not walls
SIMPLIFY_CELLS = 2.0
SEARCH_IN_M, SEARCH_OUT_M = 0.15, 0.4  # wall-surface search window around an edge
CORNER_TRIM_M = 0.1  # ignore points this close to the edge's corners
FACE_MIN_FRACTION = 0.3
FACE_BIN_M = 0.01
MIN_FACE_POINTS = 100
UPPER_WALL_M = 2.3  # above door heads (~2.0 m) and wardrobes / wall cabinets: only wall
CEILING_CLEAR_M = 0.3  # stay clear of the ceiling and cornices
UPPER_OUT_M = 0.5  # how far behind the free-space edge a smeared wall can reach
SNAPPED_STEP_M = 0.1  # steps this short left after snapping (e.g. a notch closed) go
UNSUPPORTED_SIGMA_M = 0.05  # edge with no wall behind it (open side, cut by segmentation)


@dataclass
class Edge:
    axis: int  # 0: the line u = coord (runs along v); 1: the line v = coord (runs along u)
    coord: float
    weight: float = 0.0  # outline length merged into this edge, for weighted merging
    sigma: float = UNSUPPORTED_SIGMA_M
    supported: bool = False
    length: float = 0.0


@dataclass
class RoomShape:
    polygon: np.ndarray  # (n, 2) plan coords, counter-clockwise; vertex k starts edge k
    edges: list[Edge]
    area: float = 0.0
    floor: Level | None = None
    ceiling: Level | None = None


def rectilinear_outline(mask: np.ndarray, grid: Grid, min_edge: float = MIN_EDGE_M) -> RoomShape:
    """Outline of the mask's largest region as an axis-aligned polygon."""
    contours = find_contours(np.pad(mask, 1).astype(float), 0.5)
    contour = max(contours, key=len) - 1  # undo the padding
    pts = approximate_polygon(contour, SIMPLIFY_CELLS)[:-1]
    pts = grid.origin + (pts + 0.5) * grid.res

    edges = []
    for p, q in zip(pts, np.roll(pts, -1, axis=0), strict=True):
        d = np.abs(q - p)
        axis = 0 if d[0] <= d[1] else 1
        edges.append(Edge(axis, (p[axis] + q[axis]) / 2, weight=float(np.hypot(*d))))
    edges = _merge_parallel(edges)
    return _shape(_drop_steps(edges, min_edge))


def _drop_steps(edges: list[Edge], min_edge: float) -> list[Edge]:
    """Remove edges shorter than min_edge (shortest first), merging their neighbours."""
    while len(edges) > 4:
        lengths = _edge_lengths(edges)
        k = int(np.argmin(lengths))
        if lengths[k] >= min_edge:
            break
        del edges[k]
        edges = _merge_parallel(edges)
    return edges


def measure_room(
    mask: np.ndarray,
    points: np.ndarray,
    grid: Grid,
    walls: np.ndarray,
    floor_z: float,
    labels: np.ndarray | None = None,
) -> RoomShape:
    """Outline snapped to wall surfaces, plus the room's own floor and ceiling levels.

    labels (all rooms): points nearer another room's floor than this room's are that
    room's side of an interior wall, and are not used to place this room's walls high up.
    """
    shape = rectilinear_outline(mask, grid)
    h = points[:, 2] - floor_z
    ij = grid.cells(points[:, :2])
    z = points[mask[ij[:, 0], ij[:, 1]], 2]
    floor = ceiling = None
    if len(z):
        floor = floor_level(z)
        ceiling = ceiling_level(z, floor.z)

    on_wall = walls[ij[:, 0], ij[:, 1]] & (h > WALL_BAND_M[0]) & (h < WALL_BAND_M[1])
    wall_uv = grid.to_plan(points[on_wall, :2])
    upper_uv = np.empty((0, 2))
    if floor and ceiling:
        hr = points[:, 2] - floor.z
        upper = (hr > UPPER_WALL_M) & (hr < ceiling.z - floor.z - CEILING_CLEAR_M)
        if labels is not None and (others := (labels > 0) & ~mask).any():
            own = distance_transform_edt(~mask) <= distance_transform_edt(~others)
            upper &= own[ij[:, 0], ij[:, 1]]
        upper_uv = grid.to_plan(points[upper, :2])
    n = len(shape.edges)
    for k, edge in enumerate(shape.edges):
        p, q = shape.polygon[k], shape.polygon[(k + 1) % n]
        if not _centre_of_wall(edge, p, q, upper_uv):
            _snap_to_surface(edge, p, q, wall_uv)
    shape = _shape(_drop_steps(shape.edges, SNAPPED_STEP_M))
    shape.floor, shape.ceiling = floor, ceiling
    return shape


def _behind(edge: Edge, p: np.ndarray, q: np.ndarray, uv: np.ndarray, out_m: float):
    """Signed outward offsets of the points behind an edge (corners trimmed), and the
    outward direction along the edge's axis."""
    along = 1 - edge.axis
    lo, hi = sorted((p[along], q[along]))
    # counter-clockwise polygon: outward normal is the edge direction turned clockwise
    direction = np.sign(q[along] - p[along])
    outward = direction if edge.axis == 0 else -direction
    offset = (uv[:, edge.axis] - edge.coord) * outward
    near = (
        (uv[:, along] > lo + CORNER_TRIM_M)
        & (uv[:, along] < hi - CORNER_TRIM_M)
        & (offset > -SEARCH_IN_M)
        & (offset < out_m)
    )
    return offset[near], outward


def _centre_of_wall(edge: Edge, p: np.ndarray, q: np.ndarray, upper_uv: np.ndarray) -> bool:
    """Edge onto the median of the wall points above furniture; False if too few."""
    d, outward = _behind(edge, p, q, upper_uv, UPPER_OUT_M)
    if len(d) < MIN_FACE_POINTS:
        return False
    med = float(np.median(d))
    edge.coord += outward * med
    edge.sigma = max(float(1.4826 * np.median(np.abs(d - med))), 1e-3)
    edge.supported = True
    return True


def _snap_to_surface(edge: Edge, p: np.ndarray, q: np.ndarray, wall_uv: np.ndarray) -> None:
    """Edge onto the nearest wall face (used where the wall was not seen high up)."""
    d, outward = _behind(edge, p, q, wall_uv, SEARCH_OUT_M)
    if len(d) < MIN_FACE_POINTS:
        return
    counts, bins = np.histogram(d, bins=np.arange(-SEARCH_IN_M, SEARCH_OUT_M, FACE_BIN_M))
    counts = np.convolve(counts, np.ones(3) / 3, mode="same")
    first = np.flatnonzero(counts >= FACE_MIN_FRACTION * counts.max())[0]
    face = d[np.abs(d - (bins[first] + FACE_BIN_M / 2)) < 0.025]
    med = float(np.median(face))
    edge.coord += outward * med
    edge.sigma = max(float(1.4826 * np.median(np.abs(face - med))), 1e-3)
    edge.supported = True


def signed_area(poly: np.ndarray) -> float:
    """Shoelace area; positive when the polygon is counter-clockwise."""
    nxt = np.roll(poly, -1, axis=0)
    return float(0.5 * (poly[:, 0] * nxt[:, 1] - nxt[:, 0] * poly[:, 1]).sum())


def _merge_parallel(edges: list[Edge]) -> list[Edge]:
    """Merge neighbouring edges on the same axis (cyclically) into length-weighted ones."""
    merged = list(edges)
    changed = True
    while changed and len(merged) > 1:
        changed = False
        for k in range(len(merged)):
            a, b = merged[k], merged[(k + 1) % len(merged)]
            if a.axis == b.axis:
                w = a.weight + b.weight
                a.coord = (a.coord * a.weight + b.coord * b.weight) / w if w else a.coord
                a.weight = w
                del merged[(k + 1) % len(merged)]
                changed = True
                break
    return merged


def _vertices(edges: list[Edge]) -> np.ndarray:
    """Vertex k is where edge k-1 meets edge k."""
    out = []
    for prev, edge in zip(np.roll(np.array(edges, dtype=object), 1), edges, strict=True):
        v = np.zeros(2)
        v[prev.axis], v[edge.axis] = prev.coord, edge.coord
        out.append(v)
    return np.array(out)


def _edge_lengths(edges: list[Edge]) -> np.ndarray:
    v = _vertices(edges)
    return np.linalg.norm(np.roll(v, -1, axis=0) - v, axis=1)


def _shape(edges: list[Edge]) -> RoomShape:
    poly = _vertices(edges)
    signed = signed_area(poly)
    if signed < 0:  # make counter-clockwise; vertex k must still start edge k
        edges = edges[::-1]
        edges = edges[1:] + edges[:1]
        poly = _vertices(edges)
    for edge, length in zip(edges, _edge_lengths(edges), strict=True):
        edge.length = float(length)
    return RoomShape(poly, edges, area=float(abs(signed)))
