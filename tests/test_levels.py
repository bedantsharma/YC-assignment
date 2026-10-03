import numpy as np

from floorplan.levels import ceiling_level, floor_level

rng = np.random.default_rng(0)


def _plane(z, n, noise=0.005):
    return z + rng.normal(0, noise, n)


def test_floor_is_lowest_dense_level_not_the_biggest():
    # tabletops hold more points than the floor here, but the floor is still the floor
    clutter = rng.uniform(-1.4, 1.2, 50_000)
    z = np.concatenate([_plane(-1.40, 20_000), _plane(-0.65, 40_000), clutter])
    level = floor_level(z)
    assert abs(level.z - (-1.40)) < 0.003
    assert 0.002 < level.spread < 0.01


def test_floor_ignores_a_few_stray_points_below_it():
    z = np.concatenate([_plane(0.0, 20_000), rng.uniform(-0.6, -0.1, 300)])
    assert abs(floor_level(z).z) < 0.003


def test_ceiling_is_highest_dense_level_at_least_2m_above_floor():
    z = np.concatenate([_plane(0.0, 20_000), _plane(1.9, 8_000), _plane(2.71, 3_000)])
    level = ceiling_level(z, floor_z=0.0)
    assert abs(level.z - 2.71) < 0.003


def test_no_ceiling_when_it_was_never_scanned():
    z = np.concatenate([_plane(0.0, 20_000), rng.uniform(0.0, 1.8, 20_000)])
    assert ceiling_level(z, floor_z=0.0) is None
