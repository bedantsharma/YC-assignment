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
from floorplan.plan2d import ENCLOSED_FRACTION_SPARSE, Sightlines

MAX_LIDAR_FRAMES = 3000  # more adds run time, not accuracy (depth frames overlap heavily)
VIDEO_FRAMES = 30  # 12.8 GB peak on a 16 GB Mac (docs/model_spike.md)
VIDEO_WINDOW = 30  # frames per model pass; more frames are reconstructed in chained windows
VIDEO_OVERLAP = 10  # frames shared by consecutive windows (src/floorplan/chunks.py)
SIGHT_POINTS = 3000  # per photo, for carving free space
PHOTO_WINDOW = 32  # photos per model pass: 8 per room x 4 rooms; 11.4 GB on the M4
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
    return _from_images(capture, frames, model, "video", timing, [note])


def _run_photos(path: Path, capture: Capture, model: str) -> Result:
    """Each folder reconstructed on its own; its main room kept and named after it. Rooms
    are laid out side by side: their relative positions are not measured."""
    from floorplan.photos import few_photo_warnings, load_folder, shift_room

    folders = load_photos(path).rooms
    timing: dict[str, float] = {}
    rooms, warnings, x = [], [], 0.0
    for name, photos in folders.items():
        start = time.perf_counter()
        images, split = load_folder(photos)
        warnings += [f"{name}: {note}" for note in split]
        timing["load"] = round(timing.get("load", 0.0) + time.perf_counter() - start, 3)
        sub_timing: dict[str, float] = {}
        res = _from_images(
            capture, images, model, "photo", sub_timing, [], [name] * len(images), True
        )
        for k, v in sub_timing.items():
            timing[k] = round(timing.get(k, 0.0) + v, 3)
        warnings += [
            f"{name}: {w}" for w in res.warnings if not w.startswith(("scale", "reconstruction"))
        ]
        if not res.rooms:
            warnings.append(f"{name}: no room found from its {len(photos)} photos")
            continue
        room = res.rooms[0]
        poly = np.asarray(room.polygon)
        shift_room(room, x - poly[:, 0].min(), -poly[:, 1].min())
        x += float(np.ptp(poly[:, 0])) + 1.0
        rooms.append(room)
    rel_h, rel_v = RESIDUAL_REL[("photo", model)]
    bias_h, bias_v = SCALE_BIAS[("photo", model)]
    header = [
        f"used {sum(map(len, folders.values()))} photos in {len(folders)} folders "
        f"({', '.join(f'{r}: {len(p)}' for r, p in folders.items())}); each folder "
        f"reconstructed on its own with {MODEL_NAMES[model]}",
        *few_photo_warnings(folders),
        f"scale corrected by the model's measured bias (horizontal x{1 / bias_h:.3f},"
        f" vertical x{1 / bias_v:.3f}); intervals widened by {100 * rel_h:.0f}% horizontal,"
        f" {100 * rel_v:.0f}% vertical and {100 * VIDEO_SURFACE_M:.0f} cm surface error"
        " (provisional until ground truth)",
    ]
    if len(folders) > 1:
        header.append(
            "rooms are NOT stitched: each is measured on its own and laid out side by side; "
            "joint reconstruction placed rooms 1-2 m wrong (docs/photo_tier.md)"
        )
    return Result(
        capture=capture,
        rooms=rooms,
        footprint_area=_footprint(rooms),
        drift_correction="none needed: each room's photos reconstructed jointly in one pass",
        timing_s=timing,
        warnings=header + warnings,
    )


def _footprint(rooms: list) -> Measurement | None:
    if not rooms:
        return None
    total = sum(r.floor_area.value for r in rooms)
    half = math.sqrt(sum((r.floor_area.hi - r.floor_area.value) ** 2 for r in rooms))
    return Measurement(round(total, 4), round(total - half, 4), round(total + half, 4), "m2")


def _from_images(
    capture: Capture,
    images: list,
    model: str,
    tier: str,
    timing: dict,
    notes: list[str],
    folders: list[str] | None = None,
    single_room: bool = False,
) -> Result:
    """Shared geometry of the video and photo tiers: images -> metric cloud -> plan."""
    from floorplan.chunks import chain
    from floorplan.mvs import reconstruct
    from floorplan.video import estimate_up, z_up

    start = time.perf_counter()
    links = []
    window = PHOTO_WINDOW if tier == "photo" else VIDEO_WINDOW
    if len(images) <= window:
        rec = reconstruct(images, model)
        joint = f"none needed: all {tier} images reconstructed jointly in one pass"
    else:
        rec, links = chain(
            len(images),
            lambda idx: reconstruct([images[i] for i in idx], model),
            window,
            VIDEO_OVERLAP,
        )
        joint = (
            f"{len(links) + 1} windows of {window} images ({VIDEO_OVERLAP} shared), "
            "chained by similarity fits on the shared images' point maps"
        )
    timing["reconstruction"] = round(time.perf_counter() - start, 3)

    start = time.perf_counter()
    vertical = estimate_up(rec.points, rec.cam_poses)
    points = voxel_downsample(correct_scale(z_up(rec.points, vertical), model, tier), VIDEO_VOXEL_M)
    # photos see walls only in parts: accept rooms enclosed by fewer observed walls
    cams = correct_scale(z_up(rec.cam_poses[:, :3, 3], vertical), model, tier)
    if tier == "photo":
        # photos see walls and floor only in parts: fewer walls enclose a room, and the
        # space each camera looked across counts as seen (docs/photo_tier.md)
        sight = _sightlines(rec, cams, vertical, model, tier)
        plan = build_plan(points, ENCLOSED_FRACTION_SPARSE, sight)
    else:
        plan = build_plan(points)
    labels = []
    if single_room and plan.rooms:  # one folder = one room: keep the room it was shot from
        from floorplan.photos import main_room

        k = main_room(plan.rooms, plan.rotation_deg, cams[:, :2])
        dropped = sum(r.floor_area.value for i, r in enumerate(plan.rooms) if i != k)
        if dropped:
            labels.append(f"dropped {dropped:.1f} m2 seen through doorways (other rooms)")
        plan.rooms = [plan.rooms[k]]
        plan.rooms[0].label = folders[0] if folders else plan.rooms[0].label
    elif folders is not None:
        from floorplan.photos import label_rooms

        labels = label_rooms(plan.rooms, plan.rotation_deg, cams[:, :2], folders)
    rel_h, rel_v = RESIDUAL_REL[(tier, model)]
    bias_h, bias_v = SCALE_BIAS[(tier, model)]
    rooms = [widen_room(r, rel_h, rel_v, VIDEO_SURFACE_M) for r in plan.rooms]
    timing["geometry"] = round(time.perf_counter() - start, 3)

    footprint = _footprint(rooms)
    warnings = [
        *notes,
        f"reconstruction: {MODEL_NAMES[rec.model]}, {rec.seconds:.0f} s",
        f"scale corrected by the model's measured bias (horizontal x{1 / bias_h:.3f},"
        f" vertical x{1 / bias_v:.3f}; damage room vs LiDAR); intervals widened by"
        f" {100 * rel_h:.0f}% horizontal, {100 * rel_v:.0f}% vertical and"
        f" {100 * VIDEO_SURFACE_M:.0f} cm surface error (provisional until ground truth)",
        *[
            f"window {k.window} chained: scale {k.scale:.3f}, residual "
            f"{100 * k.residual_m:.1f} cm over {k.pairs} points on {k.frames[0]} of "
            f"{k.frames[1]} shared frames"
            for k in links
        ],
        *labels,
        *plan.warnings,
    ]
    return Result(
        capture=capture,
        rooms=rooms,
        footprint_area=footprint,
        adjacency=plan.adjacency,
        plan_rotation_deg=plan.rotation_deg,
        drift_correction=joint,
        timing_s=timing,
        warnings=warnings,
    )


def _sightlines(rec, cams: np.ndarray, vertical: np.ndarray, model: str, tier: str) -> Sightlines:
    """Up to SIGHT_POINTS points per view (every n-th kept pixel), in the plan's frame."""
    from floorplan.video import z_up

    pts, view = [], []
    for v in range(len(rec.view_points)):
        p = rec.view_points[v][rec.view_keep[v]]
        p = p[:: max(1, len(p) // SIGHT_POINTS)]
        pts.append(correct_scale(z_up(p.astype(float), vertical), model, tier))
        view.append(np.full(len(p), v))
    return Sightlines(cams[:, :2], np.concatenate(pts), np.concatenate(view))


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
        adjacency=plan.adjacency,
        plan_rotation_deg=plan.rotation_deg,
        drift_correction=DRIFT_METHOD if drift else None,
        timing_s=timing,
        warnings=warnings,
    )
