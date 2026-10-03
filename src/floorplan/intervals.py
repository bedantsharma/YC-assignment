"""Tier-specific interval widening. Provisional until calibrated against ground truth.

The geometry backend's intervals come from surface spread only, which is right for LiDAR's
own noise but not for a reconstructed cloud. The video and photo tiers add, in quadrature
on each side: a relative scale error and an absolute surface error, both measured on
c_damage_01 in the model spike (docs/model_spike.md: scale 2-3% off ARKit, cloud 5-6 cm
median from LiDAR).
"""

import math
from dataclasses import replace

from floorplan.output import Measurement, Room

Z90 = 1.645
VIDEO_SCALE_REL = 0.03
VIDEO_SURFACE_M = 0.05


def widen(m: Measurement, rel: float, abs_sigma: float) -> Measurement:
    extra = Z90 * math.hypot(rel * m.value, abs_sigma)
    lo, hi = m.value - m.lo, m.hi - m.value
    return replace(
        m,
        lo=round(m.value - math.hypot(lo, extra), 4),
        hi=round(m.value + math.hypot(hi, extra), 4),
    )


def widen_room(room: Room, rel: float, surface_m: float) -> Room:
    """Walls and ceiling: scale + surface terms. Area: twice the relative scale term, plus
    each wall moving by the surface error (sigma_A = surface * sqrt(sum L^2))."""
    for wall in room.walls:
        wall.length = widen(wall.length, rel, surface_m)
    if room.ceiling_height:
        room.ceiling_height = widen(room.ceiling_height, rel, surface_m)
        for wall in room.walls:
            wall.height = room.ceiling_height
    area_abs = surface_m * math.sqrt(sum(w.length.value**2 for w in room.walls))
    room.floor_area = widen(room.floor_area, 2 * rel, area_abs)
    return room
