"""Photo-tier bake-off on Kaggle: the same photo folders through each metric multi-view model.

Runs remotely (kaggle kernels push), so the multi-GB weights never touch the laptop.
Input: private dataset bedantsharma/floorplan-photos-c: simulated photo folders (8 sharp
stills per room from dataset C's videos, scripts/make_photo_sets.py), one folder per room.
Output, per capture, model and photo count: points (voxel-thinned, metres, model frame),
camera poses (cam-to-world, OpenCV) and the photo names in input order. Scored locally
against the LiDAR of the same recording (never uploaded).

Runs: {Pi3X, MapAnything, DA3-nested} x {damage room scan 1 and 2: 8 and 4 photos;
whole home: 8 and 4 photos per room, all rooms in one pass}.
"""

import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

MAPANYTHING = (
    "git+https://github.com/facebookresearch/map-anything@3d10cf7a3016fc0f9bb13a071ee66c47b10be0d9"
)
# Fail fast with a clear message when the session has no GPU (CPU image = CPU-only torch)
subprocess.run("nvidia-smi -L || echo NO nvidia-smi", shell=True)
subprocess.run(
    [
        sys.executable,
        "-c",
        "import torch; print('preinstalled torch', torch.__version__, torch.cuda.is_available())",
    ]
)

DA3 = "git+https://github.com/Nik-V9/depth-anything-3.git@main"
pip = [sys.executable, "-m", "pip", "install", "-q"]
# Install from a clone: external models (DA3, Pi3X) load Hydra configs that live in the
# repo's configs/ directory, which a plain pip install does not ship.
REPO = Path("/kaggle/tmp/map-anything")
subprocess.run(
    ["git", "clone", "-q", "https://github.com/facebookresearch/map-anything", str(REPO)],
    check=True,
)
subprocess.run(
    ["git", "-C", str(REPO), "checkout", "-q", MAPANYTHING.rsplit("@", 1)[1]], check=True
)
subprocess.run([*pip, "-e", f"{REPO}[pi3]"], check=True)
# an editable install made inside this process is not on its import path yet
sys.path.insert(0, str(REPO))
# DA3's package declares python <= 3.13; Kaggle runs 3.13.15. Not fatal: run without DA3.
DA3_OK = (
    subprocess.run([*pip, "--ignore-requires-python", f"depth-anything-3 @ {DA3}"]).returncode == 0
)
# DA3 imports addict on its load path (utils/registry.py, model/da3.py) without declaring it
DA3_OK = DA3_OK and subprocess.run([*pip, "addict"]).returncode == 0

import numpy as np  # noqa: E402
import torch  # noqa: E402

OUT = Path("/kaggle/working")
INPUT = Path("/kaggle/input")
LOG = OUT / "log.txt"
VOXEL = 0.02
CONF_PERCENTILE = 10  # same filter as the video tier (drop the least confident 10%)
# T4 (sm75) has no memory-efficient attention for bf16: SDPA falls back to the full
# attention matrix. fp16 keeps the efficient kernel there.
AMP = "bf16" if torch.cuda.is_available() and torch.cuda.get_device_capability()[0] >= 8 else "fp16"
AMP_DTYPE = torch.bfloat16 if AMP == "bf16" else torch.float16


def log(msg: str) -> None:
    print(msg, flush=True)
    with LOG.open("a") as f:
        f.write(msg + "\n")


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


def collect(preds, use_mask: bool):
    pts, poses, view = [], [], []
    for i, p in enumerate(preds):
        xyz = p["pts3d"][0].float().cpu().numpy().reshape(-1, 3)
        keep = np.isfinite(xyz).all(axis=1)
        if use_mask and "mask" in p:
            keep &= p["mask"][0].cpu().numpy().reshape(-1).astype(bool)
        elif "conf" in p:
            conf = p["conf"][0].float().cpu().numpy().reshape(-1)
            keep &= conf >= np.percentile(conf[keep], CONF_PERCENTILE)
        thin = voxel_thin(xyz[keep])
        pts.append(thin)
        view.append(np.full(len(thin), i, np.int16))
        if "camera_poses" in p:
            poses.append(p["camera_poses"][0].float().cpu().numpy())
        else:
            poses.append(to_pose(p["cam_trans"], p["cam_quats"]))
    return np.concatenate(pts), np.concatenate(view), np.stack(poses)


def load_model(name: str):
    if name == "mapanything":
        from mapanything.models import MapAnything

        return MapAnything.from_pretrained("facebook/map-anything-apache").to("cuda")
    from mapanything.models import init_model_from_config

    return init_model_from_config(name, device="cuda")


def infer(name: str, model, frames: list[Path]):
    from mapanything.utils.image import load_images

    if name == "mapanything":
        views = load_images([str(f) for f in frames])
        start = time.perf_counter()
        preds = model.infer(
            views,
            memory_efficient_inference=True,
            use_amp=True,
            amp_dtype=AMP,
            apply_mask=True,
            mask_edges=True,
            apply_confidence_mask=True,
            confidence_percentile=CONF_PERCENTILE,
        )
        return preds, time.perf_counter() - start, True
    res, norm = {"da3_nested": (504, "dinov2"), "pi3x": (518, "identity")}[name]
    views = load_images([str(f) for f in frames], resolution_set=res, norm_type=norm, patch_size=14)
    for v in views:
        for k, x in v.items():
            if torch.is_tensor(x):
                v[k] = x.to("cuda")
    start = time.perf_counter()
    with torch.no_grad(), torch.autocast("cuda", dtype=AMP_DTYPE):
        preds = model(views)
    return preds, time.perf_counter() - start, False


def photo_sets() -> dict[str, list[Path]]:
    """tag -> photo paths. k8 folders hold 8 photos per room; k4 = every other one."""
    sets = {}
    for manifest in sorted(INPUT.rglob("manifest.json")):
        cap = manifest.parent.parent.name
        rooms = sorted(p for p in manifest.parent.iterdir() if p.is_dir())
        for k in (8, 4):
            step = 8 // k
            sets[f"{cap}__{k}"] = [f for r in rooms for f in sorted(r.glob("*.jpg"))[::step]]
    return sets


def main() -> None:
    if not torch.cuda.is_available():
        log(f"NO GPU in this session (torch {torch.__version__}); nothing to run")
        sys.exit(1)
    log(
        f"torch {torch.__version__}, GPU {torch.cuda.get_device_name(0)}, "
        f"DA3 installed {DA3_OK}, amp {AMP}"
    )
    sets = photo_sets()
    log("sets: " + ", ".join(f"{t} ({len(f)})" for t, f in sets.items()))
    rows = []
    for name in ["pi3x", "mapanything", "da3_nested"]:
        torch.cuda.empty_cache()
        try:
            model = load_model(name)
        except Exception:
            log(f"FAILED loading {name}:\n{traceback.format_exc()}")
            continue
        for tag, frames in sets.items():
            cap, k = tag.split("__")
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            try:
                preds, seconds, use_mask = infer(name, model, frames)
                pts, view, poses = collect(preds, use_mask)
                names = np.array([f"{f.parent.name}/{f.name}" for f in frames])
                out = OUT / f"{cap}__{name}__k{k}.npz"
                np.savez_compressed(
                    out, points=pts.astype(np.float32), view=view, poses=poses, names=names
                )
                row = {
                    "tag": out.stem,
                    "photos": len(frames),
                    "seconds": round(seconds, 1),
                    "peak_gpu_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2),
                    "points": len(pts),
                }
                rows.append(row)
                log(json.dumps(row))
                del preds
            except Exception:
                log(f"FAILED {tag} {name}:\n{traceback.format_exc()}")
        del model
    (OUT / "summary.json").write_text(json.dumps(rows, indent=2))
    log("done")


main()
