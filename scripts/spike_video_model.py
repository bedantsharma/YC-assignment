"""Spike: run a pretrained multi-view model on N frames of a LiDAR recording's RGB video and
compare its geometry with the same recording's LiDAR.

The model sees only RGB frames. LiDAR is used afterwards, for evaluation only:
- trajectory: similarity fit of predicted camera centres to ARKit's gives the model's scale
  error (metric models should give s ~ 1) and the residual trajectory error;
- frame: the model's cloud is rotated to z up with the fit's rotation and translation but
  NOT its scale, so the room plan below measures the model's own metric scale;
- plan: that cloud goes through the LiDAR tier's geometry backend (`build_plan`).

Runs in a separate venv with the model installed (heavy, not a project dependency yet):
  <venv>/bin/python scripts/spike_video_model.py data/home_c/lidar/c_damage_01 --model mapanything
"""

import argparse
import json
import subprocess
import time
from pathlib import Path

import numpy as np
import torch
from scipy.spatial import cKDTree

from floorplan.capture import load_lidar
from floorplan.cloud import fuse, voxel_downsample
from floorplan.lidar import build_plan
from floorplan.output import Capture, Result, write_json
from floorplan.render import render_plan

FPS = 60  # Stray Scanner rgb.mp4


def extract_frames(video: Path, indices: list[int], out: Path, rotate: bool) -> list[Path]:
    """rotate: turn 90 deg clockwise (Stray stores portrait captures sideways)."""
    vf = "transpose=1,scale=720:960" if rotate else "scale=960:720"
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for k, i in enumerate(indices):
        p = out / f"f_{k:03d}_{i:05d}.jpg"
        if not p.exists():
            subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{i / FPS:.4f}", "-i", str(video)]
                + ["-frames:v", "1", "-vf", vf, "-q:v", "2", str(p)],
                check=True,
            )
        if not p.exists():
            raise RuntimeError(f"ffmpeg produced no frame {i} from {video}")
        paths.append(p)
    return paths


def umeyama(src: np.ndarray, dst: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """s, R, t minimising |dst - (s R src + t)|."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    a, b = src - mu_s, dst - mu_d
    u, d, vt = np.linalg.svd(b.T @ a / len(src))
    sign = np.eye(3)
    sign[2, 2] = np.sign(np.linalg.det(u @ vt))
    r = u @ sign @ vt
    s = np.trace(np.diag(d) @ sign) / a.var(0).sum()
    return s, r, mu_d - s * r @ mu_s


def device_intrinsics(width: int, height: int, focal35: float) -> np.ndarray:
    """Pinhole K from a 35 mm-equivalent focal length (Apple's published lens spec)."""
    f = focal35 * np.hypot(width, height) / np.hypot(36.0, 24.0)
    return np.array([[f, 0, width / 2], [0, f, height / 2], [0, 0, 1]], np.float32)


def run_model(
    name: str, paths: list[Path], device: str, focal35: float | None
) -> tuple[list[dict], float]:
    from mapanything.utils.image import load_images, preprocess_inputs
    from PIL import Image

    if name == "mapanything":
        from mapanything.models import MapAnything

        model = MapAnything.from_pretrained("facebook/map-anything-apache").to(device)
        if focal35:
            views = []
            for p in paths:
                img = Image.open(p).convert("RGB")
                k = torch.from_numpy(device_intrinsics(*img.size, focal35))
                views.append({"img": torch.from_numpy(np.asarray(img)), "intrinsics": k})
            views = preprocess_inputs(views)
        else:
            views = load_images([str(p) for p in paths])
        start = time.perf_counter()
        preds = model.infer(
            views,
            memory_efficient_inference=True,
            use_amp=True,
            amp_dtype="bf16",
            apply_mask=True,
            mask_edges=True,
            apply_confidence_mask=True,
            confidence_percentile=10,
        )
        return preds, time.perf_counter() - start
    raise ValueError(f"unknown model {name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("capture", type=Path)
    ap.add_argument("--model", default="mapanything")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--out", type=Path, default=Path("outputs/spike"))
    ap.add_argument("--rotate", action="store_true", help="frames 90 deg clockwise (upright)")
    ap.add_argument("--focal35", type=float, help="give the model this 35 mm-equivalent focal")
    args = ap.parse_args()

    lidar = load_lidar(args.capture)
    n_frames = len(lidar.depth_paths)
    indices = np.linspace(0, n_frames - 2, args.n)  # last frame may not decode
    indices = indices.round().astype(int).tolist()
    tag = ("_upright" if args.rotate else "") + (f"_f{args.focal35:g}" if args.focal35 else "")
    out = args.out / f"{args.capture.name}_{args.model}_{args.n}{tag}"
    paths = extract_frames(args.capture / "rgb.mp4", indices, out / "frames", args.rotate)

    raw = out / "predictions.npz"
    if raw.exists():
        saved = np.load(raw)
        cams, pts, infer_s = saved["cams"], saved["pts"], float(saved["infer_s"])
        intr = saved["intrinsics"]
    else:
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        preds, infer_s = run_model(args.model, paths, device, args.focal35)
        cams = np.stack([p["camera_poses"][0].float().cpu().numpy() for p in preds])
        intr = np.stack([p["intrinsics"][0].float().cpu().numpy() for p in preds])
        pts = []
        for p in preds:
            xyz = p["pts3d"][0].float().cpu().numpy().reshape(-1, 3)
            mask = p["mask"][0].cpu().numpy().reshape(-1).astype(bool)
            pts.append(xyz[mask])
        pts = np.concatenate(pts)
        np.savez(raw, cams=cams, pts=pts, intrinsics=intr, infer_s=infer_s)

    # Evaluation only: ARKit camera centres for the same frames
    ref = lidar.poses[indices]
    s, r, t = umeyama(cams[:, :3, 3], ref[:, :3, 3])
    fit = s * cams[:, :3, 3] @ r.T + t
    ate = np.linalg.norm(fit - ref[:, :3, 3], axis=1)
    path_len = np.linalg.norm(np.diff(ref[:, :3, 3], axis=0), axis=1).sum()

    # z-up frame with rotation + translation only: keep the model's own scale
    t_rigid = ref[:, :3, 3].mean(0) - r @ cams[:, :3, 3].mean(0)
    world = voxel_downsample(pts @ r.T + t_rigid, 0.02)
    world_sim = voxel_downsample(pts * s @ r.T + t, 0.02)

    # Cloud-to-cloud after the similarity fit (geometry quality independent of scale)
    lidar_sub = load_lidar(args.capture, stride=max(1, n_frames // 300))
    ref_cloud = fuse(lidar_sub, voxel=0.02)
    d_model_to_lidar, _ = cKDTree(ref_cloud).query(world_sim, k=1)

    plan = build_plan(world)
    result = Result(
        capture=Capture(args.capture.name, tier="video", source=str(args.capture)),
        rooms=plan.rooms,
        footprint_area=plan.footprint_area,
        plan_rotation_deg=plan.rotation_deg,
        timing_s={"inference": round(infer_s, 1)},
        warnings=[f"spike: {args.model} on {args.n} frames; z-up frame from ARKit poses"]
        + plan.warnings,
    )
    write_json(result, out / "plan.json")
    render_plan(result, out / "plan.png")
    np.save(out / "cloud_model_scale.npy", world)

    summary = {
        "model": args.model,
        "frames": args.n,
        "intrinsics_fx_median": round(float(np.median(intr[:, 0, 0])), 1),
        "inference_s": round(infer_s, 1),
        "scale_to_arkit": round(float(s), 4),
        "ate_median_m": round(float(np.median(ate)), 3),
        "ate_max_m": round(float(ate.max()), 3),
        "arkit_path_len_m": round(float(path_len), 2),
        "cloud_to_lidar_median_m": round(float(np.median(d_model_to_lidar)), 3),
        "cloud_to_lidar_p90_m": round(float(np.percentile(d_model_to_lidar, 90)), 3),
        "rooms": [
            {
                "area": r_.floor_area.value,
                "ceiling": r_.ceiling_height.value if r_.ceiling_height else None,
                "walls": [round(w.length.value, 2) for w in r_.walls],
            }
            for r_ in plan.rooms
        ],
        "warnings": plan.warnings,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
