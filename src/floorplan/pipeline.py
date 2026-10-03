"""One capture in, one Result out. Stages are added here as they are built."""

import math
import time
from pathlib import Path

import numpy as np

from floorplan.capture import detect_format, load_lidar, load_photos, load_video, resolve_tier
from floorplan.cloud import fuse
from floorplan.drift import METHOD as DRIFT_METHOD
from floorplan.drift import correct_drift
from floorplan.lidar import build_plan
from floorplan.output import Capture, Result

MAX_LIDAR_FRAMES = 3000  # more adds run time, not accuracy (depth frames overlap heavily)


def run(path: Path | str, tier: str | None = None, drift: bool = False) -> Result:
    path = Path(path)
    fmt = detect_format(path)
    tier = resolve_tier(fmt, tier)
    capture = Capture(path.stem if path.is_file() else path.name, tier=tier, source=str(path))
    if tier == "lidar":
        return _run_lidar(path, capture, drift)

    start = time.perf_counter()
    if tier == "video":
        summary = f"video {load_video(path).path.name}"
    else:
        rooms = load_photos(path).rooms
        summary = f"{len(rooms)} rooms, {sum(map(len, rooms.values()))} photos"
    timing = {"load": round(time.perf_counter() - start, 3)}
    warnings = [f"loaded {summary}; {tier} geometry not implemented yet"]
    return Result(capture=capture, rooms=[], timing_s=timing, warnings=warnings)


def _run_lidar(path: Path, capture: Capture, drift: bool) -> Result:
    timing = {}
    start = time.perf_counter()
    n_frames = len(load_lidar(path).depth_paths)
    frames = load_lidar(path, stride=max(1, math.ceil(n_frames / MAX_LIDAR_FRAMES)))
    timing["load"] = round(time.perf_counter() - start, 3)

    drift_warnings = []
    if drift:
        start = time.perf_counter()
        frames, corrections = correct_drift(frames)
        timing["drift"] = round(time.perf_counter() - start, 3)
        used = [c for c in corrections if c.accepted and (c.yaw_deg or any(c.shift))]
        if corrections:
            yaw = max((abs(c.yaw_deg) for c in used), default=0.0)
            shift = max((float(np.hypot(*c.shift)) for c in used), default=0.0)
            drift_warnings.append(
                f"drift: {len(used)} of {len(corrections) - 1} chunks re-aligned "
                f"(max {yaw:.2f} deg, {100 * shift:.1f} cm)"
            )

    start = time.perf_counter()
    points = fuse(frames)
    timing["fuse"] = round(time.perf_counter() - start, 3)

    start = time.perf_counter()
    plan = build_plan(points)
    timing["geometry"] = round(time.perf_counter() - start, 3)

    warnings = [f"used {len(frames.depth_paths)} of {n_frames} depth frames"]
    warnings += drift_warnings + plan.warnings
    return Result(
        capture=capture,
        rooms=plan.rooms,
        footprint_area=plan.footprint_area,
        plan_rotation_deg=plan.rotation_deg,
        drift_correction=DRIFT_METHOD if drift else None,
        timing_s=timing,
        warnings=warnings,
    )
