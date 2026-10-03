import numpy as np
import pytest

from floorplan.plan2d import (
    dominant_angle,
    enclosure,
    make_grid,
    observed_mask,
    segment_rooms,
    wall_mask,
)
from tests.synthetic import two_rooms

RES = 0.03


@pytest.fixture(scope="module")
def apartment():
    pts = two_rooms(angle_deg=30.0)
    grid = make_grid(pts, dominant_angle(pts), RES)
    return pts, grid


def test_dominant_angle_recovers_wall_orientation():
    assert dominant_angle(two_rooms(angle_deg=30.0)) == pytest.approx(30.0, abs=0.2)
    assert dominant_angle(two_rooms(angle_deg=-20.0)) == pytest.approx(70.0, abs=0.2)


def test_grid_rotation_makes_walls_axis_aligned(apartment):
    pts, grid = apartment
    uv = grid.to_plan(pts[:, :2])
    # the west wall (x = 0 before rotation) is now a vertical line in plan coordinates
    assert np.percentile(uv[:, 0], 1) == pytest.approx(uv[:, 0].min(), abs=0.02)
    assert uv[:, 0].max() - uv[:, 0].min() == pytest.approx(9.0, abs=0.05)


def test_wall_mask_keeps_walls_and_drops_the_table(apartment):
    pts, grid = apartment
    walls = wall_mask(pts, grid, floor_z=0.0)
    table = grid.cells(_rot(np.array([[1.6, 1.4]]), 30.0))[0]
    shared = grid.cells(_rot(np.array([[3.95, 0.5]]), 30.0))[0]
    assert not walls[tuple(table)]
    assert walls[tuple(shared)]


def test_enclosure_rejects_floor_seen_through_a_window(apartment):
    pts, grid = apartment
    walls = wall_mask(pts, grid, floor_z=0.0)
    enc = enclosure(walls, RES)
    inside = grid.cells(_rot(np.array([[2.0, 0.5]]), 30.0))[0]
    outside = grid.cells(_rot(np.array([[8.5, 1.5]]), 30.0))[0]
    assert enc[tuple(inside)] > 0.9
    assert enc[tuple(outside)] < 0.6


def test_segment_rooms_splits_at_the_door(apartment):
    pts, grid = apartment
    walls = wall_mask(pts, grid, floor_z=0.0)
    labels = segment_rooms(walls, observed_mask(pts, grid, floor_z=0.0), RES)
    areas = sorted(np.bincount(labels.ravel())[1:] * RES**2)
    assert len(areas) == 2
    # free space stops a cell or two short of each wall, so areas run slightly small
    assert areas[0] == pytest.approx(9.0, rel=0.1)
    assert areas[1] == pytest.approx(12.0, rel=0.1)


def _rot(xy, deg):
    t = np.radians(deg)
    return xy @ np.array([[np.cos(t), np.sin(t)], [-np.sin(t), np.cos(t)]])
