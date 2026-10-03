"""One capture in, one Result out. Stages are added here as they are built."""

import math
import time
from pathlib import Path

import numpy as np

from floorplan.capture import detect_format, load_lidar, load_photos, load_video, resolve_tier
from floorplan.cloud import fuse, voxel_downsample
from floorplan.drift import METHOD as DRIFT_METHOD
from floorplan.drift import correct_drift
from floorplan.intervals import (
    RESIDUAL_REL,
    SCALE_BIAS,
    VIDEO_SURFACE_M,
    correct_scale,
    widen_room,
)
from floorplan.lidar import build_plan
from floorplan.output import Capture, Measurement, Result

MAX_LIDAR_FRAMES = 3000  # more adds run time, not accuracy (depth frames overlap heavily)
VIDEO_FRAMES = 30  # 12.8 GB peak on a 16 GB Mac (docs/model_spike.md)
VIDEO_WINDOW = 30  # frames per model pass; more frames are reconstructed in chained windows
VIDEO_OVERLAP = 10  # frames shared by consecutive windows (src/floorplan/chunks.py)
VIDEO_VOXEL_M = 0.02
MODEL_NAMES = {"pi3x": "Pi3X (CC BY-NC weights)", "mapanything": "MapAnything (Apache 2.0)"}


def run(
    path: Path | str,
    tier: str | None = None,
    drift: bool = False,
    frames: int = VIDEO_FRAMES,
    up: str = "auto",
    model: str = "pi3x",
) -> Result:
    path = Path(path)
    fmt = detect_format(path)
    tier = resolve_tier(fmt, tier)
    capture = Capture(path.stem if path.is_file() else path.name, tier=tier, source=str(path))
    if tier == "lidar":
        return _run_lidar(path, capture, drift)
    if tier == "video":
        return _run_video(path, capture, frames, up, model)

    return _run_photos(path, capture, model)


def _run_video(path: Path, capture: Capture, n_frames: int, up: str, model: str) -> Result:
    from floorplan.video import Orientation, orientation, sample_frames

    timing = {}
    video = load_video(path).path
    start = time.perf_counter()
    orient = orientation(video) if up == "auto" else Orientation(up, "--up", 0.0)
    frames = sample_frames(video, n_frames, orient.up_side)
    timing["frames"] = round(time.perf_counter() - start, 3)
    how = f"{orient.source}, margin {orient.margin:.1f}" if orient.margin else orient.source
    note = (
        f"used {len(frames)} frames of {video.name}; up = stored frame's {orient.up_side} ({how})"
    )
    return _from_images(capture, frames, model, "video", timing, note)


def _run_photos(path: Path, capture: Capture, model: str) -> Result:
    from floorplan.photos import load_images

    timing = {}
    start = time.perf_counter()
    rooms = load_photos(path).rooms
    folders = [room for room, photos in rooms.items() for _ in photos]
    images = load_images([p for photos in rooms.values() for p in photos])
    timing["load"] = round(time.perf_counter() - start, 3)
    note = (
        f"used {len(images)} photos in {len(rooms)} folders "
        f"({', '.join(f'{r}: {len(p)}' for r, p in rooms.items())}), reconstructed jointly"
    )
    return _from_images(capture, images, model, "photo", timing, note, folders)


def _from_images(
    capture: Capture,
    images: list,
    model: str,
    tier: str,
    timing: dict,
    note: str,
    folders: list[str] | None = None,
) -> Result:
    """Shared geometry of the video and photo tiers: images -> metric cloud -> plan."""
    from floorplan.chunks import chain
    from floorplan.mvs import reconstruct
    from floorplan.video import estimate_up, z_up

    start = time.perf_counter()
    links = []
    if len(images) <= VIDEO_WINDOW:
        rec = reconstruct(images, model)
        joint = f"none needed: all {tier} images reconstructed jointly in one pass"
    else:
        rec, links = chain(
            len(images),
            lambda idx: reconstruct([images[i] for i in idx], model),
            VIDEO_WINDOW,
            VIDEO_OVERLAP,
        )
        joint = (
            f"{len(links) + 1} windows of {VIDEO_WINDOW} images ({VIDEO_OVERLAP} shared), "
            "chained by similarity fits on the shared images' point maps"
        )
    timing["reconstruction"] = round(time.perf_counter() - start, 3)

    start = time.perf_counter()
    vertical = estimate_up(rec.points, rec.cam_poses)
    points = voxel_downsample(correct_scale(z_up(rec.points, vertical), model), VIDEO_VOXEL_M)
    plan = build_plan(points)
    labels = []
    if folders is not None:
        from floorplan.photos import label_rooms

        cams = correct_scale(z_up(rec.cam_poses[:, :3, 3], vertical), model)
        labels = label_rooms(plan.rooms, plan.rotation_deg, cams[:, :2], folders)
    rel_h, rel_v = RESIDUAL_REL[(tier, model)]
    rooms = [widen_room(r, rel_h, rel_v, VIDEO_SURFACE_M) for r in plan.rooms]
    timing["geometry"] = round(time.perf_counter() - start, 3)

    footprint = None
    if rooms:
        total = sum(r.floor_area.value for r in rooms)
        half = math.sqrt(sum((r.floor_area.hi - r.floor_area.value) ** 2 for r in rooms))
        footprint = Measurement(
            round(total, 4), round(total - half, 4), round(total + half, 4), "m2"
        )
    warnings = [
        note,
        f"reconstruction: {MODEL_NAMES[rec.model]}, {rec.seconds:.0f} s",
        f"scale corrected by the model's measured bias (horizontal x{1 / SCALE_BIAS[model][0]:.3f},"
        f" vertical x{1 / SCALE_BIAS[model][1]:.3f}; damage room vs LiDAR); intervals widened by"
        f" {100 * rel_h:.0f}% horizontal, {100 * rel_v:.0f}% vertical and"
        f" {100 * VIDEO_SURFACE_M:.0f} cm surface error (provisional until ground truth)",
        *[
            f"window {k.window} chained: scale {k.scale:.3f}, residual "
            f"{100 * k.residual_m:.1f} cm over {k.pairs} points"
            for k in links
        ],
        *labels,
        *plan.warnings,
    ]
    return Result(
        capture=capture,
        rooms=rooms,
        footprint_area=footprint,
        plan_rotation_deg=plan.rotation_deg,
        drift_correction=joint,
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
