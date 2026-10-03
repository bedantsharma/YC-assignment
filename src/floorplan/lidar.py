"""Fused point cloud -> measured rooms with intervals. Shared by every tier's geometry.

Intervals: each number gets a 90% interval of +-1.645 sigma, where sigma comes from the
measured surfaces (wall-face spread, floor and ceiling plane spread). This is provisional:
the benchmark calibrates it against ground truth (ROADMAP Phase 6).
"""

from dataclasses import dataclass, field

import numpy as np

from floorplan.levels import floor_level
from floorplan.output import Measurement, Room, Wall
from floorplan.plan2d import (
    dominant_angle,
    lintel_mask,
    make_grid,
    observed_mask,
    segment_rooms,
    wall_mask,
)
from floorplan.rooms import RoomShape, measure_room

GRID_RES_M = 0.03
Z90 = 1.645
ANGLE_BAND_M = (0.3, 2.0)  # heights above floor used to find the wall orientation


@dataclass
class Plan:
    rooms: list[Room]
    footprint_area: Measurement | None
    rotation_deg: float | None
    floor_z: float | None
    warnings: list[str] = field(default_factory=list)


def build_plan(points: np.ndarray) -> Plan:
    floor = floor_level(points[:, 2])
    h = points[:, 2] - floor.z
    band = points[(h > ANGLE_BAND_M[0]) & (h < ANGLE_BAND_M[1])]
    if len(band) < 1000:
        return Plan([], None, None, floor.z, ["no rooms found: almost no wall points"])
    angle = dominant_angle(band)
    grid = make_grid(points, angle, GRID_RES_M)
    walls = wall_mask(points, grid, floor.z)
    observed = observed_mask(points, grid, floor.z)
    labels = segment_rooms(walls, observed, GRID_RES_M, lintel_mask(points, grid, floor.z))
    shapes = [
        measure_room(labels == k, points, grid, walls, floor.z) for k in range(1, labels.max() + 1)
    ]
    if not shapes:
        return Plan([], None, angle, floor.z, ["no rooms found: no enclosed free space"])

    rooms = [_room(f"r{k}", shape) for k, shape in enumerate(shapes, start=1)]
    warnings = [
        f"{r.id}: ceiling not captured, height unknown" for r in rooms if not r.ceiling_height
    ]
    total = sum(r.floor_area.value for r in rooms)
    sigma = np.sqrt(sum(((r.floor_area.hi - r.floor_area.value) / Z90) ** 2 for r in rooms))
    return Plan(rooms, _measure(total, sigma, "m2"), angle, floor.z, warnings)


def _room(room_id: str, shape: RoomShape) -> Room:
    n = len(shape.edges)
    ceiling = None
    if shape.ceiling and shape.floor:
        sigma = float(np.hypot(shape.floor.spread, shape.ceiling.spread))
        ceiling = _measure(shape.ceiling.z - shape.floor.z, sigma, "m")
    walls = []
    for k, edge in enumerate(shape.edges):
        # a wall's length is fixed by the two perpendicular walls at its ends
        sigma = float(np.hypot(shape.edges[k - 1].sigma, shape.edges[(k + 1) % n].sigma))
        walls.append(
            Wall(
                id=f"{room_id}.w{k + 1}",
                start=_point(shape.polygon[k]),
                end=_point(shape.polygon[(k + 1) % n]),
                length=_measure(edge.length, sigma, "m"),
                height=ceiling,
                observed=edge.supported,
            )
        )
    area_sigma = float(np.sqrt(sum((e.length * e.sigma) ** 2 for e in shape.edges)))
    return Room(
        id=room_id,
        label=room_id,
        polygon=[_point(p) for p in shape.polygon],
        floor_area=_measure(shape.area, area_sigma, "m2"),
        ceiling_height=ceiling,
        walls=walls,
    )


def _measure(value: float, sigma: float, unit: str) -> Measurement:
    value, half = float(value), Z90 * float(sigma)
    return Measurement(round(value, 4), round(value - half, 4), round(value + half, 4), unit)


def _point(p: np.ndarray) -> tuple[float, float]:
    return (round(float(p[0]), 4), round(float(p[1]), 4))
