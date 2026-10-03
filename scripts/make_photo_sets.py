"""Simulated photo folders (one folder per room) from a dataset-C recording's video.

The friend sent no photos, so the photo tier is developed on stills taken from C's
`rgb.mp4` (fallback in docs/data_plan.md). This builds the test input; it is not part of
the photo tier, which only ever sees the images and the folder names.

Room of each frame: the camera position (ARKit pose of the same recording) inside the
user's hand-drawn room rectangles (data/gt/home_c_rooms.json, LiDAR plan frame). Single-room
recordings go into one folder. Per room, the room's frames are split into K equal time
slots and the sharpest frame of each slot (variance of the Laplacian) is kept, like a
person taking K photos while walking around. Frames are upright (same orientation rule as
the video tier), 960 px on the long side.

Output: data/home_c/photos_sim/<capture>/k<K>/<room>/<NN>.jpg + manifest.json.
Usage: uv run scripts/make_photo_sets.py c_home_01 c_damage_01 --k 8
"""

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from scipy.ndimage import laplace

from floorplan.capture import load_lidar
from floorplan.plan2d import Grid
from floorplan.video import FRAME_LONG_SIDE, TRANSPOSE, duration, orientation

FPS = 60  # Stray rgb.mp4: frame index = time * 60 = pose index
PROBE_FPS = 4
PROBE_W, PROBE_H = 160, 120
LABEL_ROTATION_DEG = 89.55  # plan frame the room labels were drawn in (see the labels file)
MIN_ROOM_S = 3.0  # rooms the camera passed through for less than this get no folder


def probe(video: Path) -> np.ndarray:
    """Grayscale thumbnails at PROBE_FPS for the whole video, in stored orientation."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-noautorotate", "-i", str(video)]
        + ["-vf", f"fps={PROBE_FPS},scale={PROBE_W}:{PROBE_H},format=gray"]
        + ["-f", "rawvideo", "-"],
        capture_output=True,
        check=True,
    ).stdout
    n = len(raw) // (PROBE_W * PROBE_H)
    return np.frombuffer(raw[: n * PROBE_W * PROBE_H], np.uint8).reshape(n, PROBE_H, PROBE_W)


def sharpness(thumbs: np.ndarray) -> np.ndarray:
    return np.array([laplace(t.astype(float)).var() for t in thumbs])


def rooms_at(src: Path, times: np.ndarray, labels: dict | None) -> list[str]:
    if labels is None:
        return ["room"] * len(times)
    poses = load_lidar(src).poses
    idx = np.clip((times * FPS).round().astype(int), 0, len(poses) - 1)
    grid = Grid(labels["plan_rotation_deg"], np.zeros(2), 1.0, (1, 1))
    uv = grid.to_plan(poses[idx, :2, 3])
    out = []
    for u, v in uv:
        boxes = labels["rooms"].items()
        hit = [r for r, (x0, y0, x1, y1) in boxes if x0 <= u <= x1 and y0 <= v <= y1]
        out.append(hit[0] if hit else "")
    return out


def save_frame(video: Path, t: float, up_side: str, path: Path) -> None:
    rotate = TRANSPOSE[up_side]
    scale = f"scale='if(gt(iw,ih),{FRAME_LONG_SIDE},-2)':'if(gt(iw,ih),-2,{FRAME_LONG_SIDE})'"
    vf = ",".join(f for f in (rotate, scale) if f)
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1"]
        + ["-vf", vf, "-q:v", "2", str(path)],
        check=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("captures", nargs="+")
    ap.add_argument("--k", type=int, default=8, help="photos per room")
    ap.add_argument("--out", type=Path, default=Path("data/home_c/photos_sim"))
    args = ap.parse_args()

    gt = json.loads(Path("data/gt/home_c_rooms.json").read_text())
    for cap in args.captures:
        src = Path("data/home_c/lidar") / cap
        video = src / "rgb.mp4"
        up = orientation(video).up_side
        thumbs = probe(video)
        times = np.arange(len(thumbs)) / PROBE_FPS
        keep = times < duration(video) - 0.5
        times, sharp = times[keep], sharpness(thumbs[keep])
        labels = None
        if gt["capture"] == cap:
            labels = {"rooms": gt["rooms"], "plan_rotation_deg": LABEL_ROTATION_DEG}
        room = np.array(rooms_at(src, times, labels))

        manifest = {"capture": cap, "k": args.k, "up_side": up, "rooms": {}}
        for r in sorted(set(room) - {""}):
            ts = times[room == r]
            if len(ts) / PROBE_FPS < MIN_ROOM_S:
                continue
            sh = sharp[room == r]
            picks = [int(np.argmax(s)) + int(sl[0]) for sl, s in _slots(sh, args.k)]
            chosen = sorted(float(ts[i]) for i in picks)
            for j, t in enumerate(chosen):
                save_frame(video, t, up, args.out / cap / f"k{args.k}" / r / f"{j:02d}.jpg")
            manifest["rooms"][r] = {"seconds_in_room": len(ts) / PROBE_FPS, "times": chosen}
            print(f"{cap} {r}: {len(ts) / PROBE_FPS:.0f} s in room, {len(chosen)} photos")
        (args.out / cap / f"k{args.k}" / "manifest.json").write_text(json.dumps(manifest, indent=2))


def _slots(values: np.ndarray, k: int):
    """k contiguous index slots over values: (index array, values in slot)."""
    for sl in np.array_split(np.arange(len(values)), min(k, len(values))):
        yield sl, values[sl]


if __name__ == "__main__":
    main()
