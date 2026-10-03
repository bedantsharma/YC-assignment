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


def test_ceiling_ignores_ripples_on_the_ceiling_peaks_upper_tail():
    # c_damage_02: a broad ceiling peak at 3.35 m whose upper tail has small local maxima
    tail = np.concatenate([_plane(z, n, 0.012) for z, n in [(3.40, 5_000), (3.445, 3_500)]])
    ripple = _plane(3.48, 1_800, 0.008)
    z = np.concatenate([_plane(0.0, 20_000), _plane(3.35, 15_000, 0.012), tail, ripple])
    assert abs(ceiling_level(z, floor_z=0.0).z - 3.35) < 0.01


def test_ceiling_keeps_a_separate_higher_plane():
    # a dense shelf top at 2.2 m and a thinner, clearly separate ceiling above it
    z = np.concatenate([_plane(0.0, 20_000), _plane(2.2, 9_000), _plane(2.8, 2_000)])
    assert abs(ceiling_level(z, floor_z=0.0).z - 2.8) < 0.003
