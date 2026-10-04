"""Video-tier scale correction and interval widening. Provisional until ground truth.

Scale. Each model places surfaces consistently too near or too far, differently along the
floor and up the walls (docs/video_scale.md). SCALE_BIAS is video / LiDAR, measured on the
damage room only (c_damage_01 and c_damage_02); the cloud is divided by it. Checked for
Pi3X on the home's three other rooms, not used in the fit: ceiling error 5.6-9.1% -> within
3.3%; sqrt(area) mean error 5.4% -> 3.8% (kitchen still 8.5% short).

Intervals. The geometry backend's intervals come from surface spread only, which is right
for LiDAR's own noise but not for a reconstructed cloud. The video tier adds, in
quadrature on each side: the relative error left after correction (RESIDUAL_REL: Pi3X from
the held-out rooms; MapAnything has no held-out check, so wider) and an absolute surface
error (5-6 cm median cloud-to-LiDAR distance, docs/model_spike.md).
"""

import math
from dataclasses import replace

import numpy as np

from floorplan.output import Measurement, Room

Z90 = 1.645
# (horizontal, vertical), image / LiDAR, per (tier, model). Photo, Pi3X: vertical from six
# damage-room photo runs (ceilings 0.903-0.948, docs/photo_tier.md); horizontal as video.
# MapAnything photo: video values. Horizontal re-measured (Oct 4) against the LiDAR after
# its wall fix (docs/fix_declaration.md §6): the first values (0.964 / 0.935) were fitted
# to LiDAR walls that were 7-8% short. Horizontal varies by room (Pi3X 0.80-0.99).
SCALE_BIAS = {
    ("video", "pi3x"): (0.890, 0.914),
    ("video", "mapanything"): (0.877, 1.035),
    ("photo", "pi3x"): (0.890, 0.930),
    ("photo", "mapanything"): (0.877, 1.035),
}
# 1 sigma, per (tier, model). Photo: rooms with few photos come out small (coverage), so
# horizontal is wider; vertical from the corrected photo ceilings (0.95-1.02)
RESIDUAL_REL = {
    ("video", "pi3x"): (0.05, 0.02),
    ("video", "mapanything"): (0.06, 0.04),
    ("photo", "pi3x"): (0.14, 0.055),
    ("photo", "mapanything"): (0.14, 0.055),
}
# Photo values (Oct 4): the 90th percentile of the photo tier's relative error on home C's
# ground truth (22 room sides: 23%; 8 ceilings: 9%) divided by 1.645, so the 90% intervals
# cover what partial room coverage does; fitted on C itself (no held-out photo set yet).
# MapAnything photo: no data, given the same width.
VIDEO_SURFACE_M = 0.05


def correct_scale(points: np.ndarray, model: str, tier: str = "video") -> np.ndarray:
    """z-up cloud with the model's horizontal and vertical bias divided out."""
    h, v = SCALE_BIAS[(tier, model)]
    return points / np.array([h, h, v])


def widen(m: Measurement, rel: float, abs_sigma: float) -> Measurement:
    extra = Z90 * math.hypot(rel * m.value, abs_sigma)
    lo, hi = m.value - m.lo, m.hi - m.value
    return replace(
        m,
        lo=round(m.value - math.hypot(lo, extra), 4),
        hi=round(m.value + math.hypot(hi, extra), 4),
    )


def widen_room(room: Room, rel_h: float, rel_v: float, surface_m: float) -> Room:
    """Walls: horizontal + surface terms; ceiling: vertical + surface terms. Area: twice the
    horizontal term, plus each wall moving by the surface error (sigma = s * sqrt(sum L^2))."""
    for wall in room.walls:
        wall.length = widen(wall.length, rel_h, surface_m)
    if room.ceiling_height:
        room.ceiling_height = widen(room.ceiling_height, rel_v, surface_m)
        for wall in room.walls:
            wall.height = room.ceiling_height
    area_abs = surface_m * math.sqrt(sum(w.length.value**2 for w in room.walls))
    room.floor_area = widen(room.floor_area, 2 * rel_h, area_abs)
    return room
