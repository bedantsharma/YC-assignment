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
