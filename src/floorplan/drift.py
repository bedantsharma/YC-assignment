"""Drift correction: re-align the capture's poses chunk by chunk on the walls.

ARKit poses drift slowly, so a wall seen early and again late lands in two places and its
face thickens. The frames are cut into time chunks; each chunk's wall points (top-down)
are registered to the chunks before it with trimmed 2D ICP (yaw about the vertical plus a
horizontal shift). Corrections are small by construction (|yaw| < 3 deg, shift < 0.3 m),
rejected when the chunk overlaps the map too little, and interpolated per frame so poses
don't jump at chunk boundaries. Height (z) is left alone: the floor fixes it.
"""

import dataclasses
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from floorplan.capture import LidarCapture
from floorplan.cloud import fuse, voxel_downsample
from floorplan.levels import floor_level
from floorplan.plan2d import WALL_BAND_M

METHOD = "chunked 2D ICP on wall points (yaw + shift per chunk, interpolated per frame)"
CHUNK_FRAMES = 150
VOXEL_M = 0.04
INLIER_M = 0.10  # ICP pairs farther apart than this are ignored (trimmed ICP)
MIN_OVERLAP = 0.5  # share of a chunk's wall points that must find a partner in the map
MIN_CONSTRAINT = 0.15  # weaker wall-normal direction's share: below it the fit can slide
NORMAL_NEIGHBOURS = 8
MAX_YAW_DEG = 3.0
MAX_SHIFT_M = 0.3
ICP_ITERATIONS = 20


@dataclass
class Correction:
    frame: int  # chunk centre (frame index)
    yaw_deg: float
    shift: tuple[float, float]
    overlap: float
    accepted: bool


def register_2d(
    src: np.ndarray, dst: np.ndarray, iterations: int = ICP_ITERATIONS
) -> tuple[float, np.ndarray, float, float]:
    """Rotation (rad) and shift moving 2D points src onto dst, plus the overlap and how
    well the matched walls pin the shift down in their weaker direction (0..0.5).

    Constraint: eigenvalues of the summed n n^T of the matched map points' wall normals.
    One straight wall pins only its normal direction (constraint 0): the fit can slide
    along it, so such a correction is not trustworthy.
    """
    tree = cKDTree(dst)
    theta, t = 0.0, np.zeros(2)
    overlap, j, ok = 0.0, None, None
    for _ in range(iterations):
        c, s = np.cos(theta), np.sin(theta)
        moved = src @ np.array([[c, -s], [s, c]]).T + t
        d, j = tree.query(moved, distance_upper_bound=INLIER_M)
        ok = np.isfinite(d)
        overlap = float(ok.mean())
        if ok.sum() < 10:
            return 0.0, np.zeros(2), overlap, 0.0
        a, b = src[ok], dst[j[ok]]
        mu_a, mu_b = a.mean(0), b.mean(0)
        h = (a - mu_a).T @ (b - mu_b)
        theta = float(np.arctan2(h[0, 1] - h[1, 0], h[0, 0] + h[1, 1]))
        c, s = np.cos(theta), np.sin(theta)
        t = mu_b - np.array([[c, -s], [s, c]]) @ mu_a
    return theta, t, overlap, _constraint(dst, np.unique(j[ok]), tree)


def _constraint(dst: np.ndarray, idx: np.ndarray, tree: cKDTree) -> float:
    _, nb = tree.query(dst[idx], k=NORMAL_NEIGHBOURS)
    local = dst[nb] - dst[nb].mean(axis=1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", local, local)
    _, vecs = np.linalg.eigh(cov)
    normals = vecs[:, :, 0]  # smallest-variance direction = wall normal
    h = normals.T @ normals
    ev = np.linalg.eigvalsh(h)
    return float(ev[0] / ev.sum())


def correct_drift(cap: LidarCapture) -> tuple[LidarCapture, list[Correction]]:
    n = len(cap.depth_paths)
    bounds = list(range(0, n, CHUNK_FRAMES)) + [n]
    if len(bounds) < 3:
        return cap, []  # one chunk: nothing to align against
    chunks = [_part(cap, a, b) for a, b in zip(bounds[:-1], bounds[1:], strict=True)]
    clouds = [fuse(c, voxel=VOXEL_M) for c in chunks]
    floor = floor_level(np.concatenate(clouds)[:, 2]).z

    def walls_2d(p: np.ndarray) -> np.ndarray:
        h = p[:, 2] - floor
        return p[(h > WALL_BAND_M[0]) & (h < WALL_BAND_M[1]), :2]

    corrections = [Correction((bounds[0] + bounds[1]) // 2, 0.0, (0.0, 0.0), 1.0, True)]
    world_map = walls_2d(clouds[0])
    for k in range(1, len(chunks)):
        src = walls_2d(clouds[k])
        centre = (bounds[k] + bounds[k + 1]) // 2
        if len(src) < 100 or len(world_map) < 100:
            corrections.append(Correction(centre, 0.0, (0.0, 0.0), 0.0, False))
            continue
        theta, t, overlap, constraint = register_2d(src, world_map)
        ok = (
            overlap >= MIN_OVERLAP
            and constraint >= MIN_CONSTRAINT
            and abs(np.degrees(theta)) < MAX_YAW_DEG
            and np.linalg.norm(t) < MAX_SHIFT_M
        )
        if not ok:
            theta, t = 0.0, np.zeros(2)
        corrections.append(Correction(centre, float(np.degrees(theta)), tuple(t), overlap, ok))
        c, s = np.cos(theta), np.sin(theta)
        moved = src @ np.array([[c, -s], [s, c]]).T + t
        world_map = _thin_2d(np.concatenate([world_map, moved]))

    return dataclasses.replace(cap, poses=_apply(cap.poses, corrections)), corrections


def _thin_2d(xy: np.ndarray) -> np.ndarray:
    return voxel_downsample(np.column_stack([xy, np.zeros(len(xy))]), VOXEL_M)[:, :2]


def _part(cap: LidarCapture, a: int, b: int) -> LidarCapture:
    return dataclasses.replace(
        cap,
        depth_paths=cap.depth_paths[a:b],
        confidence_paths=cap.confidence_paths[a:b],
        poses=cap.poses[a:b],
        intrinsics=cap.intrinsics[a:b],
    )


def _apply(poses: np.ndarray, corrections: list[Correction]) -> np.ndarray:
    """Left-multiply each pose by the per-frame interpolated correction."""
    frames = np.arange(len(poses))
    at = [c.frame for c in corrections]
    yaw = np.radians(np.interp(frames, at, [c.yaw_deg for c in corrections]))
    tx = np.interp(frames, at, [c.shift[0] for c in corrections])
    ty = np.interp(frames, at, [c.shift[1] for c in corrections])
    out = poses.copy()
    for i in frames:
        c, s = np.cos(yaw[i]), np.sin(yaw[i])
        m = np.eye(4)
        m[:2, :2] = [[c, -s], [s, c]]
        m[:2, 3] = tx[i], ty[i]
        out[i] = m @ poses[i]
    return out
