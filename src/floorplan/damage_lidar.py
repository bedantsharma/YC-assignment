"""Damage stage of the LiDAR tier: keyframes of the recording's RGB video -> detections ->
sizes on the measured surfaces -> flags and scope.

Keyframes (damage_frames.py). The frames where the user paused (the protocol asks for a
hold at each damage), then the fewest frames that see every wall and ceiling patch twice,
close and near face-on; up to DAMAGE_FRAMES in all. Each is swapped for the sharpest of
its neighbours (variance of the Laplacian). Stray Scanner stores frame i of rgb.mp4 with
pose row i of odometry.csv (same count on every capture checked); the stage loads the full
recording itself, since the pipeline's copy is thinned for geometry.

Calls. The detector is a network call, so up to DETECT_WORKERS images are sent at once.

Upright. Stray stores portrait captures sideways; the detector gets each frame turned by a
multiple of 90 degrees so the world's up is the image's top (from the frame's pose), and
the intrinsics and pose are turned with it, so geometry works in the detector's pixels.

Depth check. A box on a picture frame or a lamp lies in front of the wall: when the LiDAR
depth at the mask centre is more than OCCLUDED_M shorter than the distance to the surface
the ray hits, the detection is dropped and counted in a warning.
"""

import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from floorplan.capture import STRAY_RGB_SIZE, LidarCapture, detect_format, load_lidar
from floorplan.damage import Detection, detect, model_name
from floorplan.damage_frames import MIN_VIEWS, NEED, confirm, select
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

DAMAGE_FRAMES = 60
CANDIDATE_STEP = 4  # frames either side of a chosen frame tried for sharpness
DETECT_WORKERS = 8
UNSEEN_WARN = 0.3  # warn about surfaces with more than this share never seen up close
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
    crack_pass: bool = False,
):
    """(surfaces, damage, flags, scope, warnings) for one Stray Scanner capture."""
    if detect_format(path) != "stray":
        return [], [], [], [], ["damage: only Stray Scanner recordings are supported so far"]
    video = path / "rgb.mp4"
    full = load_lidar(path)  # `frames` is thinned for geometry; video frame i = pose row i
    n = len(full.poses)
    depth_w = Image.open(full.depth_paths[0]).size[0]
    to_rgb = STRAY_RGB_SIZE[0] / depth_w
    k_rgb = full.intrinsics.copy()
    k_rgb[:, :2] *= to_rgb
    planes = surface_planes(rooms, floor_z)
    plan_poses = np.array([to_plan_pose(p, angle_deg) for p in full.poses])
    sel = select(
        plan_poses, k_rgb, STRAY_RGB_SIZE, planes, _fps(path), n_frames, lambda i: _depth(full, i)
    )
    idx = _sharpest(video, sel.frames, n)
    rng = np.random.default_rng(SEED)

    views = []
    for i, raw in idx.items():
        turns, pose, K = upright(full.poses[i], k_rgb[i], raw.size)
        image = Image.fromarray(np.rot90(np.asarray(raw), turns))
        views.append((i, turns, raw.size, image, View(f"frame_{i:06d}", pose, K, image.size)))
    with ThreadPoolExecutor(DETECT_WORKERS) as pool:
        found = list(pool.map(lambda v: detect(v[4].image_id, v[3], crack_pass=crack_pass), views))

    placed: list[Placed] = []
    counts = {"detections": 0, "occluded": 0, "off_surface": 0, "context": 0}
    for (i, turns, raw_size, image, view), dets in zip(views, found, strict=True):
        counts["detections"] += len(dets)
        kept = []
        for det in dets:
            if _occluded(det, view, full, i, turns, raw_size, angle_deg, planes, rooms):
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

    cams = {view.image_id: (plan_poses[i], k_rgb[i], _depth(full, i)) for i, _, _, _, view in views}
    merged, dropped, unconfirmed = confirm(merge(placed), cams, STRAY_RGB_SIZE)
    for m in unconfirmed:
        m.notes.append("seen once; no other keyframe could see this spot (unconfirmed)")
    surfs, damage, flags, scope = build(merged, rooms)
    n_pause = sum(1 for f in sel.frames if any(a <= f <= b for a, b in sel.pauses))
    warnings = [
        f"damage keyframes: {len(sel.frames)} of {n} frames ({n_pause} from "
        f"{len(sel.pauses)} pauses, the rest for coverage); wall and ceiling patches seen "
        f"up close by 1+ keyframes: {100 * sel.seen_once:.0f}%, by {NEED}+: "
        f"{100 * sel.seen_need:.0f}%",
        f"damage: {model_name()} (hosted, Google) on {len(idx)} keyframes: "
        f"{counts['detections']} detections, {counts['occluded']} dropped as in front of the "
        f"surface (LiDAR depth), {counts['off_surface']} not on a measured surface; "
        f"{len(damage)} damage items after merging views; masks are model-free (contrast, "
        "ellipse fallback)",
    ]
    if dropped:
        warnings.append(
            f"damage: {len(dropped)} item(s) dropped by the {MIN_VIEWS}-view rule (reported "
            "in one keyframe while other keyframes looked at the same spot): "
            + "; ".join(
                f"{m.label} on {m.surface.surface_id} at ({m.centre[0]:.2f}, "
                f"{m.centre[1]:.2f}), seen by {n} keyframes"
                for m, n in dropped
            )
        )
    unseen = [f"{sid} {100 * v:.0f}%" for sid, v in sel.unseen.items() if v > UNSEEN_WARN]
    if unseen:
        warnings.append(
            "damage: never seen up close by any frame (small damage there can be missed): "
            + ", ".join(unseen)
        )
    single = [d.id for d in damage if len(d.views) == 1]
    if single:
        warnings.append(
            "damage: seen once, and no other keyframe could see the spot (unconfirmed): "
            + ", ".join(single)
        )
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


def _fps(path: Path) -> float:
    t = np.loadtxt(path / "odometry.csv", delimiter=",", skiprows=1, usecols=0, ndmin=1)
    return float(1.0 / np.median(np.diff(t))) if len(t) > 1 else 30.0


def _depth(cap: LidarCapture, i: int) -> np.ndarray:
    """LiDAR depth in metres, 0 where confidence is low."""
    depth = np.asarray(Image.open(cap.depth_paths[i]), dtype=float) / 1000.0
    conf = np.asarray(Image.open(cap.confidence_paths[i]))
    return np.where(conf >= 1, depth, 0.0)


def _sharpest(video: Path, centres: list[int], n: int) -> dict[int, Image.Image]:
    """Sharpest frame within CANDIDATE_STEP of each centre (one decoding pass)."""
    offsets = range(-CANDIDATE_STEP, CANDIDATE_STEP + 1, 2)
    owner = {}
    for k, c in enumerate(centres):
        for o in offsets:
            if 0 <= c + o < n:
                owner.setdefault(c + o, k)
    cands = sorted(owner)
    if not cands:
        return {}
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
        sharp = float(ndimage.laplace(img[::4, ::4].mean(axis=2)).var())
        k = owner[c]
        if k not in best or sharp > best[k][0]:
            best[k] = (sharp, c, img.copy())
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
        if det.points:
            draw.line(det.points, fill=col, width=lw)
        draw.rectangle(det.box, outline=col, width=lw)
        draw.text((det.box[0] + 4, det.box[1] + 4), f"{det.label} {det.score:.2f}", fill=col)
    return im


def _overlay(image, dets, kept, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    overlay(image, dets, kept).save(path, quality=85)
