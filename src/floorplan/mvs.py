"""Multi-view reconstruction from RGB frames (metric scale, no poses needed).

Two models, chosen by the bake-off in docs/model_research.md:
- `pi3x` (default): Pi3X, cameras ~5x more accurate and walls closer on dataset C.
  Weights are CC BY-NC 4.0 (non-commercial).
- `mapanything`: MapAnything, Apache 2.0 weights; the commercial-safe fallback.

Optional dependency: `uv sync --extra video` (torch, MapAnything, Pi3; ~4-5 GB of weights per
model fetched from Hugging Face on first use).
"""

import hashlib
import os
import time
import warnings
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image

MODELS = {
    "pi3x": "yyfz233/Pi3X",  # CC BY-NC 4.0
    "mapanything": "facebook/map-anything-apache",  # Apache 2.0
}
DEFAULT_MODEL = "pi3x"
CONF_PERCENTILE = 10  # drop the least confident 10% of pixels (same as the bake-off)
# Directory of cached reconstructions, keyed by model + exact frame pixels: a GPU run
# (Kaggle) fills it, a laptop run replays it without loading the model. With
# FLOORPLAN_RECON_CACHE_ONLY=1 a cache miss is an error instead of a model run.
CACHE_ENV, CACHE_ONLY_ENV = "FLOORPLAN_RECON_CACHE", "FLOORPLAN_RECON_CACHE_ONLY"


@dataclass
class Reconstruction:
    view_points: np.ndarray  # (V, H, W, 3) metres, model's world frame (OpenCV axes)
    view_keep: np.ndarray  # (V, H, W) bool: finite and confident
    cam_poses: np.ndarray  # (V, 4, 4) camera-to-world, OpenCV convention
    seconds: float  # inference only, model load excluded
    model: str

    @property
    def points(self) -> np.ndarray:
        return self.view_points[self.view_keep]


def reconstruct(frames: list[Image.Image], model: str = DEFAULT_MODEL) -> Reconstruction:
    if model not in MODELS:
        raise ValueError(f"unknown model {model!r}; choose from {sorted(MODELS)}")
    cached = _cache_path(frames, model)
    if cached and cached.exists():
        z = np.load(cached)
        return Reconstruction(z["view_points"], z["view_keep"], z["cam_poses"],
                              float(z["seconds"]), model)  # fmt: skip
    if cached and os.environ.get(CACHE_ONLY_ENV) == "1":
        raise RuntimeError(f"no cached reconstruction {cached.name} ({CACHE_ONLY_ENV}=1)")
    rec = _infer(frames, model)
    if cached:
        cached.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cached, view_points=rec.view_points, view_keep=rec.view_keep,
                            cam_poses=rec.cam_poses, seconds=rec.seconds)  # fmt: skip
    return rec


def _cache_path(frames: list[Image.Image], model: str) -> Path | None:
    root = os.environ.get(CACHE_ENV)
    if not root:
        return None
    h = hashlib.sha1(model.encode())
    for f in frames:
        a = np.asarray(f)
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return Path(root) / f"{model}_{len(frames)}_{h.hexdigest()[:16]}.npz"


def _infer(frames: list[Image.Image], model: str) -> Reconstruction:
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    try:
        import torch
        from mapanything.utils.image import preprocess_inputs
    except ImportError as err:
        raise RuntimeError(
            "the video and photo tiers need the model: run `uv sync --extra video`"
        ) from err

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    if torch.cuda.is_available():
        device = "cuda"
    imgs = [{"img": torch.from_numpy(np.asarray(f))} for f in frames]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if model == "pi3x":
            views = preprocess_inputs(imgs, norm_type="identity", patch_size=14)
            return _pi3x(views, device)
        return _mapanything(preprocess_inputs(imgs), device)


@cache
def _load(model: str, device: str):
    """Load once per process: chunked runs call the model once per window."""
    if model == "mapanything":
        from mapanything.models import MapAnything

        return MapAnything.from_pretrained(MODELS["mapanything"]).to(device)
    import torch
    from pi3.models.pi3x import Pi3X

    net = Pi3X.from_pretrained(MODELS["pi3x"]).eval()
    net.disable_multimodal()  # RGB only: no intrinsics, depth or pose inputs
    # Pi3X turns autocast off for its heads only on CUDA; on MPS they would run in bf16 and
    # the camera head's SVD fails (MPS SVD is float32 only). Run the heads in float32.
    backbone_head = net.forward_head

    # On a 15 GB T4, 24 full-HD photos in one pass left no room for cuSOLVER to start
    # (CUSOLVER_STATUS_INTERNAL_ERROR in the camera head's SVD, hall photos, Oct 4): free the
    # cached blocks first and use MAGMA, which needs no cuSOLVER handle. U V^T is unique, so
    # the poses do not depend on the backend.
    if device == "cuda":
        torch.backends.cuda.preferred_linalg_library("magma")

    def forward_head(hidden, *args, **kwargs):
        if device == "cuda":
            torch.cuda.empty_cache()
        with torch.autocast(device, enabled=False):
            return backbone_head(hidden.float(), *args, **kwargs)

    net.forward_head = forward_head
    return net.to(device)


def _mapanything(views, device: str) -> Reconstruction:
    net = _load("mapanything", device)
    start = time.perf_counter()
    preds = net.infer(
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
    xyz = np.stack([p["pts3d"][0].float().cpu().numpy() for p in preds])
    keep = np.stack([p["mask"][0].cpu().numpy().astype(bool) for p in preds]).reshape(xyz.shape[:3])
    keep &= np.isfinite(xyz).all(axis=-1)
    poses = np.stack([p["camera_poses"][0].float().cpu().numpy() for p in preds])
    return Reconstruction(xyz, keep, poses, seconds, "mapanything")


def _pi3x(views, device: str) -> Reconstruction:
    import torch

    net = _load("pi3x", device)
    imgs = torch.stack([v["img"][0] for v in views])[None].to(device)  # (1, V, 3, H, W)
    # pre-Ampere GPUs (Kaggle T4) have no efficient bf16 attention: use fp16 there
    old_gpu = device == "cuda" and torch.cuda.get_device_capability()[0] < 8
    dtype = torch.float16 if old_gpu else torch.bfloat16
    start = time.perf_counter()
    with torch.no_grad(), torch.autocast(device, dtype=dtype):
        res = net(imgs=imgs)
    seconds = time.perf_counter() - start

    xyz = res["points"][0].float().cpu().numpy()
    conf = res["conf"][0, ..., 0].float().cpu().numpy()
    keep = np.isfinite(xyz).all(axis=-1)
    keep &= conf >= np.percentile(conf[keep], CONF_PERCENTILE)
    poses = res["camera_poses"][0].float().cpu().numpy()
    return Reconstruction(xyz, keep, poses, seconds, "pi3x")
