"""Damage stage of the LiDAR tier: keyframes of the recording's RGB video -> detections ->
sizes on the measured surfaces -> flags and scope.

Keyframes. DAMAGE_FRAMES slots evenly over the recording; in each, the sharpest of a few
neighbouring frames (variance of the Laplacian). Stray Scanner stores frame i of rgb.mp4
with pose row i of odometry.csv (same count on every capture checked).

Upright. Stray stores portrait captures sideways; the detector gets each frame turned by a
multiple of 90 degrees so the world's up is the image's top (from the frame's pose), and
the intrinsics and pose are turned with it, so geometry works in the detector's pixels.

Depth check. A box on a picture frame or a lamp lies in front of the wall: when the LiDAR
depth at the mask centre is more than OCCLUDED_M shorter than the distance to the surface
the ray hits, the detection is dropped and counted in a warning.
"""

import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from floorplan.capture import STRAY_RGB_SIZE, LidarCapture, detect_format
from floorplan.damage import Detection, detect, model_name
from floorplan.damage_geom import (
    Placed,
    View,
    first_hit,
    merge,
    place,
    room_of,
    surface_planes,
    to_plan_pose,
)
from floorplan.damage_rules import build
from floorplan.output import Room

DAMAGE_FRAMES = 40
CANDIDATE_STEP = 6  # frames either side of a slot tried for sharpness
OCCLUDED_M = 0.25
SEED = 0


def run_damage(
    path: Path,
    frames: LidarCapture,
    rooms: list[Room],
    angle_deg: float,
    floor_z: float,
    n_frames: int = DAMAGE_FRAMES,
    overlay_dir: Path | None = None,
):
    """(surfaces, damage, flags, scope, warnings) for one Stray Scanner capture."""
    if detect_format(path) != "stray":
        return [], [], [], [], ["damage: only Stray Scanner recordings are supported so far"]
    video = path / "rgb.mp4"
    n = len(frames.poses)
    idx = _keyframes(video, n, n_frames)
    depth_w = Image.open(frames.depth_paths[0]).size[0]
    to_rgb = STRAY_RGB_SIZE[0] / depth_w
    planes = surface_planes(rooms, floor_z)
    rng = np.random.default_rng(SEED)

    placed: list[Placed] = []
    counts = {"detections": 0, "occluded": 0, "off_surface": 0, "context": 0}
    for i, raw in idx.items():
        k_raw = frames.intrinsics[i].copy()
        k_raw[:2] *= to_rgb
        turns, pose, K = upright(frames.poses[i], k_raw, raw.size)
        image = Image.fromarray(np.rot90(np.asarray(raw), turns))
        view = View(f"frame_{i:06d}", pose, K, image.size)
        dets = detect(view.image_id, image)
        counts["detections"] += len(dets)
        kept = []
        for det in dets:
            if _occluded(det, view, frames, i, turns, raw.size, angle_deg, planes, rooms):
                counts["occluded"] += 1
                continue
            p = place(view, angle_deg, planes, rooms, det, rng)
            if p is None:
                counts["off_surface"] += 1
                continue
            counts["context"] += not det.is_damage
            placed.append(p)
            kept.append(det)
        if overlay_dir is not None and dets:
            _overlay(image, dets, kept, overlay_dir / f"{view.image_id}.jpg")

    merged = merge(placed)
    surfs, damage, flags, scope = build(merged, rooms)
    warnings = [
        f"damage: {model_name()} (hosted, Google) on {len(idx)} keyframes: "
        f"{counts['detections']} detections, {counts['occluded']} dropped as in front of the "
        f"surface (LiDAR depth), {counts['off_surface']} not on a measured surface; "
        f"{len(damage)} damage items after merging views; masks are model-free (contrast, "
        "ellipse fallback)"
    ]
    single = [d.id for d in damage if len(d.views) == 1]
    if single:
        warnings.append(f"damage: seen in one view only (less certain): {', '.join(single)}")
    return surfs, damage, flags, scope, warnings


def upright(pose: np.ndarray, K: np.ndarray, size: tuple[int, int]):
    """(turns, pose, K) for the image np.rot90(img, turns) whose top is the world's up."""
    w, h = size
    best = None
    for turns in range(4):
        A = _rot_pixels(turns, w, h)
        Kr = A @ K
        for q in _z_rotations():
            Kn = Kr @ q.T
            if abs(Kn[0, 1]) < 1e-6 and abs(Kn[1, 0]) < 1e-6 and Kn[0, 0] > 0 and Kn[1, 1] > 0:
                break
        pn = pose.copy()
        pn[:3, :3] = pose[:3, :3] @ q.T
        up_score = float(-pn[:3, 1] @ np.array([0, 0, 1.0]))
        if best is None or up_score > best[0]:
            best = (up_score, turns, pn, Kn / Kn[2, 2])
    return best[1], best[2], best[3]


def _rot_pixels(turns: int, w: int, h: int) -> np.ndarray:
    """Homogeneous map raw pixel (x, y) -> pixel in np.rot90(img, turns) (counter-clockwise)."""
    A = np.eye(3)
    for _ in range(turns % 4):
        # one counter-clockwise turn of a w x h image: x' = y, y' = w - x
        A = np.array([[0, 1, 0], [-1, 0, w], [0, 0, 1.0]]) @ A
        w, h = h, w
    return A


def _z_rotations() -> list[np.ndarray]:
    out = []
    for k in range(4):
        c, s = round(np.cos(k * np.pi / 2)), round(np.sin(k * np.pi / 2))
        out.append(np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]]))
    return out


def _occluded(det: Detection, view, frames, i, turns, raw_size, angle_deg, planes, rooms):
    if det.mask is None or not det.mask.any():
        return False
    cy, cx = ndimage.center_of_mass(det.mask)
    pose = to_plan_pose(view.pose, angle_deg)
    d = np.linalg.inv(view.K) @ np.array([cx + 0.5, cy + 0.5, 1.0])
    ray = pose[:3, :3] @ (d / np.linalg.norm(d))
    hit = first_hit(planes, pose[:3, 3], ray, room_of(rooms, pose[:3, 3][:2]))
    if hit is None:
        return False
    z_surface = hit[1] * (d / np.linalg.norm(d))[2]  # depth along the optical axis
    # back to the raw (stored) frame, then to depth resolution
    A = _rot_pixels(turns, *raw_size)
    x, y, _ = np.linalg.inv(A) @ np.array([cx + 0.5, cy + 0.5, 1.0])
    depth = np.asarray(Image.open(frames.depth_paths[i]), dtype=float) / 1000.0
    conf = np.asarray(Image.open(frames.confidence_paths[i]))
    s = depth.shape[1] / raw_size[0]
    r, c = int(y * s), int(x * s)
    win = (slice(max(0, r - 2), r + 3), slice(max(0, c - 2), c + 3))
    vals = depth[win][(conf[win] >= 1) & (depth[win] > 0)]
    if not len(vals):
        return False
    return float(np.median(vals)) < z_surface - OCCLUDED_M


def _keyframes(video: Path, n: int, slots: int) -> dict[int, Image.Image]:
    """Sharpest frame near each of `slots` evenly spaced frame indices."""
    centres = np.linspace(CANDIDATE_STEP, n - 1 - CANDIDATE_STEP, slots).round().astype(int)
    offsets = (-CANDIDATE_STEP, 0, CANDIDATE_STEP)
    cands = sorted({int(c + o) for c in centres for o in offsets if 0 <= c + o < n})
    w, h = STRAY_RGB_SIZE
    expr = "+".join(f"eq(n\\,{c})" for c in cands)
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-noautorotate", "-i", str(video), "-vf", f"select='{expr}'"]
        + ["-vsync", "0", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE,
    )
    best: dict[int, tuple[float, int, np.ndarray]] = {}
    for c in cands:
        buf = proc.stdout.read(w * h * 3)
        if len(buf) < w * h * 3:
            break
        img = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        g = img[::4, ::4].mean(axis=2)
        sharp = float(ndimage.laplace(g).var())
        slot = int(np.argmin(np.abs(centres - c)))
        if slot not in best or sharp > best[slot][0]:
            best[slot] = (sharp, c, img.copy())
    proc.stdout.close()
    proc.wait()
    return {c: Image.fromarray(img) for _, c, img in sorted(best.values(), key=lambda t: t[1])}


COLOURS = {
    "crack": (255, 60, 60),
    "water_stain": (60, 140, 255),
    "mould": (40, 200, 80),
    "hole": (255, 160, 0),
    "peeling_paint": (220, 80, 255),
    "outlet_or_switch": (200, 200, 200),
    "exposed_wiring": (255, 255, 0),
}


def overlay(image: Image.Image, dets: list[Detection], kept: list[Detection]) -> Image.Image:
    """Image with each detection's box (dashed grey when dropped) and mask tinted."""
    im = image.convert("RGB").copy()
    arr = np.asarray(im).copy()
    for det in kept:
        if det.mask is not None:
            col = np.array(COLOURS.get(det.label, (255, 255, 255)))
            arr[det.mask] = (0.5 * arr[det.mask] + 0.5 * col).astype(np.uint8)
    im = Image.fromarray(arr)
    draw = ImageDraw.Draw(im)
    lw = max(2, im.width // 400)
    for det in dets:
        col = COLOURS.get(det.label, (255, 255, 255)) if det in kept else (128, 128, 128)
        draw.rectangle(det.box, outline=col, width=lw)
        draw.text((det.box[0] + 4, det.box[1] + 4), f"{det.label} {det.score:.2f}", fill=col)
    return im


def _overlay(image, dets, kept, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    overlay(image, dets, kept).save(path, quality=85)
