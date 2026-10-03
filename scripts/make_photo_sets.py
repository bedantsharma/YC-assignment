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

`--protocol` selects like a person following docs/capture_protocol.md instead (stand near
a corner or wall, point across the room): per room, sharp frames taken away from the
room's middle and facing towards it, with headings spread round the room. Uses the same
ARKit poses, again only to build the test input. Output folder k<K>p.

Output: data/home_c/photos_sim/<capture>/k<K>[p]/<room>/<NN>.jpg + manifest.json.
Usage: uv run scripts/make_photo_sets.py c_home_01 c_damage_01 --k 8 [--protocol]
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
MIN_TURN = np.radians(20)  # protocol picks: no two within 20 deg of heading ...
MIN_STEP = 0.5  # ... and 0.5 m of position
MAX_TILT = np.radians(30)  # protocol picks: camera within 30 deg of level


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
    ap.add_argument("--protocol", action="store_true", help="corner/wall shots facing in")
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
        poses = load_lidar(src).poses
        pidx = np.clip((times * FPS).round().astype(int), 0, len(poses) - 1)
        cam_xy, view_xy = poses[pidx, :2, 3], poses[pidx, :2, 2]  # OpenCV: column 2 = forward
        level = np.abs(poses[pidx, 2, 2]) < np.sin(MAX_TILT)  # protocol photos are held level
        tag = f"k{args.k}" + ("p" if args.protocol else "")

        manifest = {"capture": cap, "k": args.k, "up_side": up, "rooms": {}}
        for r in sorted(set(room) - {""}):
            ts = times[room == r]
            if len(ts) / PROBE_FPS < MIN_ROOM_S:
                continue
            sh = sharp[room == r]
            if args.protocol:
                m = room == r
                picks = _protocol_picks(cam_xy[m], view_xy[m], np.where(level[m], sh, 0.0), args.k)
            else:
                picks = [int(np.argmax(s)) + int(sl[0]) for sl, s in _slots(sh, args.k)]
            chosen = sorted(float(ts[i]) for i in picks)
            for j, t in enumerate(chosen):
                save_frame(video, t, up, args.out / cap / tag / r / f"{j:02d}.jpg")
            manifest["rooms"][r] = {"seconds_in_room": len(ts) / PROBE_FPS, "times": chosen}
            print(f"{cap} {r}: {len(ts) / PROBE_FPS:.0f} s in room, {len(chosen)} photos")
        (args.out / cap / tag / "manifest.json").write_text(json.dumps(manifest, indent=2))


def _protocol_picks(cam: np.ndarray, view: np.ndarray, sharp: np.ndarray, k: int) -> list[int]:
    """Frames taken away from the room's middle, facing into it, headings spread out."""
    centre = cam.mean(axis=0)
    out = centre - cam
    dist = np.linalg.norm(out, axis=1)
    facing = np.einsum("ij,ij->i", view, out) / (np.linalg.norm(view, axis=1) * dist + 1e-9)
    ok = (facing > 0.3) & (sharp > 0) & (sharp >= np.median(sharp[sharp > 0]))
    score = np.where(ok, dist * facing, -np.inf)
    heading = np.arctan2(view[:, 1], view[:, 0])
    picks: list[int] = []
    # headings spread round the room; relaxed if the walk gives too few, but never a near
    # duplicate (within MIN_TURN of heading and MIN_STEP of position of an earlier pick)
    for gap in (0.7 * 2 * np.pi / k, 0.35 * 2 * np.pi / k, MIN_TURN):
        for i in np.argsort(-score):
            if len(picks) == k or not np.isfinite(score[i]):
                break
            if picks:
                turn = np.abs(np.angle(np.exp(1j * (heading[i] - heading[picks]))))
                step = np.linalg.norm(cam[picks] - cam[i], axis=1)
                if turn.min() < gap or ((turn < MIN_TURN) & (step < MIN_STEP)).any():
                    continue
            picks.append(int(i))
        if len(picks) == k:
            break
    return picks


def _slots(values: np.ndarray, k: int):
    """k contiguous index slots over values: (index array, values in slot)."""
    for sl in np.array_split(np.arange(len(values)), min(k, len(values))):
        yield sl, values[sl]


if __name__ == "__main__":
    main()
