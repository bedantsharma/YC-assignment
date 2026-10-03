"""One capture in, one Result out. Stages are added here as they are built."""

import time
from pathlib import Path

from floorplan.capture import detect_format, load_lidar, load_photos, load_video, resolve_tier
from floorplan.output import Capture, Result


def run(path: Path | str, tier: str | None = None) -> Result:
    path = Path(path)
    fmt = detect_format(path)
    tier = resolve_tier(fmt, tier)
    timing, warnings = {}, []

    start = time.perf_counter()
    if tier == "lidar":
        frames = load_lidar(path)
        summary = f"{len(frames.depth_paths)} depth frames"
    elif tier == "video":
        summary = f"video {load_video(path).path.name}"
    else:
        rooms = load_photos(path).rooms
        summary = f"{len(rooms)} rooms, {sum(map(len, rooms.values()))} photos"
    timing["load"] = round(time.perf_counter() - start, 3)

    warnings.append(f"loaded {summary}; geometry stages not implemented yet")
    capture_id = path.stem if path.is_file() else path.name
    return Result(
        capture=Capture(capture_id, tier=tier, source=str(path)),
        rooms=[],
        timing_s=timing,
        warnings=warnings,
    )
