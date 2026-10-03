import json

import pytest

from floorplan.output import (
    Adjacency,
    Capture,
    Damage,
    Flag,
    Measurement,
    Opening,
    Result,
    Room,
    ScopeItem,
    Surface,
    Wall,
    write_json,
)


def m(value, spread=0.01, unit="m"):
    return Measurement(value, value - spread, value + spread, unit)


def small_result() -> Result:
    """Two rooms joined by a door, one damaged wall with a flag and a scope line."""
    wall = Wall("r1.w1", start=(0.0, 0.0), end=(3.0, 0.0), length=m(3.0), height=m(2.5))
    door = Opening("r1.o1", wall_id="r1.w1", kind="door", width=m(0.8), connects_to="r2")
    room1 = Room(
        "r1",
        label="bedroom",
        polygon=[(0.0, 0.0), (3.0, 0.0), (3.0, 4.0), (0.0, 4.0)],
        floor_area=m(12.0, 0.1, "m2"),
        ceiling_height=m(2.5),
        walls=[wall],
        openings=[door],
    )
    room2 = Room(
        "r2",
        label="hallway",
        polygon=[(0.0, -1.0), (3.0, -1.0), (3.0, 0.0), (0.0, 0.0)],
        floor_area=m(3.0, 0.1, "m2"),
        ceiling_height=m(2.5),
    )
    surface = Surface("s1", room_id="r1", kind="wall", wall_id="r1.w1", area=m(7.5, 0.1, "m2"))
    damage = Damage(
        "d1",
        surface_id="s1",
        damage_class="water_stain",
        score=0.82,
        region=(0.4, 1.8, 0.9, 2.3),
        area=m(0.25, 0.02, "m2"),
    )
    flag = Flag(
        "f1",
        rule_id="R1",
        rule="stain within 0.5 m of the ceiling suggests a leak above",
        surface_id="s1",
        damage_ids=["d1"],
    )
    scope = ScopeItem(
        "sc1",
        surface_id="s1",
        action="treat stain and repaint wall",
        quantity=m(7.5, 0.1, "m2"),
        reason_ids=["d1", "f1"],
    )
    return Result(
        capture=Capture("cap1", tier="lidar", source="data/raw/cap1"),
        rooms=[room1, room2],
        adjacency=[Adjacency("r1", "r2", opening_id="r1.o1")],
        surfaces=[surface],
        damage=[damage],
        flags=[flag],
        scope=[scope],
    )


def test_measurement_rejects_value_outside_interval():
    with pytest.raises(ValueError, match="interval"):
        Measurement(3.0, 3.1, 3.2, "m")


def test_measurement_serialises_value_interval_and_unit():
    assert small_result().to_dict()["rooms"][0]["ceiling_height"] == {
        "value": 2.5,
        "lo": 2.49,
        "hi": 2.51,
        "unit": "m",
    }


def test_capture_rejects_unknown_tier():
    with pytest.raises(ValueError, match="tier"):
        Capture("cap1", tier="radar", source="x")


def test_opening_rejects_unknown_kind():
    with pytest.raises(ValueError, match="kind"):
        Opening("o1", wall_id="w1", kind="skylight", width=m(0.8))


def test_valid_result_has_no_reference_errors():
    assert small_result().validate() == []


def test_validate_reports_scope_item_on_unknown_surface():
    result = small_result()
    result.scope[0].surface_id = "s404"
    assert result.validate() == ["scope sc1: unknown surface s404"]


def test_validate_reports_opening_on_wall_of_another_room():
    result = small_result()
    result.rooms[0].openings[0].wall_id = "r2.w9"
    assert result.validate() == ["opening r1.o1: wall r2.w9 is not in room r1"]


def test_validate_reports_adjacency_to_unknown_room():
    result = small_result()
    result.adjacency[0].room_b = "r9"
    assert result.validate() == ["adjacency r1-r9: unknown room r9"]


def test_write_json_round_trips_and_records_format_version(tmp_path):
    path = write_json(small_result(), tmp_path / "out" / "plan.json")
    data = json.loads(path.read_text())
    assert data["format_version"] == "0.1"
    assert data["capture"]["tier"] == "lidar"
    assert data == small_result().to_dict()


def test_write_json_refuses_result_with_reference_errors(tmp_path):
    result = small_result()
    result.damage[0].surface_id = "s404"
    with pytest.raises(ValueError, match="unknown surface s404"):
        write_json(result, tmp_path / "plan.json")
