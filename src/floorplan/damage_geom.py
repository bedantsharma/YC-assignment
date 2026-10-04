"""Damage masks -> size and position on the measured surfaces (docs/damage_research.md §3).

For each detection: cast the camera ray through the mask's centre, find the first room
surface it hits (a wall's vertical plane within the wall's extent, the floor or the ceiling
inside the room), then cast a ray through every mask-outline pixel onto that plane. The
outline in surface coordinates gives the area (shoelace) and extent:

- wall: u = metres along the wall from its start corner, v = metres above the floor. Walls
  run counter-clockwise, so seen from inside the room u is measured from the right-hand
  corner;
- floor / ceiling: plan (x, y).

90% interval by Monte Carlo (MC_DRAWS draws per view): mask outline grown or shrunk by
U(-MASK_PX, MASK_PX) pixels, the plane moved along its normal by its own sigma, the camera
rotated by POSE_ROT_DEG and moved by POSE_T_M (1 sigma each), the floor by FLOOR_SIGMA_M.
One damage seen in several views is merged by surface, class and distance; its draws are
pooled, so the interval also covers the spread between views.

Plan frame (plan2d.Grid): world rotated about z by -angle. Poses: camera-to-world, z up,
OpenCV camera axes; intrinsics at the resolution of the image the detector saw.
"""

from dataclasses import dataclass, field

import numpy as np
from matplotlib.path import Path as MplPath
from skimage import measure, morphology

from floorplan.output import Room

MC_DRAWS = 300
MASK_PX = 2.0
POSE_ROT_DEG = 0.5
POSE_T_M = 0.02
FLOOR_SIGMA_M = 0.01
PLANE_SIGMA_DEFAULT_M = 0.02
WALL_TOL_M = 0.10  # a hit this far past a wall's end still counts as on that wall
NO_CEILING_M = 3.5  # walls' height when the ceiling was never seen
OUTLINE_POINTS = 96
MERGE_M = 0.25  # same class, same surface, centres closer than this (or overlapping): one
Z90 = 1.645


@dataclass
class View:
    image_id: str
    pose: np.ndarray  # (4, 4) camera-to-world, z up, OpenCV axes
    K: np.ndarray  # (3, 3) at the detector image's resolution
    size: tuple[int, int]  # (w, h) of the detector image


@dataclass
class SurfacePlane:
    surface_id: str
    room_id: str
    kind: str  # wall / floor / ceiling
    origin: np.ndarray  # plan-frame 3D point (wall: start corner at floor height)
    u_axis: np.ndarray
    v_axis: np.ndarray
    normal: np.ndarray
    u_range: tuple[float, float]
    v_range: tuple[float, float]
    sigma: float  # 1-sigma uncertainty of the plane's position along its normal
    polygon: np.ndarray | None = None  # floor / ceiling: room outline (plan x, y)
    wall_id: str | None = None


@dataclass
class Placed:
    """One detection placed on one surface, from one view."""

    image_id: str
    label: str
    score: float
    surface: SurfacePlane
    outline_uv: np.ndarray  # (N, 2) metres on the surface
    area: float  # m2
    area_draws: np.ndarray
    region: tuple[float, float, float, float]  # u0, v0, u1, v1
    centre: tuple[float, float]
    length: float | None = None  # cracks: skeleton length, m
    length_draws: np.ndarray | None = None
    px_size_m: float = 0.0  # one image pixel on the surface, metres
    note: str = ""
    distance_m: float = 0.0  # camera to the surface hit, along the centre ray


@dataclass
class Merged:
    label: str
    surface: SurfacePlane
    score: float
    area: tuple[float, float, float]  # value, lo, hi
    region: tuple[float, float, float, float]
    centre: tuple[float, float]
    views: list[str] = field(default_factory=list)
    length: tuple[float, float, float] | None = None
    width_m: float | None = None
    px_size_m: float = 0.0
    notes: list[str] = field(default_factory=list)


def surface_planes(rooms: list[Room], floor_z: float) -> list[SurfacePlane]:
    """Every wall, floor and ceiling of the rooms as planes in the plan frame (z up)."""
    out = []
    for room in rooms:
        height = room.ceiling_height.value if room.ceiling_height else NO_CEILING_M
        poly = np.asarray(room.polygon, float)
        for wall in room.walls:
            a, b = np.asarray(wall.start, float), np.asarray(wall.end, float)
            d = b - a
            length = float(np.linalg.norm(d))
            if length < 1e-6:
                continue
            u = np.array([d[0], d[1], 0.0]) / length
            n = np.array([-u[1], u[0], 0.0])  # left of the wall direction = into the room
            sigma = (wall.length.hi - wall.length.lo) / 2 / Z90 / np.sqrt(2)
            out.append(
                SurfacePlane(
                    f"{wall.id}.face",
                    room.id,
                    "wall",
                    np.array([a[0], a[1], floor_z]),
                    u,
                    np.array([0.0, 0.0, 1.0]),
                    n,
                    (0.0, length),
                    (0.0, height),
                    float(sigma) if sigma > 0 else PLANE_SIGMA_DEFAULT_M,
                    wall_id=wall.id,
                )
            )
        ex, ey = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
        out.append(
            SurfacePlane(
                f"{room.id}.floor",
                room.id,
                "floor",
                np.array([0, 0, floor_z]),
                ex,
                ey,
                np.array([0, 0, 1.0]),
                (-np.inf, np.inf),
                (-np.inf, np.inf),
                FLOOR_SIGMA_M,
                polygon=poly,
            )
        )
        if room.ceiling_height:
            sig = (room.ceiling_height.hi - room.ceiling_height.lo) / 2 / Z90
            out.append(
                SurfacePlane(
                    f"{room.id}.ceiling",
                    room.id,
                    "ceiling",
                    np.array([0, 0, floor_z + height]),
                    ex,
                    ey,
                    np.array([0, 0, -1.0]),
                    (-np.inf, np.inf),
                    (-np.inf, np.inf),
                    float(sig),
                    polygon=poly,
                )
            )
    return out


def to_plan_pose(pose: np.ndarray, angle_deg: float) -> np.ndarray:
    """Camera-to-world pose -> camera-to-plan pose (rotation about z by -angle)."""
    t = np.radians(angle_deg)
    c, s = np.cos(t), np.sin(t)
    rz = np.eye(4)
    rz[:2, :2] = [[c, s], [-s, c]]
    return rz @ pose


def rays(view: View, pose: np.ndarray, px: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Origin (3,) and unit directions (N, 3) in the pose's frame for pixel centres px."""
    hom = np.column_stack([px, np.ones(len(px))])
    d = (np.linalg.inv(view.K) @ hom.T).T @ pose[:3, :3].T
    return pose[:3, 3], d / np.linalg.norm(d, axis=1, keepdims=True)


def first_hit(
    planes: list[SurfacePlane], origin: np.ndarray, d: np.ndarray, room_id: str | None
) -> tuple[SurfacePlane, float] | None:
    """Nearest surface hit by one ray (only the camera's room when it is in one)."""
    best = None
    for pl in planes:
        if room_id is not None and pl.room_id != room_id:
            continue
        denom = float(d @ pl.normal)
        if abs(denom) < 1e-9:
            continue
        t = float((pl.origin - origin) @ pl.normal) / denom
        if t <= 0.05 or (best is not None and t >= best[1]):
            continue
        p = origin + t * d - pl.origin
        u, v = float(p @ pl.u_axis), float(p @ pl.v_axis)
        if pl.kind == "wall":
            ok = pl.u_range[0] - WALL_TOL_M <= u <= pl.u_range[1] + WALL_TOL_M
            ok &= pl.v_range[0] - WALL_TOL_M <= v <= pl.v_range[1] + WALL_TOL_M
        else:
            ok = MplPath(pl.polygon).contains_point((u, v), radius=WALL_TOL_M)
        if ok:
            best = (pl, t)
    return best


def room_of(rooms: list[Room], xy: np.ndarray) -> str | None:
    for room in rooms:
        if MplPath(np.asarray(room.polygon)).contains_point(tuple(xy)):
            return room.id
    return None


def mask_outline(mask: np.ndarray, n: int = OUTLINE_POINTS) -> np.ndarray:
    """Outer boundary of the largest part of a mask as (n, 2) pixel (x, y) points."""
    padded = np.pad(mask, 1)
    contours = measure.find_contours(padded.astype(float), 0.5)
    if not contours:
        return np.empty((0, 2))
    c = max(contours, key=len)[:, ::-1] - 1.0  # (row, col) -> (x, y), undo the pad
    idx = np.linspace(0, len(c) - 1, min(n, len(c))).astype(int)
    return c[idx] + 0.5  # pixel centres


def place(
    view: View,
    angle_deg: float,
    planes: list[SurfacePlane],
    rooms: list[Room],
    det,
    rng: np.random.Generator,
) -> Placed | None:
    """Put one detection (with a mask) on the surface it lies on, with Monte Carlo draws."""
    outline = mask_outline(det.mask)
    if len(outline) < 3:
        return None
    pose = to_plan_pose(view.pose, angle_deg)
    centre_px = _centroid(outline)
    origin, d = rays(view, pose, centre_px[None])
    hit = first_hit(planes, origin, d[0], room_of(rooms, origin[:2]))
    if hit is None:
        return None
    plane, dist = hit
    uv = _project(view, pose, plane, outline, 0.0)
    if uv is None:
        return None
    area = abs(_shoelace(uv))
    mask_px = float(det.mask.sum())
    px_size = float(np.sqrt(area / mask_px)) if mask_px > 0 else 0.0

    skel_px = 0.0
    if det.label == "crack":
        skel_px = float(morphology.skeletonize(det.mask).sum())
    r_eq = np.sqrt(max(mask_px, 1.0) / np.pi)

    areas, lengths = np.empty(MC_DRAWS), np.empty(MC_DRAWS)
    for k in range(MC_DRAWS):
        grow = rng.uniform(-MASK_PX, MASK_PX)
        pts = centre_px + (outline - centre_px) * max(0.05, 1.0 + grow / r_eq)
        p = _perturb(pose, rng)
        offset = rng.normal(0.0, plane.sigma)
        uvk = _project(view, p, plane, pts, offset)
        areas[k] = abs(_shoelace(uvk)) if uvk is not None else np.nan
        # crack length scales with the local pixel size, not the mask growth
        scale = np.sqrt(areas[k] / max(1.0, mask_px * max(0.05, 1 + grow / r_eq) ** 2))
        lengths[k] = skel_px * scale
    keep = np.isfinite(areas)
    u0, v0 = uv.min(axis=0)
    u1, v1 = uv.max(axis=0)
    c = _centroid(uv)
    return Placed(
        image_id=view.image_id,
        label=det.label,
        score=det.score,
        surface=plane,
        outline_uv=uv,
        area=area,
        area_draws=areas[keep],
        region=(float(u0), float(v0), float(u1), float(v1)),
        centre=(float(c[0]), float(c[1])),
        length=skel_px * px_size if det.label == "crack" else None,
        length_draws=lengths[keep] if det.label == "crack" else None,
        px_size_m=px_size,
        note=det.note,
        distance_m=dist,
    )


def merge(placed: list[Placed]) -> list[Merged]:
    """One entry per physical damage: same class, same surface, close or overlapping."""
    groups: list[list[Placed]] = []
    for p in sorted(placed, key=lambda q: -q.score):
        for g in groups:
            q = g[0]
            if q.label != p.label or q.surface.surface_id != p.surface.surface_id:
                continue
            gap = np.hypot(p.centre[0] - q.centre[0], p.centre[1] - q.centre[1])
            if gap < MERGE_M or _overlap(p.region, q.region):
                g.append(p)
                break
        else:
            groups.append([p])
    out = []
    for g in groups:
        draws = np.concatenate([p.area_draws for p in g])
        value = float(np.median([p.area for p in g]))
        lo, hi = np.percentile(draws, [5, 95]) if len(draws) else (value, value)
        length = width = None
        if g[0].label == "crack":
            ldraws = np.concatenate([p.length_draws for p in g])
            lv = float(np.median([p.length for p in g]))
            llo, lhi = np.percentile(ldraws, [5, 95])
            length = (lv, min(float(llo), lv), max(float(lhi), lv))
            width = value / lv if lv > 0 else None
        region = tuple(float(np.median([p.region[i] for p in g])) for i in range(4))
        centre = tuple(float(np.median([p.centre[i] for p in g])) for i in range(2))
        out.append(
            Merged(
                label=g[0].label,
                surface=g[0].surface,
                score=max(p.score for p in g),
                area=(value, min(float(lo), value), max(float(hi), value)),
                region=region,
                centre=centre,
                views=[p.image_id for p in g],
                length=length,
                width_m=width,
                px_size_m=float(np.median([p.px_size_m for p in g])),
                notes=sorted({p.note for p in g if p.note}),
            )
        )
    return out


def _project(
    view: View, pose: np.ndarray, plane: SurfacePlane, px: np.ndarray, offset: float
) -> np.ndarray | None:
    origin, d = rays(view, pose, px)
    o = plane.origin + offset * plane.normal
    denom = d @ plane.normal
    if np.any(np.abs(denom) < 1e-9):
        return None
    t = ((o - origin) @ plane.normal) / denom
    if np.any(t <= 0):
        return None
    p = origin + t[:, None] * d - plane.origin
    return np.column_stack([p @ plane.u_axis, p @ plane.v_axis])


def _perturb(pose: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    from scipy.spatial.transform import Rotation

    out = pose.copy()
    rot = Rotation.from_rotvec(np.radians(rng.normal(0, POSE_ROT_DEG, 3))).as_matrix()
    out[:3, :3] = pose[:3, :3] @ rot
    out[:3, 3] = pose[:3, 3] + rng.normal(0, POSE_T_M, 3)
    return out


def _shoelace(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _centroid(p: np.ndarray) -> np.ndarray:
    a = _shoelace(p)
    if abs(a) < 1e-12:
        return p.mean(axis=0)
    x, y = p[:, 0], p[:, 1]
    cross = x * np.roll(y, -1) - np.roll(x, -1) * y
    return np.array(
        [((x + np.roll(x, -1)) * cross).sum(), ((y + np.roll(y, -1)) * cross).sum()]
    ) / (6 * a)


def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
