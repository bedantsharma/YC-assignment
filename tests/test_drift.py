import numpy as np
import pytest

from floorplan.drift import Correction, _apply, register_2d


def _room_outline(step=0.02):
    """Top-down wall points of an L-shaped room (asymmetric, so ICP has a unique answer)."""
    corners = [(0, 0), (5, 0), (5, 3), (2, 3), (2, 4.5), (0, 4.5), (0, 0)]
    segs = []
    for a, b in zip(corners[:-1], corners[1:], strict=True):
        a, b = np.array(a, float), np.array(b, float)
        n = int(np.linalg.norm(b - a) / step)
        segs.append(a + np.outer(np.linspace(0, 1, n), b - a))
    return np.concatenate(segs)


def test_register_2d_recovers_a_small_yaw_and_shift():
    dst = _room_outline()
    theta, t = np.radians(1.5), np.array([0.06, -0.04])
    c, s = np.cos(theta), np.sin(theta)
    rot = np.array([[c, -s], [s, c]])
    src = (dst - t) @ rot  # inverse transform: src moved by (theta, t) gives dst
    src += np.random.default_rng(0).normal(0, 0.005, src.shape)
    got_theta, got_t, overlap, constraint = register_2d(src, dst)
    assert np.degrees(got_theta) == pytest.approx(1.5, abs=0.1)
    assert got_t == pytest.approx(t, abs=0.01)
    assert overlap > 0.9
    assert constraint > 0.3  # an L-shaped room pins both directions


def test_a_single_straight_wall_does_not_constrain_the_fit():
    wall = np.column_stack([np.arange(0, 4, 0.02), np.zeros(200)])
    *_, constraint = register_2d(wall + [0.3, 0.01], wall)
    assert constraint < 0.05


def test_corrections_are_interpolated_between_chunk_centres():
    poses = np.repeat(np.eye(4)[None], 101, axis=0)
    corr = [
        Correction(0, 0.0, (0.0, 0.0), 1.0, True),
        Correction(100, 0.0, (0.2, 0.0), 1.0, True),
    ]
    out = _apply(poses, corr)
    assert out[50, 0, 3] == pytest.approx(0.1)
    assert out[100, 0, 3] == pytest.approx(0.2)
    assert out[0, 0, 3] == 0.0
