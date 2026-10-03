"""Chunked reconstruction: a long video in overlapping windows, chained into one frame.

One model pass over the whole home does not work: 30 frames of a 166 s walk find one room
of four (docs/model_research.md), and more frames in one pass run out of memory. So the
frames are split into overlapping windows (e.g. 30 frames, 10 shared with the previous
window). Each window is reconstructed on its own. The shared frames have a dense point map
in both windows, pixel for pixel, which gives thousands of correspondences: a trimmed
similarity fit (scale, rotation, translation) maps each window onto the previous one, so
every window ends up in the first window's frame and scale.

RGB only: the fit uses the model's own outputs, never the recording's poses or depth.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from floorplan.mvs import Reconstruction

FIT_SAMPLES = 20000  # correspondences used per fit (random subset of the shared pixels)
TRIM_ROUNDS = 3
TRIM_KEEP = 0.8  # keep the best 80% of residuals each round


@dataclass
class Link:
    window: int
    scale: float
    residual_m: float  # median distance of the kept correspondences after the fit
    pairs: int


def windows(n: int, size: int, overlap: int) -> list[range]:
    """Index ranges covering 0..n-1; consecutive ranges share `overlap` indices."""
    if n <= size:
        return [range(n)]
    if not 0 < overlap < size:
        raise ValueError("overlap must be between 0 and the window size")
    step = size - overlap
    starts = list(range(0, n - size, step)) + [n - size]
    return [range(s, s + size) for s in starts]


def umeyama(src: np.ndarray, dst: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """s, R, t minimising |dst - (s R src + t)|."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    a, b = src - mu_s, dst - mu_d
    u, d, vt = np.linalg.svd(b.T @ a / len(src))
    sign = np.eye(3)
    sign[2, 2] = np.sign(np.linalg.det(u @ vt))
    r = u @ sign @ vt
    s = float(np.trace(np.diag(d) @ sign) / a.var(0).sum())
    return s, r, mu_d - s * r @ mu_s


def fit_similarity(
    src: np.ndarray, dst: np.ndarray, seed: int = 0
) -> tuple[float, np.ndarray, np.ndarray, float, int]:
    """Trimmed similarity fit: robust to the pixels where the two windows disagree."""
    rng = np.random.default_rng(seed)
    if len(src) > FIT_SAMPLES:
        pick = rng.choice(len(src), FIT_SAMPLES, replace=False)
        src, dst = src[pick], dst[pick]
    keep = np.ones(len(src), bool)
    for _ in range(TRIM_ROUNDS + 1):
        s, r, t = umeyama(src[keep], dst[keep])
        err = np.linalg.norm(s * src @ r.T + t - dst, axis=1)
        keep = err <= np.quantile(err, TRIM_KEEP)
    return s, r, t, float(np.median(err[keep])), int(keep.sum())


def transform(rec: Reconstruction, s: float, r: np.ndarray, t: np.ndarray) -> Reconstruction:
    pts = s * rec.view_points @ r.T + t
    poses = rec.cam_poses.copy()
    poses[:, :3, :3] = r @ poses[:, :3, :3]
    poses[:, :3, 3] = s * poses[:, :3, 3] @ r.T + t
    return Reconstruction(pts, rec.view_keep, poses, rec.seconds, rec.model)


def chain(
    n: int,
    run: Callable[[list[int]], Reconstruction],
    size: int,
    overlap: int,
) -> tuple[Reconstruction, list[Link]]:
    """Reconstruct frames 0..n-1 window by window and chain them into one frame.

    `run(indices)` reconstructs the given frames. Shared frames keep the earlier window's
    points (already in the common frame); the later window adds only its new frames.
    """
    spans = windows(n, size, overlap)
    pts, keep, poses = {}, {}, {}  # frame index -> its arrays, in the first window's frame
    seconds, links, model = 0.0, [], ""
    for k, span in enumerate(spans):
        rec = run(list(span))
        seconds, model = seconds + rec.seconds, rec.model
        if k:
            src, dst = [], []
            for j, i in enumerate(span):
                if i in pts:
                    both = rec.view_keep[j] & keep[i]
                    src.append(rec.view_points[j][both])
                    dst.append(pts[i][both])
            src, dst = np.concatenate(src), np.concatenate(dst)
            s, r, t, res, m = fit_similarity(src, dst)
            rec = transform(rec, s, r, t)
            links.append(Link(k, s, res, m))
        for j, i in enumerate(span):
            if i not in pts:
                pts[i], keep[i], poses[i] = rec.view_points[j], rec.view_keep[j], rec.cam_poses[j]
    idx = sorted(pts)
    out = Reconstruction(
        np.stack([pts[i] for i in idx]),
        np.stack([keep[i] for i in idx]),
        np.stack([poses[i] for i in idx]),
        seconds,
        model,
    )
    return out, links
