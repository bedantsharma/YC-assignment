"""Photo tier front end: room folders of stills in, plan rooms named after the folders out.

Input contract (brief): 2-8 stills per room, one folder per room, no depth or poses. Each
folder is reconstructed on its own (same model, scale correction and plan backend as the
video tier, plus line-of-sight carving) and gives the room its photos were taken from.
Reconstructing all folders jointly was tried first and placed rooms 1-2 m wrong
(docs/photo_tier.md), so rooms are measured but not stitched: the plan lays them side by
side and says so.

Naming. A photo is taken from inside a room, so each plan room is named after the folder
whose photos' camera positions fall inside it most often. A room no photo was taken from
is named after the nearest camera's folder, with a warning.
"""

import math
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
STRIP_OVERLAP = 0.25  # share of a strip seen by the next (odd-orientation photos)


def few_photo_warnings(rooms: dict[str, list[Path]]) -> list[str]:
    return [
        f"folder {name!r}: {len(photos)} photos; rooms with fewer than {MIN_PHOTOS_GOOD} came "
        "out 10-35% small in tests (parts of the room never seen): take 5-8 per room"
        for name, photos in rooms.items()
        if len(photos) < MIN_PHOTOS_GOOD
    ]


def load_images(paths: list[Path]) -> list[Image.Image]:
    """Upright RGB images (EXIF orientation applied), long side PHOTO_LONG_SIDE."""
    _register_heif()
    out = []
    for p in paths:
        img = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
        img.thumbnail((PHOTO_LONG_SIDE, PHOTO_LONG_SIDE), Image.Resampling.LANCZOS)
        out.append(img)
    return out


def load_folder(paths: list[Path]) -> tuple[list[Image.Image], list[str]]:
    """One folder's photos as images of one orientation, plus notes on what was split.

    The model resizes every view of a pass to one aspect ratio, so a portrait photo in a
    landscape folder loses its top and bottom to a centre crop. Instead each photo of the
    minority orientation is split, at full resolution, into strips of the majority aspect
    that overlap by STRIP_OVERLAP and together cover the whole photo. A strip is an
    off-centre crop of the same camera: Pi3X predicts a ray per pixel, so it needs no
    centred principal point. Folders of one orientation come out as load_images.
    """
    full = [_upright(p) for p in paths]
    landscape = [im.width >= im.height for im in full]
    major = sum(landscape) * 2 >= len(full)  # True: landscape (ties go landscape)
    ref = [im for im, ls in zip(full, landscape, strict=True) if ls == major]
    aspect = float(np.median([max(im.size) / min(im.size) for im in ref]))
    out, split = [], 0
    for im, ls in zip(full, landscape, strict=True):
        if ls == major:
            out.append(im)
            continue
        split += 1
        w, h = im.size
        if major:  # portrait photo -> landscape strips stacked top to bottom
            s = round(w / aspect)
            n = math.ceil((h - s) / (s * (1 - STRIP_OVERLAP))) + 1
            out += [im.crop((0, y, w, y + s)) for y in _offsets(h, s, n)]
        else:  # landscape photo -> portrait strips left to right
            s = round(h / aspect)
            n = math.ceil((w - s) / (s * (1 - STRIP_OVERLAP))) + 1
            out += [im.crop((x, 0, x + s, h)) for x in _offsets(w, s, n)]
    for im in out:
        im.thumbnail((PHOTO_LONG_SIDE, PHOTO_LONG_SIDE), Image.Resampling.LANCZOS)
    kind = "portrait" if major else "landscape"
    notes = [f"{split} {kind} photo(s) split into {'landscape' if major else 'portrait'} "
             "strips to match the folder"] if split else []  # fmt: skip
    return out, notes


def _offsets(length: int, strip: int, n: int) -> list[int]:
    return [round(v) for v in np.linspace(0, length - strip, n)]


def _upright(path: Path) -> Image.Image:
    _register_heif()
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def _register_heif() -> None:
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()  # iPhone Camera saves HEIC by default
    except ImportError:
        pass


def main_room(rooms: list[Room], angle_deg: float, cams_xy: np.ndarray) -> int:
    """Index of the room the photos were taken from (most cameras inside; else largest)."""
    uv = Grid(angle_deg, np.zeros(2), 1.0, (1, 1)).to_plan(cams_xy)
    inside = [int(Poly(np.asarray(r.polygon)).contains_points(uv).sum()) for r in rooms]
    return max(range(len(rooms)), key=lambda k: (inside[k], rooms[k].floor_area.value))


def rename_room(room: Room, room_id: str) -> Room:
    """Give a folder's room its own id (every folder's plan starts at r1). Openings to other
    rooms of that folder are cut: those rooms are dropped."""
    old = room.id
    room.id = room_id
    if room.label == old:
        room.label = room_id
    for w in room.walls:
        w.id = room_id + w.id[len(old) :]
    for o in room.openings:
        o.id = room_id + o.id[len(old) :]
        o.wall_id = room_id + o.wall_id[len(old) :]
        o.connects_to = None
    return room


def shift_room(room: Room, dx: float, dy: float) -> Room:
    room.polygon = [(round(x + dx, 4), round(y + dy, 4)) for x, y in room.polygon]
    for w in room.walls:
        w.start = (round(w.start[0] + dx, 4), round(w.start[1] + dy, 4))
        w.end = (round(w.end[0] + dx, 4), round(w.end[1] + dy, 4))
    return room


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
