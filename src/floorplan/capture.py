"""Detect what kind of capture a path holds and load it in one common frame.

Common frame for all LiDAR sources: metres, **z up**, poses are camera-to-world 4x4 matrices
acting on OpenCV camera coordinates (x right, y down, z forward), intrinsics at the depth
image resolution.

Isolation rule (docs/data_plan.md): video and photo captures carry only file paths, so the
video and photo tiers can never read depth, poses or intrinsics from a LiDAR recording.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation

VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v"}
PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
TIERS_BY_FORMAT = {  # first entry is the default tier
    "stray": ("lidar", "video"),
    "arkitscenes": ("lidar", "video"),
    "video": ("video",),
    "photos": ("photo",),
}
STRAY_RGB_SIZE = (1920, 1440)  # odometry.csv intrinsics refer to this resolution
ARKIT_MAX_POSE_GAP_S = 0.01  # depth frame must lie within 10 ms of a pose sample

# Stray Scanner / ARKit world is y-up; rotate so y -> z (x stays, z -> -y)
_Y_UP_TO_Z_UP = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)


@dataclass
class LidarCapture:
    depth_paths: list[Path]  # 16-bit PNG, millimetres
    confidence_paths: list[Path]  # 8-bit PNG, 0 = low, 2 = high
    poses: np.ndarray  # (N, 4, 4) camera-to-world, z up
    intrinsics: np.ndarray  # (N, 3, 3) at depth resolution


@dataclass
class VideoCapture:
    path: Path


@dataclass
class PhotoCapture:
    rooms: dict[str, list[Path]]  # room name -> photos, in name order


def detect_format(path: Path | str) -> str:
    path = Path(path)
    if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES:
        return "video"
    if path.is_dir():
        if (path / "odometry.csv").exists() and (path / "depth").is_dir():
            return "stray"
        if (path / "lowres_wide.traj").exists() and (path / "lowres_depth").is_dir():
            return "arkitscenes"
        if _photo_rooms(path):
            return "photos"
    raise ValueError(f"not a recognised capture: {path}")


def resolve_tier(fmt: str, tier: str | None) -> str:
    available = TIERS_BY_FORMAT[fmt]
    if tier is None:
        return available[0]
    if tier not in available:
        raise ValueError(
            f"{tier} tier is not available from a {fmt} capture (available: {available})"
        )
    return tier


def load_lidar(path: Path | str, stride: int = 1) -> LidarCapture:
    path = Path(path)
    fmt = detect_format(path)
    if fmt == "stray":
        cap = _load_stray(path)
    elif fmt == "arkitscenes":
        cap = _load_arkitscenes(path)
    else:
        raise ValueError(f"{fmt} capture has no LiDAR data: {path}")
    if stride > 1:
        cap = LidarCapture(
            cap.depth_paths[::stride],
            cap.confidence_paths[::stride],
            cap.poses[::stride],
            cap.intrinsics[::stride],
        )
    return cap


def load_video(path: Path | str) -> VideoCapture:
    path = Path(path)
    fmt = detect_format(path)
    if fmt == "video":
        return VideoCapture(path)
    if fmt == "stray":
        return VideoCapture(path / "rgb.mp4")
    if fmt == "arkitscenes":
        return VideoCapture(path / f"{path.name}.mov")
    raise ValueError(f"{fmt} capture has no video: {path}")


def load_photos(path: Path | str) -> PhotoCapture:
    rooms = _photo_rooms(Path(path))
    if not rooms:
        raise ValueError(f"no photos found: {path}")
    return PhotoCapture(rooms)


def _photo_rooms(path: Path) -> dict[str, list[Path]]:
    def photos_in(d: Path) -> list[Path]:
        return sorted(
            p for p in d.iterdir() if p.suffix.lower() in PHOTO_SUFFIXES and not _hidden(p)
        )

    rooms = {d.name: photos_in(d) for d in sorted(path.iterdir()) if d.is_dir() and not _hidden(d)}
    rooms = {name: photos for name, photos in rooms.items() if photos}
    if not rooms and photos_in(path):
        rooms = {path.name: photos_in(path)}
    return rooms


def _load_stray(path: Path) -> LidarCapture:
    with open(path / "odometry.csv") as f:
        rows = [[c.strip() for c in r] for r in list(csv.reader(f))[1:] if r]
    depth_w, depth_h = Image.open(path / "depth" / f"{rows[0][1]}.png").size
    sx, sy = depth_w / STRAY_RGB_SIZE[0], depth_h / STRAY_RGB_SIZE[1]

    depth, conf, poses, intr = [], [], [], []
    for r in rows:
        frame = r[1]
        x, y, z, qx, qy, qz, qw, fx, fy, cx, cy = (float(v) for v in r[2:13])
        pose = np.eye(4)
        pose[:3, :3] = Rotation.from_quat([qx, qy, qz, qw]).as_matrix()
        pose[:3, 3] = [x, y, z]
        poses.append(_Y_UP_TO_Z_UP @ pose)
        intr.append([[fx * sx, 0, cx * sx], [0, fy * sy, cy * sy], [0, 0, 1]])
        depth.append(path / "depth" / f"{frame}.png")
        conf.append(path / "confidence" / f"{frame}.png")
    return LidarCapture(depth, conf, np.array(poses), np.array(intr))


def _load_arkitscenes(path: Path) -> LidarCapture:
    depth_files = sorted((path / "lowres_depth").glob("*.png"))
    stamps = np.array([float(p.stem.split("_")[1]) for p in depth_files])
    traj = np.atleast_2d(np.loadtxt(path / "lowres_wide.traj"))

    depth, conf, poses, intr = [], [], [], []
    for t, *rotvec_and_t in traj:
        j = int(np.argmin(np.abs(stamps - t)))
        if abs(stamps[j] - t) > ARKIT_MAX_POSE_GAP_S:
            continue
        world_to_cam = np.eye(4)
        world_to_cam[:3, :3] = Rotation.from_rotvec(rotvec_and_t[:3]).as_matrix()
        world_to_cam[:3, 3] = rotvec_and_t[3:]
        poses.append(np.linalg.inv(world_to_cam))

        stem = depth_files[j].stem
        _, _, fx, fy, cx, cy = np.loadtxt(path / "lowres_wide_intrinsics" / f"{stem}.pincam")
        intr.append([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
        depth.append(depth_files[j])
        conf.append(path / "confidence" / f"{stem}.png")
    return LidarCapture(depth, conf, np.array(poses), np.array(intr))


def _hidden(p: Path) -> bool:
    """macOS metadata, not captures: '._IMG_1.jpg' (AppleDouble files that a Mac adds to a
    zip or a non-Mac disk) and the '__MACOSX' folder of a zip made on a Mac."""
    return p.name.startswith(".") or p.name == "__MACOSX"


INCOMING = Path("outputs/incoming")


def unpack(path: Path | str, into: Path = INCOMING) -> Path:
    """A zipped capture (how Stray Scanner recordings are shared) -> the capture inside it,
    extracted once to into/<zip name>/. Anything that is not a .zip is returned as is.
    Inside, the capture is the first folder (shallowest) holding a LiDAR recording, else
    the first video file, else the extracted folder itself (photo folders)."""
    import zipfile

    path = Path(path)
    if not (path.is_file() and path.suffix.lower() == ".zip"):
        return path
    out = into / path.stem
    if not out.exists():
        tmp = out.with_name(out.name + ".tmp")
        with zipfile.ZipFile(path) as z:
            z.extractall(tmp)
        tmp.rename(out)
    shown = [q for q in out.rglob("*") if not any(map(_hidden, q.relative_to(out).parents))]
    shown = [q for q in shown if not _hidden(q)]
    recordings = [
        d for d in shown
        if d.is_dir() and ((d / "odometry.csv").exists() or (d / "lowres_wide.traj").exists())
    ]  # fmt: skip
    if recordings:
        return min(recordings, key=lambda d: len(d.parts))
    videos = sorted(
        (f for f in shown if f.suffix.lower() in VIDEO_SUFFIXES), key=lambda f: len(f.parts)
    )
    if videos:
        return videos[0]
    inner = [d for d in out.iterdir() if d.is_dir() and not _hidden(d)]
    loose = [f for f in out.iterdir() if f.is_file() and not _hidden(f)]
    return inner[0] if len(inner) == 1 and not loose else out
