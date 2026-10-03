"""Pipeline output: one result type shared by every tier, written as JSON.

Every measured number is a `Measurement` carrying its confidence interval, so no value can
leave the pipeline without one. Plan coordinates are metres in a top-down frame (x, y): the
capture's world frame rotated about the vertical by -`plan_rotation_deg`, so that the
dominant walls run along x and y.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

FORMAT_VERSION = "0.1"
TIERS = ("lidar", "video", "photo")
OPENING_KINDS = ("door", "window", "passage")
SURFACE_KINDS = ("wall", "floor", "ceiling")

Point = tuple[float, float]


@dataclass
class Measurement:
    value: float
    lo: float
    hi: float
    unit: str

    def __post_init__(self):
        if not self.lo <= self.value <= self.hi:
            raise ValueError(f"value {self.value} outside interval [{self.lo}, {self.hi}]")


@dataclass
class Capture:
    id: str
    tier: str
    source: str
    device: str | None = None

    def __post_init__(self):
        if self.tier not in TIERS:
            raise ValueError(f"tier must be one of {TIERS}, got {self.tier!r}")


@dataclass
class Wall:
    id: str
    start: Point
    end: Point
    length: Measurement
    height: Measurement | None = None
    observed: bool = True  # False: no wall surface seen (open side), position inferred


@dataclass
class Opening:
    id: str
    wall_id: str
    kind: str
    width: Measurement
    height: Measurement | None = None
    connects_to: str | None = None  # room id on the other side, if any

    def __post_init__(self):
        if self.kind not in OPENING_KINDS:
            raise ValueError(f"kind must be one of {OPENING_KINDS}, got {self.kind!r}")


@dataclass
class Room:
    id: str
    label: str
    polygon: list[Point]
    floor_area: Measurement
    ceiling_height: Measurement | None = None  # None when the ceiling was never captured
    walls: list[Wall] = field(default_factory=list)
    openings: list[Opening] = field(default_factory=list)


@dataclass
class Adjacency:
    room_a: str
    room_b: str
    opening_id: str | None = None


@dataclass
class Surface:
    id: str
    room_id: str
    kind: str
    area: Measurement
    wall_id: str | None = None  # set when kind == "wall"

    def __post_init__(self):
        if self.kind not in SURFACE_KINDS:
            raise ValueError(f"kind must be one of {SURFACE_KINDS}, got {self.kind!r}")


@dataclass
class Damage:
    id: str
    surface_id: str
    damage_class: str
    score: float  # detector confidence, 0..1
    region: tuple[float, float, float, float]  # u0, v0, u1, v1 in metres on the surface
    area: Measurement


@dataclass
class Flag:
    """Concealed-damage flag; `rule_id` and `rule` name the rule that fired."""

    id: str
    rule_id: str
    rule: str
    surface_id: str
    damage_ids: list[str] = field(default_factory=list)


@dataclass
class ScopeItem:
    id: str
    surface_id: str
    action: str
    quantity: Measurement
    reason_ids: list[str] = field(default_factory=list)  # damage / flag ids


@dataclass
class Result:
    capture: Capture
    rooms: list[Room]
    adjacency: list[Adjacency] = field(default_factory=list)
    surfaces: list[Surface] = field(default_factory=list)
    damage: list[Damage] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    scope: list[ScopeItem] = field(default_factory=list)
    footprint_area: Measurement | None = None
    plan_rotation_deg: float | None = None
    drift_correction: str | None = None
    interval_coverage: float = 0.9
    timing_s: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        """Return broken cross-references (empty when the result is consistent)."""
        errors = []
        rooms = {r.id: r for r in self.rooms}
        surfaces = {s.id for s in self.surfaces}
        for room in self.rooms:
            walls = {w.id for w in room.walls}
            for o in room.openings:
                if o.wall_id not in walls:
                    errors.append(f"opening {o.id}: wall {o.wall_id} is not in room {room.id}")
        for a in self.adjacency:
            for rid in (a.room_a, a.room_b):
                if rid not in rooms:
                    errors.append(f"adjacency {a.room_a}-{a.room_b}: unknown room {rid}")
        for s in self.surfaces:
            if s.room_id not in rooms:
                errors.append(f"surface {s.id}: unknown room {s.room_id}")
        for kind, items in (("damage", self.damage), ("flag", self.flags), ("scope", self.scope)):
            for item in items:
                if item.surface_id not in surfaces:
                    errors.append(f"{kind} {item.id}: unknown surface {item.surface_id}")
        return errors

    def to_dict(self) -> dict:
        """JSON-native dict (tuples become lists), identical to what `write_json` stores."""
        return json.loads(json.dumps({"format_version": FORMAT_VERSION, **asdict(self)}))


def write_json(result: Result, path: Path | str) -> Path:
    """Validate and write `result` as JSON; refuse to write an inconsistent result."""
    errors = result.validate()
    if errors:
        raise ValueError("invalid result: " + "; ".join(errors))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2))
    return path
