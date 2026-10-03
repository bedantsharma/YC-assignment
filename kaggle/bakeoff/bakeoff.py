"""Model bake-off on Kaggle: same upright frames through each metric multi-view model.

Runs remotely (kaggle kernels push), so the multi-GB weights never touch the laptop.
Input: private dataset bedantsharma/floorplan-home-c (dataset C's three rgb.mp4 and the
30 upright frames per recording that `floorplan run --tier video` uses). Output, per
capture and model: points (voxel-thinned, metres, model frame), camera poses
(cam-to-world, OpenCV), timing and peak GPU memory. Scored locally with
scripts/score_bakeoff.py against the LiDAR of the same recording (never uploaded).

Run A: 30 frames x {MapAnything (Apache), DA3-nested (CC BY-NC), Pi3X (CC BY-NC)}.
Run B: MapAnything on more frames of the whole video (90), which a 24 GB GPU allows.
"""

import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

MAPANYTHING = (
    "git+https://github.com/facebookresearch/map-anything@3d10cf7a3016fc0f9bb13a071ee66c47b10be0d9"
)
subprocess.run(
    [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-q",
        f"mapanything[pi3,depth-anything-3] @ {MAPANYTHING}",
    ],
    check=True,
)

import numpy as np  # noqa: E402
import torch  # noqa: E402

OUT = Path("/kaggle/working")
INPUT = Path("/kaggle/input")
LOG = OUT / "log.txt"
VOXEL = 0.02
CONF_PERCENTILE = 10  # same filter as the video tier (drop the least confident 10%)


def log(msg: str) -> None:
    print(msg, flush=True)
    with LOG.open("a") as f:
        f.write(msg + "\n")


def find(name: str) -> Path:
    hits = sorted(INPUT.rglob(name))
    if not hits:
        raise FileNotFoundError(name)
    return hits[0]


def voxel_thin(p: np.ndarray, voxel: float = VOXEL) -> np.ndarray:
    cells = np.floor(p / voxel).astype(np.int64)
    _, idx = np.unique(cells, axis=0, return_index=True)
    return p[idx]


def to_pose(trans, quat) -> np.ndarray:
    from mapanything.utils.geometry import quaternion_to_rotation_matrix

    r = quaternion_to_rotation_matrix(quat.float()).cpu().numpy()
    pose = np.eye(4)
    pose[:3, :3] = r[0]
    pose[:3, 3] = trans.float().cpu().numpy()[0]
    return pose


def collect(preds, use_mask: bool) -> tuple[np.ndarray, np.ndarray]:
    pts, poses = [], []
    for p in preds:
        xyz = p["pts3d"][0].float().cpu().numpy().reshape(-1, 3)
        keep = np.isfinite(xyz).all(axis=1)
        if use_mask and "mask" in p:
            keep &= p["mask"][0].cpu().numpy().reshape(-1).astype(bool)
        elif "conf" in p:
            conf = p["conf"][0].float().cpu().numpy().reshape(-1)
            keep &= conf >= np.percentile(conf[keep], CONF_PERCENTILE)
        pts.append(xyz[keep])
        if "camera_poses" in p:
            poses.append(p["camera_poses"][0].float().cpu().numpy())
        else:
            poses.append(to_pose(p["cam_trans"], p["cam_quats"]))
    return voxel_thin(np.concatenate(pts)), np.stack(poses)


def run_mapanything(frames: list[Path]):
    from mapanything.models import MapAnything
    from mapanything.utils.image import load_images

    model = MapAnything.from_pretrained("facebook/map-anything-apache").to("cuda")
    views = load_images([str(f) for f in frames])
    start = time.perf_counter()
    preds = model.infer(
        views,
        memory_efficient_inference=True,
        use_amp=True,
        amp_dtype="bf16",
        apply_mask=True,
        mask_edges=True,
        apply_confidence_mask=True,
        confidence_percentile=CONF_PERCENTILE,
    )
    seconds = time.perf_counter() - start
    del model
    return preds, seconds, True


def run_external(name: str, frames: list[Path], resolution: int, norm: str):
    from mapanything.models import init_model_from_config
    from mapanything.utils.image import load_images

    model = init_model_from_config(name, device="cuda")
    views = load_images(
        [str(f) for f in frames], resolution_set=resolution, norm_type=norm, patch_size=14
    )
    for v in views:
        for k, x in v.items():
            if torch.is_tensor(x):
                v[k] = x.to("cuda")
    start = time.perf_counter()
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        preds = model(views)
    seconds = time.perf_counter() - start
    del model
    return preds, seconds, False


MODELS = {
    "mapanything": lambda fr: run_mapanything(fr),
    "da3_nested": lambda fr: run_external("da3_nested", fr, 504, "dinov2"),
    "pi3x": lambda fr: run_external("pi3x", fr, 518, "identity"),
}


def save(tag: str, preds, seconds: float, use_mask: bool, n: int) -> dict:
    pts, poses = collect(preds, use_mask)
    np.savez_compressed(OUT / f"{tag}.npz", points=pts.astype(np.float32), poses=poses)
    row = {
        "tag": tag,
        "frames": n,
        "seconds": round(seconds, 1),
        "peak_gpu_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2),
        "points": len(pts),
    }
    log(json.dumps(row))
    return row


def extract(video: Path, n: int, out: Path) -> list[Path]:
    """n frames evenly over the video, turned upright (all C videos: up = stored left)."""
    out.mkdir(parents=True, exist_ok=True)
    dur = float(
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(video),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    paths = []
    for k, t in enumerate(np.linspace(0.5, dur - 0.5, n)):
        p = out / f"{k:03d}.jpg"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1"]
            + ["-vf", "transpose=1,scale=720:960", "-q:v", "2", str(p)],
            check=True,
        )
        if p.exists():
            paths.append(p)
    return paths


def main() -> None:
    log(f"torch {torch.__version__}, GPU {torch.cuda.get_device_name(0)}")
    info = json.loads(find("info.json").read_text())
    rows = []
    captures = ["c_damage_01", "c_damage_02", "c_home_01"]

    # Run A: identical 30 frames through each model
    for cap in captures:
        frames = sorted(find("info.json").parent.joinpath(cap).glob("*.jpg"))
        assert info[cap]["up_side"] == "left" and len(frames) == 30, (cap, len(frames))
        for name, fn in MODELS.items():
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            try:
                preds, seconds, use_mask = fn(frames)
                rows.append(save(f"{cap}__{name}__30", preds, seconds, use_mask, len(frames)))
                del preds
            except Exception:
                log(f"FAILED {cap} {name}:\n{traceback.format_exc()}")

    # Run B: MapAnything on more of the whole video
    for cap, n in [("c_damage_01", 90), ("c_home_01", 90)]:
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        try:
            frames = extract(find(f"{cap}.mp4"), n, OUT / "frames_b" / cap)
            preds, seconds, use_mask = run_mapanything(frames)
            rows.append(save(f"{cap}__mapanything__{n}", preds, seconds, use_mask, len(frames)))
            del preds
        except Exception:
            log(f"FAILED run B {cap}:\n{traceback.format_exc()}")

    (OUT / "summary.json").write_text(json.dumps(rows, indent=2))
    os.system(f"rm -rf {OUT / 'frames_b'}")
    log("done")


main()
