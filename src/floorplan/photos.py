"""Photo tier front end: room folders of stills in, plan rooms named after the folders out.

Input contract (brief): 2-8 stills per room, one folder per room, no depth or poses. All
folders are reconstructed jointly (photos through doorways tie the rooms together), so the
geometry is the video tier's: same model, same scale correction, same plan backend.

Naming. A photo is taken from inside a room, so each plan room is named after the folder
whose photos' camera positions fall inside it most often. A room no photo was taken from
is named after the nearest camera's folder, with a warning.
"""

from collections import Counter
from pathlib import Path

import numpy as np
from matplotlib.path import Path as Poly
from PIL import Image, ImageOps

from floorplan.output import Room
from floorplan.plan2d import Grid

PHOTO_LONG_SIDE = 960
# Rooms with fewer photos than this came out 10-35% small in tests (part of the room never
# seen; docs/photo_tier.md); with 5-7 protocol-style photos, within 3-5% on sqrt(area)
MIN_PHOTOS_GOOD = 5


def few_photo_warnings(rooms: dict[str, list[Path]]) -> list[str]:
    return [
        f"folder {name!r}: {len(photos)} photos; rooms with fewer than {MIN_PHOTOS_GOOD} came "
        "out 10-35% small in tests (parts of the room never seen): take 5-8 per room"
        for name, photos in rooms.items()
        if len(photos) < MIN_PHOTOS_GOOD
    ]


def load_images(paths: list[Path]) -> list[Image.Image]:
    """Upright RGB images (EXIF orientation applied), long side PHOTO_LONG_SIDE."""
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()  # iPhone Camera saves HEIC by default
    except ImportError:
        pass
    out = []
    for p in paths:
        img = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
        img.thumbnail((PHOTO_LONG_SIDE, PHOTO_LONG_SIDE), Image.Resampling.LANCZOS)
        out.append(img)
    return out


def label_rooms(
    rooms: list[Room], angle_deg: float, cams_xy: np.ndarray, folders: list[str]
) -> list[str]:
    """Name each plan room after a folder; returns warnings. cams_xy: (V, 2) world xy."""
    uv = Grid(angle_deg, np.zeros(2), 1.0, (1, 1)).to_plan(cams_xy)
    warnings, used = [], Counter()
    for room in rooms:
        inside = Poly(np.asarray(room.polygon)).contains_points(uv)
        if inside.any():
            votes = Counter(f for f, i in zip(folders, inside, strict=True) if i)
            name = votes.most_common(1)[0][0]
        else:
            centre = np.asarray(room.polygon).mean(axis=0)
            name = folders[int(np.argmin(np.linalg.norm(uv - centre, axis=1)))]
            warnings.append(f"{room.id}: no photo taken inside; named after the nearest photo")
        used[name] += 1
        room.label = name if used[name] == 1 else f"{name} ({used[name]})"
    for name, n in used.items():
        if n > 1:
            warnings.append(f"folder {name!r} spans {n} plan rooms")
    missing = sorted(set(folders) - set(used))
    if missing:
        warnings.append(f"no plan room found for folder(s): {', '.join(missing)}")
    return warnings
