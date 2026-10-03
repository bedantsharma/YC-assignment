import numpy as np
import pytest

from floorplan.lidar import build_plan
from floorplan.output import Capture, Result
from floorplan.render import render_plan
from tests.synthetic import two_rooms


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
