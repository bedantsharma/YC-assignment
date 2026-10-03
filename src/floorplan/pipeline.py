"""One capture in, one Result out. Stages are added here as they are built."""

import math
import time
from pathlib import Path

import numpy as np

from floorplan.capture import detect_format, load_lidar, load_photos, load_video, resolve_tier
from floorplan.cloud import fuse, voxel_downsample
from floorplan.drift import METHOD as DRIFT_METHOD
from floorplan.drift import correct_drift
from floorplan.intervals import VIDEO_SCALE_REL, VIDEO_SURFACE_M, widen_room
from floorplan.lidar import build_plan
from floorplan.output import Capture, Measurement, Result

MAX_LIDAR_FRAMES = 3000  # more adds run time, not accuracy (depth frames overlap heavily)
VIDEO_FRAMES = 30  # 12.8 GB peak on a 16 GB Mac (docs/model_spike.md)
VIDEO_VOXEL_M = 0.02


def run(
    path: Path | str,
    tier: str | None = None,
    drift: bool = False,
    frames: int = VIDEO_FRAMES,
    up: str = "auto",
) -> Result:
    path = Path(path)
    fmt = detect_format(path)
    tier = resolve_tier(fmt, tier)
    capture = Capture(path.stem if path.is_file() else path.name, tier=tier, source=str(path))
    if tier == "lidar":
        return _run_lidar(path, capture, drift)
    if tier == "video":
        return _run_video(path, capture, frames, up)

    start = time.perf_counter()
    rooms = load_photos(path).rooms
    summary = f"{len(rooms)} rooms, {sum(map(len, rooms.values()))} photos"
    timing = {"load": round(time.perf_counter() - start, 3)}
    warnings = [f"loaded {summary}; photo geometry not implemented yet"]
    return Result(capture=capture, rooms=[], timing_s=timing, warnings=warnings)


def _run_video(path: Path, capture: Capture, n_frames: int, up: str) -> Result:
    from floorplan.mvs import reconstruct
    from floorplan.video import Orientation, estimate_up, orientation, sample_frames, z_up

    timing = {}
    video = load_video(path).path
    start = time.perf_counter()
    orient = orientation(video) if up == "auto" else Orientation(up, "--up", 0.0)
    frames = sample_frames(video, n_frames, orient.up_side)
    timing["frames"] = round(time.perf_counter() - start, 3)

    start = time.perf_counter()
    rec = reconstruct(frames)
    timing["reconstruction"] = round(time.perf_counter() - start, 3)

    start = time.perf_counter()
    vertical = estimate_up(rec.points, rec.cam_poses)
    points = voxel_downsample(z_up(rec.points, vertical), VIDEO_VOXEL_M)
    plan = build_plan(points)
    rooms = [widen_room(r, VIDEO_SCALE_REL, VIDEO_SURFACE_M) for r in plan.rooms]
    timing["geometry"] = round(time.perf_counter() - start, 3)

    footprint = None
    if rooms:
        total = sum(r.floor_area.value for r in rooms)
        half = math.sqrt(sum((r.floor_area.hi - r.floor_area.value) ** 2 for r in rooms))
        footprint = Measurement(
            round(total, 4), round(total - half, 4), round(total + half, 4), "m2"
        )
    how = f"{orient.source}, margin {orient.margin:.1f}" if orient.margin else orient.source
    warnings = [
        f"used {len(frames)} frames of {video.name}; up = stored frame's {orient.up_side} ({how})",
        f"reconstruction: MapAnything, {rec.seconds:.0f} s; intervals widened by "
        f"{100 * VIDEO_SCALE_REL:.0f}% scale and {100 * VIDEO_SURFACE_M:.0f} cm surface error "
        "(provisional, from the model spike)",
        *plan.warnings,
    ]
    return Result(
        capture=capture,
        rooms=rooms,
        footprint_area=footprint,
        plan_rotation_deg=plan.rotation_deg,
        drift_correction="none needed: all frames reconstructed jointly in one pass",
        timing_s=timing,
        warnings=warnings,
    )


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
