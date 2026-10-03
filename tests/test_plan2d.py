import numpy as np
import pytest

from floorplan.plan2d import (
    attach_unenclosed,
    dominant_angle,
    enclosure,
    lintel_mask,
    make_grid,
    merge_open_boundaries,
    observed_mask,
    segment_rooms,
    wall_mask,
)
from tests.synthetic import kitchen, two_rooms

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


def test_wall_mask_drops_a_counter_front_but_keeps_the_wall_behind_it():
    pts = kitchen()
    grid = make_grid(pts, dominant_angle(pts), RES)
    walls = wall_mask(pts, grid, floor_z=0.0)
    front = grid.cells(np.array([[3.4, 1.5]]))[0]
    behind = grid.cells(np.array([[4.0, 1.5]]))[0]
    assert not walls[tuple(front)]
    assert walls[tuple(behind)]


def test_wall_mask_keeps_a_wall_scanned_only_up_to_chest_height():
    pts = two_rooms(angle_deg=30.0)
    low = pts[pts[:, 2] < 1.3]  # the phone never pointed above 1.3 m
    grid = make_grid(low, dominant_angle(low), RES)
    walls = wall_mask(low, grid, floor_z=0.0)
    shared = grid.cells(_rot(np.array([[3.95, 0.5]]), 30.0))[0]
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
    labels, _ = segment_rooms(walls, observed_mask(pts, grid, floor_z=0.0), RES)
    areas = sorted(np.bincount(labels.ravel())[1:] * RES**2)
    assert len(areas) == 2
    # free space stops a cell or two short of each wall, so areas run slightly small
    assert areas[0] == pytest.approx(9.0, rel=0.1)
    assert areas[1] == pytest.approx(12.0, rel=0.1)


def _rot(xy, deg):
    t = np.radians(deg)
    return xy @ np.array([[np.cos(t), np.sin(t)], [-np.sin(t), np.cos(t)]])


def test_segment_rooms_splits_at_a_wide_door_under_a_lintel():
    pts = two_rooms(angle_deg=30.0, door=(0.9, 2.1), lintel=2.0)  # 1.2 m wide
    grid = make_grid(pts, dominant_angle(pts), RES)
    walls = wall_mask(pts, grid, floor_z=0.0)
    labels, _ = segment_rooms(
        walls, observed_mask(pts, grid, floor_z=0.0), RES, lintel_mask(pts, grid, floor_z=0.0)
    )
    assert labels.max() == 2


def test_rooms_touching_along_a_long_open_boundary_merge():
    labels = np.zeros((100, 100), int)
    labels[:, :50], labels[:, 50:] = 1, 2  # 3 m of contact, no wall
    merged = merge_open_boundaries(labels, RES)
    assert merged.max() == 1


def test_rooms_meeting_only_in_a_doorway_stay_separate():
    labels = np.zeros((100, 100), int)  # a wall (label 0) at columns 49-50
    labels[:, :49], labels[:, 51:] = 1, 2
    labels[40:60, 49], labels[40:60, 50] = 1, 2  # they touch only in a 0.6 m doorway
    assert merge_open_boundaries(labels, RES).max() == 2


def test_unenclosed_floor_bordering_a_room_is_attached_as_low_confidence():
    labels = np.zeros((100, 100), int)
    labels[:, :50] = 1
    unenclosed = np.zeros_like(labels, bool)
    unenclosed[:, 50:70] = True  # borders room 1
    unenclosed[:, 80:] = True  # touches no room
    out, low = attach_unenclosed(labels, unenclosed, RES)
    assert (out[:, 50:70] == 1).all() and low[:, 50:70].all()
    assert (out[:, 80:] == 0).all() and not low[:, 80:].any()
    assert not low[:, :50].any()


def test_low_confidence_zone_reaches_at_most_one_metre_past_the_room():
    labels = np.zeros((100, 200), int)
    labels[:, :50] = 1
    unenclosed = np.zeros_like(labels, bool)
    unenclosed[:, 50:150] = True  # 3 m of floor beyond the room's last enclosed cell
    out, low = attach_unenclosed(labels, unenclosed, RES)
    depth = low.any(axis=0).sum() * RES
    assert depth == pytest.approx(1.0, abs=2 * RES)
    assert (out[:, 100:] == 0).all()
