import numpy as np
import pytest

from floorplan.plan2d import (
    Grid,
    dominant_angle,
    make_grid,
    observed_mask,
    segment_rooms,
    wall_mask,
)
from floorplan.rooms import measure_room, rectilinear_outline, signed_area
from tests.synthetic import smeared_room, two_rooms

RES = 0.03


def test_outline_of_an_l_shaped_mask_has_six_axis_aligned_edges():
    grid = Grid(0.0, np.zeros(2), 0.1, (60, 60))
    mask = np.zeros(grid.shape, bool)
    mask[10:50, 10:30] = True  # 4 m x 2 m
    mask[10:30, 30:50] = True  # plus 2 m x 2 m -> L shape
    mask[25, 30:33] = False  # a nick smaller than min_edge must not create edges
    shape = rectilinear_outline(mask, grid)
    assert len(shape.edges) == 6
    assert signed_area(shape.polygon) == pytest.approx(12.0, abs=0.3)


@pytest.fixture(scope="module")
def measured():
    pts = two_rooms(angle_deg=30.0, ceiling=2.5)
    grid = make_grid(pts, dominant_angle(pts), RES)
    walls = wall_mask(pts, grid, floor_z=0.0)
    labels, _ = segment_rooms(walls, observed_mask(pts, grid, floor_z=0.0), RES)
    rooms = [measure_room(labels == k, pts, grid, walls, floor_z=0.0) for k in (1, 2)]
    return sorted(rooms, key=lambda r: r.area)


def test_walls_snap_to_the_wall_surfaces(measured):
    small, big = measured
    assert sorted(e.length for e in small.edges) == pytest.approx([2.95, 2.95, 3, 3], abs=0.01)
    assert sorted(e.length for e in big.edges) == pytest.approx([3, 3, 3.95, 3.95], abs=0.01)
    assert big.area == pytest.approx(3.95 * 3, abs=0.05)
    assert all(e.supported for e in big.edges)
    assert all(0 < e.sigma < 0.02 for e in big.edges)


def test_room_floor_and_ceiling(measured):
    room = measured[1]
    assert room.floor.z == pytest.approx(0.0, abs=0.003)
    assert room.ceiling.z - room.floor.z == pytest.approx(2.5, abs=0.005)


def _rooms(pts):
    grid = make_grid(pts, dominant_angle(pts), RES)
    walls = wall_mask(pts, grid, floor_z=0.0)
    labels, _ = segment_rooms(walls, observed_mask(pts, grid, floor_z=0.0), RES)
    return [
        measure_room(labels == k, pts, grid, walls, 0.0, labels) for k in range(1, labels.max() + 1)
    ]


def test_a_smeared_wall_is_measured_at_its_middle_and_furniture_is_not_a_wall():
    (room,) = _rooms(smeared_room())
    short, long_ = sorted(np.ptp(room.polygon, axis=0))
    assert long_ == pytest.approx(4.0, abs=0.03)  # middle of the 3.9 / 4.0 / 4.1 copies
    assert short == pytest.approx(3.0, abs=0.03)  # behind the wardrobe, not its front (2.6)
    assert len(room.edges) == 4  # the wardrobe's notch closes
    assert max(e.sigma for e in room.edges) > 0.05  # a smeared wall gets a wide interval


def test_the_far_face_of_an_interior_wall_belongs_to_the_neighbour():
    rooms = sorted(_rooms(two_rooms(angle_deg=0.0, ceiling=3.0)), key=lambda r: r.area)
    small, big = rooms
    assert sorted(np.ptp(big.polygon, axis=0)) == pytest.approx([3, 3.95], abs=0.02)
    assert sorted(np.ptp(small.polygon, axis=0)) == pytest.approx([2.95, 3], abs=0.02)
