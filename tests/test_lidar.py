import numpy as np
import pytest

from floorplan.lidar import build_plan
from floorplan.output import Capture, Result
from floorplan.render import render_plan
from tests.synthetic import kitchen, two_rooms


@pytest.fixture(scope="module")
def plan():
    return build_plan(two_rooms(angle_deg=30.0, ceiling=2.5))


def _contains(m, truth):
    return m.lo <= truth <= m.hi


def test_rooms_carry_intervals_that_contain_the_truth(plan):
    rooms = sorted(plan.rooms, key=lambda r: r.floor_area.value)
    assert [r.id for r in plan.rooms] == ["r1", "r2"]
    assert _contains(rooms[1].floor_area, 3.95 * 3)
    assert _contains(rooms[0].floor_area, 2.95 * 3)
    for room in rooms:
        assert room.ceiling_height.value == pytest.approx(2.5, abs=0.005)
        assert _contains(room.ceiling_height, 2.5)
        lengths = sorted(w.length.value for w in room.walls)
        assert lengths[-1] - lengths[0] < 1.0  # both rooms are near-square or 3 x 3.95


def test_wall_ids_follow_the_room_and_endpoints_close_the_polygon(plan):
    room = plan.rooms[0]
    assert [w.id for w in room.walls] == [f"{room.id}.w{k}" for k in range(1, len(room.walls) + 1)]
    for wall, corner in zip(room.walls, room.polygon, strict=True):
        assert wall.start == pytest.approx(corner)
    assert room.walls[-1].end == pytest.approx(room.polygon[0])


def test_footprint_is_the_sum_of_room_areas(plan):
    total = sum(r.floor_area.value for r in plan.rooms)
    assert plan.footprint_area.value == pytest.approx(total)


def test_degenerate_cloud_gives_no_rooms_and_a_warning():
    flat = np.column_stack([np.random.default_rng(0).uniform(0, 3, (5000, 2)), np.zeros(5000)])
    plan = build_plan(flat)
    assert plan.rooms == []
    assert any("no rooms" in w for w in plan.warnings)


def test_render_writes_a_png(plan, tmp_path):
    result = Result(Capture("synthetic", "lidar", "test"), plan.rooms)
    path = render_plan(result, tmp_path / "plan.png")
    assert path.read_bytes()[:4] == b"\x89PNG"


def test_kitchen_is_measured_to_the_wall_behind_the_counter():
    plan = build_plan(kitchen())
    assert len(plan.rooms) == 1
    room = plan.rooms[0]
    assert room.floor_area.value == pytest.approx(4.0 * 3.0, rel=0.03)
    assert max(w.length.value for w in room.walls) == pytest.approx(4.0, abs=0.03)


def test_rooms_joined_by_a_wide_door_under_a_lintel_stay_separate():
    plan = build_plan(two_rooms(angle_deg=30.0, door=(0.9, 2.1), lintel=2.0))
    areas = sorted(r.floor_area.value for r in plan.rooms)
    assert areas == pytest.approx([2.95 * 3, 3.95 * 3], rel=0.05)


def test_a_room_with_an_unscanned_wall_keeps_its_floor_flagged_low_confidence():
    pts = two_rooms(angle_deg=0.0)
    gap = (pts[:, 0] < 0.05) & (pts[:, 1] > 0.5) & (pts[:, 1] < 2.5)
    plan = build_plan(pts[~gap])  # 2 m of room A's west wall never scanned
    assert len(plan.rooms) == 2
    room_a = max(plan.rooms, key=lambda r: r.floor_area.value)
    assert room_a.floor_area.lo <= 3.95 * 3 <= room_a.floor_area.hi
    assert any(w.startswith(f"{room_a.id}:") and "low confidence" in w for w in plan.warnings)
    assert room_a.low_confidence_area.value > 0.3
    assert all(r.low_confidence_area is None for r in plan.rooms if r is not room_a)
