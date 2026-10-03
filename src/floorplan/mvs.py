"""Multi-view reconstruction from RGB frames (metric scale, no poses needed).

Two models, chosen by the bake-off in docs/model_research.md:
- `pi3x` (default): Pi3X, cameras ~5x more accurate and walls closer on dataset C.
  Weights are CC BY-NC 4.0 (non-commercial).
- `mapanything`: MapAnything, Apache 2.0 weights; the commercial-safe fallback.

Optional dependency: `uv sync --extra video` (torch, MapAnything, Pi3; ~4-5 GB of weights per
model fetched from Hugging Face on first use).
"""

import os
import time
import warnings
from dataclasses import dataclass
from functools import cache

import numpy as np
from PIL import Image

MODELS = {
    "pi3x": "yyfz233/Pi3X",  # CC BY-NC 4.0
    "mapanything": "facebook/map-anything-apache",  # Apache 2.0
}
DEFAULT_MODEL = "pi3x"
CONF_PERCENTILE = 10  # drop the least confident 10% of pixels (same as the bake-off)


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

    def forward_head(hidden, *args, **kwargs):
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
    start = time.perf_counter()
    with torch.no_grad(), torch.autocast(device, dtype=torch.bfloat16):
        res = net(imgs=imgs)
    seconds = time.perf_counter() - start

    xyz = res["points"][0].float().cpu().numpy()
    conf = res["conf"][0, ..., 0].float().cpu().numpy()
    keep = np.isfinite(xyz).all(axis=-1)
    keep &= conf >= np.percentile(conf[keep], CONF_PERCENTILE)
    poses = res["camera_poses"][0].float().cpu().numpy()
    return Reconstruction(xyz, keep, poses, seconds, "pi3x")
