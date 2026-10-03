import numpy as np
import pytest

from floorplan.intervals import correct_scale, widen, widen_room
from floorplan.output import Measurement
from floorplan.video import estimate_up, z_up
from tests.synthetic import two_rooms


def _tilt(deg_x, deg_y):
    ax, ay = np.radians(deg_x), np.radians(deg_y)
    rx = np.array([[1, 0, 0], [0, np.cos(ax), -np.sin(ax)], [0, np.sin(ax), np.cos(ax)]])
    ry = np.array([[np.cos(ay), 0, np.sin(ay)], [0, 1, 0], [-np.sin(ay), 0, np.cos(ay)]])
    return ry @ rx


def test_z_up_maps_the_up_vector_to_z():
    up = np.array([0.3, -0.2, 0.93])
    up /= np.linalg.norm(up)
    assert z_up(up[None], up)[0] == pytest.approx([0, 0, 1], abs=1e-9)


def test_estimate_up_finds_the_vertical_of_a_tilted_room_from_rough_cameras():
    rot = _tilt(6.0, -4.0)  # the reconstruction's frame is tilted against gravity
    pts = two_rooms(angle_deg=20.0) @ rot.T
    true_up = rot @ [0, 0, 1]
    # cameras held roughly level: image-up (-y) within ~10 deg of true up, but biased
    cams = np.repeat(np.eye(4)[None], 5, axis=0)
    cams[:, :3, 1] = -(rot @ _tilt(8.0, 3.0) @ [0, 0, 1])
    up = estimate_up(pts, cams)
    assert np.degrees(np.arccos(up @ true_up)) < 0.5


def test_widen_adds_scale_and_surface_terms_in_quadrature():
    m = widen(Measurement(4.0, 3.95, 4.05, "m"), rel=0.03, abs_sigma=0.05)
    extra = 1.645 * np.hypot(0.12, 0.05)
    assert m.hi - m.value == pytest.approx(np.hypot(0.05, extra), abs=1e-4)
    assert m.value - m.lo == pytest.approx(np.hypot(0.05, extra), abs=1e-4)


def test_photo_scale_bias_is_its_own():
    pts = np.array([[0.964, 0.0, 0.930]])
    assert np.allclose(correct_scale(pts, "pi3x", "photo"), [[1.0, 0.0, 1.0]])


def test_correct_scale_divides_out_horizontal_and_vertical_bias():
    pts = np.array([[0.964, -1.928, 0.914], [0.0, 0.0, 2.742]])
    out = correct_scale(pts, "pi3x")
    assert np.allclose(out, [[1.0, -2.0, 1.0], [0.0, 0.0, 3.0]])


def test_widen_room_uses_vertical_error_for_ceiling_only():
    from floorplan.output import Room, Wall

    def m(v):
        return Measurement(v, v, v, "m")

    walls = [Wall(f"w{i}", (0, 0), (1, 0), m(4.0), m(3.0), True) for i in range(4)]
    room = Room("r1", "r1", [], Measurement(16.0, 16.0, 16.0, "m2"), m(3.0), walls)
    widen_room(room, rel_h=0.05, rel_v=0.0, surface_m=0.0)
    assert room.walls[0].length.hi - 4.0 == pytest.approx(1.645 * 0.05 * 4.0, abs=1e-4)
    assert room.ceiling_height.hi == pytest.approx(3.0)
    assert room.floor_area.hi - 16.0 == pytest.approx(1.645 * 0.10 * 16.0, abs=1e-3)
