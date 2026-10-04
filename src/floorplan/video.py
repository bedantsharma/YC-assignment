"""Video tier front end: upright frames from a video, and the vertical of a reconstruction.

RGB only (isolation rule, docs/data_plan.md): nothing here reads depth, poses, intrinsics
or IMU, even when the video comes from a LiDAR recording.

Orientation. Camera-app videos carry a rotation tag that ffmpeg applies when decoding.
Stray Scanner videos carry none and store portrait captures sideways, which collapses the
reconstruction (docs/model_spike.md). Without a tag, "up" is the frame side that is
brightest on average (ceiling, lights, windows): right on all 6 Stray captures checked
against ARKit gravity (evaluation only).

Vertical. After reconstruction, up starts as the cameras' mean image-up direction and is
refined to the direction the wall normals are perpendicular to. On c_damage_01 this agrees
with the floor normals to 0.6 deg.

Frames store. ffmpeg on the laptop (ARM) and on Kaggle (x86) decode the same video to
slightly different pixels, whatever the version (c_home_v2: 6.1 and 7.1 agree on the Mac,
Kaggle's 6.1 differs), so a reconstruction cached on Kaggle (keyed by pixels) would not
replay. With FLOORPLAN_FRAMES_CACHE set, sampled frames are stored as lossless PNG, keyed
by the video's bytes, frame count and orientation: decode once on the laptop, ship the
store, and Kaggle reads the same pixels instead of decoding.
"""

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

from floorplan.cloud import voxel_downsample

SIDES = ("top", "right", "bottom", "left")
TRANSPOSE = {"top": None, "left": "transpose=1", "right": "transpose=2", "bottom": "vflip,hflip"}
PROBE_FRAMES = 60
EDGE_SHARE = 0.25  # strip of the frame (share of its height / width) compared per side
FRAME_LONG_SIDE = 960
NORMAL_NEIGHBOURS = 12
PLANAR_MAX = 0.02  # smallest / total local variance: below this a point lies on a plane
WALL_BAND_DEG = 25.0
FRAMES_CACHE_ENV = "FLOORPLAN_FRAMES_CACHE"


@dataclass
class Orientation:
    up_side: str  # side of the stored frame that is up in the scene
    source: str  # "metadata" or "brightness"
    margin: float  # brightness score of the chosen side minus the runner-up (0 for metadata)


def duration(video: Path) -> float:
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json"])
    return float(json.loads(out(video))["format"]["duration"])


def orientation(video: Path) -> Orientation:
    out = _run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries"]
        + ["stream_side_data=rotation:stream_tags=rotate", "-of", "json"]
    )
    stream = json.loads(out(video))["streams"][0]
    tagged = stream.get("tags", {}).get("rotate") or any(
        "rotation" in d for d in stream.get("side_data_list", [])
    )
    if tagged:
        return Orientation("top", "metadata", 0.0)  # ffmpeg rotates on decode
    score = np.zeros(4)
    for t in np.linspace(0.5, duration(video) - 0.5, PROBE_FRAMES):
        f = _gray(video, t)
        h, w = f.shape
        eh, ew = int(EDGE_SHARE * h / 2), int(EDGE_SHARE * w / 2)
        sides = np.array([f[:eh].mean(), f[:, -ew:].mean(), f[-eh:].mean(), f[:, :ew].mean()])
        score += (sides - sides.mean()) / (f.std() + 1.0)
    order = np.argsort(score)[::-1]
    return Orientation(SIDES[order[0]], "brightness", float(score[order[0]] - score[order[1]]))


def sample_frames(video: Path, n: int, up_side: str) -> list[Image.Image]:
    """n upright frames, evenly spaced in time (read from the frames store if it has them)."""
    store = _frames_dir(video, n, up_side)
    if store and store.is_dir():
        return [Image.open(p).convert("RGB") for p in sorted(store.glob("*.png"))]
    frames = _decode_frames(video, n, up_side)
    if store:
        tmp = store.with_name(store.name + ".tmp")
        tmp.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(frames):
            f.save(tmp / f"{i:04d}.png")
        tmp.rename(store)
    return frames


def _frames_dir(video: Path, n: int, up_side: str) -> Path | None:
    root = os.environ.get(FRAMES_CACHE_ENV)
    if not root:
        return None
    h = hashlib.sha1()
    with open(video, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return Path(root) / f"{video.stem}_{h.hexdigest()[:12]}_{n}_{up_side}_{FRAME_LONG_SIDE}"


def _decode_frames(video: Path, n: int, up_side: str) -> list[Image.Image]:
    rotate = TRANSPOSE[up_side]
    scale = f"scale='if(gt(iw,ih),{FRAME_LONG_SIDE},-2)':'if(gt(iw,ih),-2,{FRAME_LONG_SIDE})'"
    vf = ",".join(f for f in (rotate, scale) if f)
    frames = []
    for t in np.linspace(0.5, duration(video) - 0.5, n):
        png = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1"]
            + ["-vf", vf, "-f", "image2pipe", "-vcodec", "png", "-"],
            capture_output=True,
            check=True,
        ).stdout
        if png:
            from io import BytesIO

            frames.append(Image.open(BytesIO(png)).convert("RGB"))
    return frames


def estimate_up(points: np.ndarray, cam_poses: np.ndarray, voxel: float = 0.04) -> np.ndarray:
    """Unit up vector of a reconstruction (OpenCV cam-to-world poses, upright frames)."""
    up = -cam_poses[:, :3, 1].mean(axis=0)
    up /= np.linalg.norm(up)
    p = voxel_downsample(points, voxel)
    _, nb = cKDTree(p).query(p, k=NORMAL_NEIGHBOURS)
    local = p[nb] - p[nb].mean(axis=1, keepdims=True)
    var, vec = np.linalg.eigh(np.einsum("nki,nkj->nij", local, local))
    normals = vec[:, :, 0]
    planar = var[:, 0] / (var.sum(axis=1) + 1e-12) < PLANAR_MAX
    seed = up
    for _ in range(4):
        wall = planar & (np.abs(normals @ up) < np.sin(np.radians(WALL_BAND_DEG)))
        m = normals[wall]
        if len(m) < 100:
            break
        _, evec = np.linalg.eigh(m.T @ m)
        up = evec[:, 0] * np.sign(evec[:, 0] @ seed)
    return up


def z_up(points: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Rotate points so `up` becomes +z (rotation about the axis up x z)."""
    z = np.array([0.0, 0.0, 1.0])
    axis = np.cross(up, z)
    s, c = np.linalg.norm(axis), float(up @ z)
    if s < 1e-9:
        return points if c > 0 else points * [1, -1, -1]
    k = axis / s
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    rot = np.eye(3) + s * kx + (1 - c) * kx @ kx
    return points @ rot.T


def _gray(video: Path, t: float, w: int = 160, h: int = 120) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-noautorotate", "-ss", f"{t:.3f}", "-i", str(video)]
        + ["-frames:v", "1", "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, np.uint8)[: w * h].reshape(h, w).astype(float)


def _run(cmd: list[str]):
    def call(video: Path) -> str:
        return subprocess.run(cmd + [str(video)], capture_output=True, text=True, check=True).stdout

    return call
