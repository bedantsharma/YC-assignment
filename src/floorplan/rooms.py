"""One room's geometry: rectilinear outline snapped to the measured wall surfaces.

Works in plan coordinates (see plan2d). A room's outline comes from its free-space mask,
which stops a cell or two short of the walls; each edge is then moved onto the wall
surface measured from the points behind it, and the wall's sigma is that surface's spread.
"""

from dataclasses import dataclass

import numpy as np
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
    while len(edges) > 4:
        lengths = _edge_lengths(edges)
        k = int(np.argmin(lengths))
        if lengths[k] >= min_edge:
            break
        del edges[k]
        edges = _merge_parallel(edges)
    return _shape(edges)


def measure_room(
    mask: np.ndarray, points: np.ndarray, grid: Grid, walls: np.ndarray, floor_z: float
) -> RoomShape:
    """Outline snapped to wall surfaces, plus the room's own floor and ceiling levels."""
    shape = rectilinear_outline(mask, grid)
    h = points[:, 2] - floor_z
    ij = grid.cells(points[:, :2])
    on_wall = walls[ij[:, 0], ij[:, 1]] & (h > WALL_BAND_M[0]) & (h < WALL_BAND_M[1])
    wall_uv = grid.to_plan(points[on_wall, :2])
    for k, edge in enumerate(shape.edges):
        _snap_to_surface(edge, shape.polygon[k], shape.polygon[(k + 1) % len(shape.edges)], wall_uv)
    shape = _shape(shape.edges)

    z = points[mask[ij[:, 0], ij[:, 1]], 2]
    if len(z):
        shape.floor = floor_level(z)
        shape.ceiling = ceiling_level(z, shape.floor.z)
    return shape


def _snap_to_surface(edge: Edge, p: np.ndarray, q: np.ndarray, wall_uv: np.ndarray) -> None:
    along = 1 - edge.axis
    lo, hi = sorted((p[along], q[along]))
    # counter-clockwise polygon: outward normal is the edge direction turned clockwise
    direction = np.sign(q[along] - p[along])
    outward = direction if edge.axis == 0 else -direction
    offset = (wall_uv[:, edge.axis] - edge.coord) * outward
    near = (
        (wall_uv[:, along] > lo + CORNER_TRIM_M)
        & (wall_uv[:, along] < hi - CORNER_TRIM_M)
        & (offset > -SEARCH_IN_M)
        & (offset < SEARCH_OUT_M)
    )
    d = offset[near]
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
