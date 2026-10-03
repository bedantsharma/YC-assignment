"""Multi-view reconstruction from RGB frames with MapAnything (metric scale, no poses needed).

Optional dependency: `uv sync --extra video` (torch + MapAnything, ~5 GB of weights fetched
from Hugging Face on first use). Chosen by the spike in docs/model_spike.md.
"""

import os
import time
import warnings
from dataclasses import dataclass

import numpy as np
from PIL import Image

MODEL_ID = "facebook/map-anything-apache"  # Apache 2.0 weights


@dataclass
class Reconstruction:
    points: np.ndarray  # (N, 3) metres, first camera's frame (OpenCV axes)
    cam_poses: np.ndarray  # (V, 4, 4) camera-to-world, OpenCV convention
    intrinsics: np.ndarray  # (V, 3, 3) at the model's input resolution
    seconds: float  # inference only, model load excluded


def reconstruct(frames: list[Image.Image]) -> Reconstruction:
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    try:
        import torch
        from mapanything.models import MapAnything
        from mapanything.utils.image import preprocess_inputs
    except ImportError as err:
        raise RuntimeError(
            "the video and photo tiers need the model: run `uv sync --extra video`"
        ) from err

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    if torch.cuda.is_available():
        device = "cuda"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = MapAnything.from_pretrained(MODEL_ID).to(device)
        views = preprocess_inputs([{"img": torch.from_numpy(np.asarray(f))} for f in frames])
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
        seconds = time.perf_counter() - start

    pts = []
    for p in preds:
        xyz = p["pts3d"][0].float().cpu().numpy().reshape(-1, 3)
        mask = p["mask"][0].cpu().numpy().reshape(-1).astype(bool)
        pts.append(xyz[mask])
    poses = np.stack([p["camera_poses"][0].float().cpu().numpy() for p in preds])
    intr = np.stack([p["intrinsics"][0].float().cpu().numpy() for p in preds])
    return Reconstruction(np.concatenate(pts), poses, intr, seconds)
