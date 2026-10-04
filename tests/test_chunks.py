import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from floorplan.chunks import chain, fit_similarity, windows
from floorplan.mvs import Reconstruction


def test_windows_cover_all_frames_with_overlap():
    spans = windows(90, 30, 10)
    assert spans[0] == range(0, 30) and spans[-1].stop == 90
    assert all(len(set(a) & set(b)) >= 10 for a, b in zip(spans, spans[1:], strict=False))
    assert windows(20, 30, 10) == [range(20)]
    with pytest.raises(ValueError):
        windows(90, 30, 30)


def test_fit_similarity_ignores_outliers():
    rng = np.random.default_rng(1)
    src = rng.uniform(-3, 3, (5000, 3))
    r = Rotation.from_euler("xyz", [10, -20, 35], degrees=True).as_matrix()
    dst = 1.07 * src @ r.T + [0.5, -1.0, 2.0]
    dst[:500] += rng.normal(0, 0.5, (500, 3))  # 10% of pixels disagree between windows
    s, r_fit, _, res, _ = fit_similarity(src, dst)
    assert s == pytest.approx(1.07, abs=0.002)
    assert np.allclose(r_fit, r, atol=1e-3)
    assert res < 1e-3


def test_chain_puts_every_window_in_the_first_windows_frame():
    rng = np.random.default_rng(2)
    n, h, w = 50, 6, 8
    truth = rng.uniform(-4, 4, (n, h, w, 3))  # each frame's pixels, in a common frame
    poses = np.tile(np.eye(4), (n, 1, 1))
    poses[:, :3, 3] = rng.uniform(-2, 2, (n, 3))

    def run(idx):
        # each window comes back in its own arbitrary frame and scale, like a model pass
        g = np.random.default_rng(idx[0])
        s = g.uniform(0.9, 1.1)
        r = Rotation.random(random_state=idx[0]).as_matrix()
        t = g.uniform(-5, 5, 3)
        p = poses[idx].copy()
        p[:, :3, :3] = r @ p[:, :3, :3]
        p[:, :3, 3] = s * p[:, :3, 3] @ r.T + t
        keep = np.ones((len(idx), h, w), bool)
        return Reconstruction(s * truth[idx] @ r.T + t, keep, p, 1.0, "fake")

    out, links = chain(n, run, size=20, overlap=6)
    ref = run(list(range(20)))  # window 0 defines the frame
    s0, r0, t0 = _similarity(truth[:20], ref.view_points)
    expected = s0 * truth @ r0.T + t0
    assert out.view_points.shape == truth.shape
    assert np.allclose(out.view_points, expected, atol=1e-6)
    assert len(links) == len(windows(n, 20, 6)) - 1
    assert out.seconds == pytest.approx(len(windows(n, 20, 6)))


def _similarity(src, dst):
    s, r, t, _, _ = fit_similarity(src.reshape(-1, 3), dst.reshape(-1, 3))
    return s, r, t


def test_chain_ignores_shared_frames_the_two_windows_place_differently():
    # Each shared frame matches pixel for pixel, but the later window puts the first 4 of
    # its 10 shared frames 3 m away (it misjudged where they sit, e.g. across a doorway).
    rng = np.random.default_rng(3)
    n, h, w = 50, 16, 16
    truth = rng.uniform(-4, 4, (n, h, w, 3))
    poses = np.tile(np.eye(4), (n, 1, 1))

    def run(idx):
        pts = truth[idx].copy()
        if idx[0] == 20:  # second window: its first 4 frames shifted
            pts[:4] += [3.0, 0.0, 0.0]
        keep = np.ones((len(idx), h, w), bool)
        return Reconstruction(0.8 * pts, keep, poses[idx].copy(), 1.0, "fake")

    out, links = chain(n, run, size=30, overlap=10)
    assert links[0].scale == pytest.approx(1.0, abs=1e-6)
    assert links[0].residual_m < 1e-6
    assert links[0].frames == (6, 10)
    assert np.allclose(out.view_points[30:], 0.8 * truth[30:], atol=1e-6)


def test_chain_without_shared_confident_pixels_says_so():
    def run(idx):
        keep = np.zeros((len(idx), 2, 2), bool) if idx[0] else np.ones((len(idx), 2, 2), bool)
        pts = np.zeros((len(idx), 2, 2, 3))
        return Reconstruction(pts, keep, np.tile(np.eye(4), (len(idx), 1, 1)), 0.0, "pi3x")

    with pytest.raises(RuntimeError, match="shares no confident pixels"):
        chain(8, run, 5, 2)
