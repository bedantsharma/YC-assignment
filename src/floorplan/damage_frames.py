"""Which frames of a recording go to the damage detector (ROADMAP Phase 5, agreed Oct 4).

Evenly spaced frames can miss a small damage that only a few seconds of the walk look at.
Two signals replace them:

1. Pauses. The capture protocol asks the user to stop about 1 m from each damage and hold
   still. Two ways to see it, both for at least STILL_MIN_S:
   - still camera: translation under STILL_SPEED_MS and rotation under STILL_TURN_DEGS,
     smoothed over SMOOTH_S;
   - dwell: the point the image centre looks at stays within GAZE_SPREAD_M on a surface no
     further than DWELL_DIST_M. A hand drifting while looking at one spot is a look, not a
     walk (home C's recordings, made before the hold was asked for, have slow looks at the
     damage at 5-9 cm/s but no still holds).
   Each pause gives PAUSE_FRAMES frames. Door / window holds and the start / end holds of
   the protocol fire too; they only cost a few calls.
2. Coverage. We know every wall and ceiling plane and every frame's pose, so the walls are
   cut into patches (PATCH_M) and a frame "sees" a patch when the patch is in the image,
   no further than MAX_DIST_M, within MAX_ANGLE_DEG of face-on, and not hidden (the LiDAR
   depth there is not shorter than the patch). Greedy set cover then picks the fewest
   frames that see every patch NEED times. Patches no frame sees well are reported: that
   wall was never looked at closely enough to find small damage.

Pause frames come first; coverage frames fill the budget in the order the greedy picks them.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from matplotlib.path import Path as MplPath

from floorplan.damage_geom import SurfacePlane, first_hit

STILL_SPEED_MS = 0.06
STILL_TURN_DEGS = 6.0
SMOOTH_S = 0.5
STILL_MIN_S = 1.2
GAZE_SPREAD_M = 0.15  # the looked-at point stays within this of its median
DWELL_DIST_M = 2.0
GAZE_STEP = 3  # frames between gaze samples
PAUSE_FRAMES = 2  # per pause: frames at 1/3 and 2/3 of it
PATCH_M = 0.25
CEILING_PATCH_M = 0.5
MAX_DIST_M = 3.0  # f ~ 1340 px: a 6 cm hole is still ~27 px across at 3 m face-on
MAX_ANGLE_DEG = 60.0
OCCLUSION_M = 0.15
NEED = 2
CANDIDATE_S = 0.5  # coverage candidates: one frame every half second
MIN_GAP_FRAMES = 10  # chosen frames closer than this are the same view


@dataclass
class Selection:
    frames: list[int]  # in priority order: pauses, then coverage
    pauses: list[tuple[int, int]]  # (first, last) frame of each pause
    patches: int = 0
    seen_once: float = 0.0  # share of patches seen well by at least one chosen frame
    seen_need: float = 0.0  # ... by NEED chosen frames
    unseen: dict[str, float] = field(default_factory=dict)  # surface id -> share never seen


def still_segments(poses: np.ndarray, fps: float) -> list[tuple[int, int]]:
    """(first, last) frame index of each stretch where the camera is held still."""
    n = len(poses)
    if n < 3:
        return []
    step = np.linalg.norm(np.diff(poses[:, :3, 3], axis=0), axis=1) * fps
    rel = np.einsum("nji,njk->nik", poses[:-1, :3, :3], poses[1:, :3, :3])
    cos = np.clip((np.trace(rel, axis1=1, axis2=2) - 1) / 2, -1.0, 1.0)
    turn = np.degrees(np.arccos(cos)) * fps
    k = max(1, round(SMOOTH_S * fps))
    kernel = np.ones(k) / k
    speed = np.convolve(step, kernel, mode="same")
    turning = np.convolve(turn, kernel, mode="same")
    still = np.append((speed < STILL_SPEED_MS) & (turning < STILL_TURN_DEGS), False)
    out, start = [], None
    for i, s in enumerate(still):
        if s and start is None:
            start = i
        elif not s and start is not None:
            if (i - start) / fps >= STILL_MIN_S:
                out.append((start, i - 1))
            start = None
    return out


def dwell_segments(
    poses: np.ndarray, Ks: np.ndarray, size: tuple[int, int], planes: list[SurfacePlane], fps: float
) -> list[tuple[int, int]]:
    """(first, last) frame of each stretch where the image centre stays on one close spot."""
    w, h = size
    idx = np.arange(0, len(poses), GAZE_STEP)
    gaze = np.full((len(idx), 3), np.nan)
    for j, i in enumerate(idx):
        d = poses[i, :3, :3] @ (np.linalg.inv(Ks[i]) @ np.array([w / 2, h / 2, 1.0]))
        d /= np.linalg.norm(d)
        hit = first_hit(planes, poses[i, :3, 3], d, None)
        if hit is not None and hit[1] <= DWELL_DIST_M:
            gaze[j] = poses[i, :3, 3] + hit[1] * d
    win = max(2, int(np.ceil(STILL_MIN_S * fps / GAZE_STEP)))
    ok = np.zeros(len(idx), bool)  # sample j starts a dwelling window
    for j in range(len(idx) - win + 1):
        g = gaze[j : j + win]
        if np.isnan(g).any():
            continue
        if np.linalg.norm(g - np.median(g, axis=0), axis=1).max() <= GAZE_SPREAD_M:
            ok[j] = True
    out, start = [], None
    for j in range(len(idx) + 1):
        on = j < len(idx) and ok[j]
        if on and start is None:
            start = j
        elif not on and start is not None:
            out.append((int(idx[start]), int(idx[min(j - 1 + win - 1, len(idx) - 1)])))
            start = None
    return out


def _union(segs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for a, b in sorted(segs):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def patches(planes: list[SurfacePlane]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Centres (M, 3) and inward normals (M, 3) of wall and ceiling patches, and their
    surface ids. Floors are left out: furniture covers them and the protocol does not ask
    to inspect them closely."""
    pts, normals, ids = [], [], []
    for pl in planes:
        if pl.kind == "wall":
            us = np.arange(PATCH_M / 2, pl.u_range[1], PATCH_M)
            vs = np.arange(PATCH_M / 2, pl.v_range[1], PATCH_M)
            uu, vv = np.meshgrid(us, vs)
            uv = np.column_stack([uu.ravel(), vv.ravel()])
        elif pl.kind == "ceiling":
            lo, hi = pl.polygon.min(axis=0), pl.polygon.max(axis=0)
            xs = np.arange(lo[0] + CEILING_PATCH_M / 2, hi[0], CEILING_PATCH_M)
            ys = np.arange(lo[1] + CEILING_PATCH_M / 2, hi[1], CEILING_PATCH_M)
            xx, yy = np.meshgrid(xs, ys)
            uv = np.column_stack([xx.ravel(), yy.ravel()])
            uv = uv[MplPath(pl.polygon).contains_points(uv)] if len(uv) else uv
        else:
            continue
        if not len(uv):
            continue
        pts.append(pl.origin + uv[:, :1] * pl.u_axis + uv[:, 1:] * pl.v_axis)
        normals.append(np.repeat(pl.normal[None], len(uv), axis=0))
        ids += [pl.surface_id] * len(uv)
    if not pts:
        return np.empty((0, 3)), np.empty((0, 3)), []
    return np.concatenate(pts), np.concatenate(normals), ids


def sees(
    pose: np.ndarray,
    K: np.ndarray,
    size: tuple[int, int],
    pts: np.ndarray,
    normals: np.ndarray,
    depth: np.ndarray | None = None,
) -> np.ndarray:
    """Which patches one camera sees well. pose: camera-to-frame of pts; K at `size`;
    depth: LiDAR depth image (metres, any resolution of the same view) for occlusion."""
    R, t = pose[:3, :3], pose[:3, 3]
    d = pts - t
    dist = np.linalg.norm(d, axis=1)
    xc = d @ R  # camera coordinates (R is camera-to-frame)
    z = xc[:, 2]
    ok = (z > 0.1) & (dist <= MAX_DIST_M)
    ok &= -np.einsum("ij,ij->i", d, normals) / np.maximum(dist, 1e-9) >= np.cos(
        np.radians(MAX_ANGLE_DEG)
    )
    px = xc @ K.T
    u = px[:, 0] / np.where(z > 0, z, 1)
    v = px[:, 1] / np.where(z > 0, z, 1)
    w, h = size
    ok &= (u >= 0) & (u < w) & (v >= 0) & (v < h)
    if depth is not None and ok.any():
        sy, sx = depth.shape[0] / h, depth.shape[1] / w
        r = np.clip((v[ok] * sy).astype(int), 0, depth.shape[0] - 1)
        c = np.clip((u[ok] * sx).astype(int), 0, depth.shape[1] - 1)
        measured = depth[r, c]
        hidden = (measured > 0) & (measured < z[ok] - OCCLUSION_M)
        idx = np.flatnonzero(ok)
        ok[idx[hidden]] = False
    return ok


def select(
    poses: np.ndarray,
    K: np.ndarray,
    size: tuple[int, int],
    planes: list[SurfacePlane],
    fps: float,
    budget: int,
    depth_of: Callable[[int], np.ndarray | None] | None = None,
) -> Selection:
    """Frames for the detector: pause frames first, then greedy coverage, up to `budget`.
    poses: camera-to-plan (same frame as the planes); K (N, 3, 3) or (3, 3) at `size`."""
    n = len(poses)
    Ks = np.broadcast_to(K, (n, 3, 3)) if K.ndim == 2 else K
    pauses = _union(still_segments(poses, fps) + dwell_segments(poses, Ks, size, planes, fps))
    chosen: list[int] = []

    def add(i: int) -> bool:
        if len(chosen) >= budget or any(abs(i - j) < MIN_GAP_FRAMES for j in chosen):
            return False
        chosen.append(i)
        return True

    for a, b in pauses:
        for k in range(1, PAUSE_FRAMES + 1):
            add(int(round(a + (b - a) * k / (PAUSE_FRAMES + 1))))

    pts, normals, ids = patches(planes)
    sel = Selection([], pauses, patches=len(pts))
    if not len(pts):
        sel.frames = chosen
        return sel

    def seen(i: int) -> np.ndarray:
        return sees(poses[i], Ks[i], size, pts, normals, depth_of(i) if depth_of else None)

    step = max(1, round(CANDIDATE_S * fps))
    cands = list(range(0, n, step))
    vis = np.array([seen(i) for i in cands])
    count = np.zeros(len(pts), int)
    for i in chosen:  # pause frames count towards coverage too
        count += seen(i)
    used = np.zeros(len(cands), bool)
    while len(chosen) < budget:
        gain = (vis & (count < NEED)[None]).sum(axis=1)
        gain[used] = 0
        best = int(np.argmax(gain))
        if gain[best] == 0:
            break
        used[best] = True
        if add(cands[best]):
            count += vis[best]
    ever = vis.any(axis=0)
    sel.frames = chosen
    sel.seen_once = float((count >= 1).mean())
    sel.seen_need = float((count >= NEED).mean())
    ids_arr = np.array(ids)
    for sid in dict.fromkeys(ids):
        m = ids_arr == sid
        share = float((~ever[m]).mean())
        if share > 0:
            sel.unseen[sid] = round(share, 3)
    return sel


MIN_VIEWS = 2


def confirm(merged: list, cams: dict, size: tuple[int, int]) -> tuple[list, list, list]:
    """Two-view rule, judged against what the keyframes could see (agreed Oct 4).

    cams: image id -> (camera-to-plan pose, K at `size`, depth image or None). For each
    merged damage, count the keyframes that see its centre up close (`sees`). Reported in
    fewer than MIN_VIEWS images although MIN_VIEWS or more keyframes looked at that spot:
    the others contradict it, so it is dropped. Reported once and no other keyframe could
    see the spot: kept, but unconfirmed. Returns (kept, dropped, unconfirmed).
    """
    kept, dropped, unconfirmed = [], [], []
    for m in merged:
        pl = m.surface
        point = pl.origin + m.centre[0] * pl.u_axis + m.centre[1] * pl.v_axis
        looked = sum(
            bool(sees(pose, K, size, point[None], pl.normal[None], depth)[0])
            for pose, K, depth in cams.values()
        )
        seen = len(set(m.views))
        looked = max(looked, seen)  # a far-away view that reported it also looked
        if seen < MIN_VIEWS <= looked:
            dropped.append((m, looked))
        else:
            kept.append(m)
            if seen < MIN_VIEWS:
                unconfirmed.append(m)
    return kept, dropped, unconfirmed
