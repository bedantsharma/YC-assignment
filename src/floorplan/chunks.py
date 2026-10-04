"""Chunked reconstruction: a long video in overlapping windows, chained into one frame.

One model pass over the whole home does not work: 30 frames of a 166 s walk find one room
of four (docs/model_research.md), and more frames in one pass run out of memory. So the
frames are split into overlapping windows (e.g. 30 frames, 10 shared with the previous
window). Each window is reconstructed on its own. The shared frames have a dense point map
in both windows, pixel for pixel, which gives thousands of correspondences: a trimmed
similarity fit (scale, rotation, translation) maps each window onto the previous one, so
every window ends up in the first window's frame and scale.

The two windows can disagree on where some shared frames sit relative to the others (shared
frames spanning a doorway: each frame matches to 1-2 cm on its own, but one window places
half of them metres away). One fit over all of them then averages two placements (home C,
scale 0.54 and 153 cm residual). So each shared frame's own fit is a candidate, the frames
that agree with the best candidate are kept, and the link is fitted on those only. This
runs only when the fit over all shared frames is clearly broken (JOINT_OK_M): on healthy
links, dropping frames loosens the rotation and moved the damage room's walls by 20 cm.

RGB only: the fit uses the model's own outputs, never the recording's poses or depth.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from floorplan.mvs import Reconstruction

FIT_SAMPLES = 20000  # correspondences used per fit (random subset of the shared pixels)
TRIM_ROUNDS = 3
TRIM_KEEP = 0.8  # keep the best 80% of residuals each round
JOINT_OK_M = 0.10  # fits over all shared frames: 1-7 cm when healthy, 25-153 cm when broken
AGREE_M = 0.05  # a shared frame agrees with a candidate fit if its median residual is below
MIN_FRAME_PIXELS = 200  # shared frames with fewer common pixels are not used


@dataclass
class Link:
    window: int
    scale: float
    residual_m: float  # median distance of the kept correspondences after the fit
    pairs: int
    frames: tuple[int, int] = (0, 0)  # shared frames that agreed with the fit, of all shared


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


def fit_shared(
    src: list[np.ndarray], dst: list[np.ndarray]
) -> tuple[float, np.ndarray, np.ndarray, float, int, tuple[int, int]]:
    """Fit over all shared frames, or, if that fit is broken, over the shared frames that
    agree with each other (one array pair per frame)."""
    s, r, t, res, m = fit_similarity(np.concatenate(src), np.concatenate(dst))
    if res <= JOINT_OK_M:
        return s, r, t, res, m, (len(src), len(src))
    pairs = [(a, b) for a, b in zip(src, dst, strict=True) if len(a) >= MIN_FRAME_PIXELS]
    if not pairs:  # too little overlap per frame: fall back to everything
        pairs = [(np.concatenate(src), np.concatenate(dst))]
    rng = np.random.default_rng(0)
    probe = [  # a few pixels per frame to test candidates
        (a[i], b[i])
        for a, b in pairs
        for i in [rng.choice(len(a), min(len(a), 2000), replace=False)]
    ]
    best: tuple[int, float, list[int]] = (-1, np.inf, [])
    for a, b in pairs:
        s, r, t, _, _ = fit_similarity(a, b)
        err = [np.median(np.linalg.norm(s * pa @ r.T + t - pb, axis=1)) for pa, pb in probe]
        agree = [k for k, e in enumerate(err) if e < AGREE_M]
        score = (len(agree), -float(np.median(err)))
        if score > (best[0], -best[1]):
            best = (len(agree), float(np.median(err)), agree)
    use = best[2] or list(range(len(pairs)))
    s, r, t, res, m = fit_similarity(
        np.concatenate([pairs[k][0] for k in use]), np.concatenate([pairs[k][1] for k in use])
    )
    return s, r, t, res, m, (len(use), len(src))


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
            s, r, t, res, m, used = fit_shared(src, dst)
            rec = transform(rec, s, r, t)
            links.append(Link(k, s, res, m, used))
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
