"""Reconstruction on this machine without running it out of memory (Kaggle fallback).

One Pi3X pass over 30 frames peaks at ~12.8 GB (docs/model_spike.md), which pushed the
16 GB M4 into red memory pressure. Here a frame set is reconstructed in small windows,
each in its own child process, then chained exactly as long videos are (`chunks.chain`:
overlapping windows joined by similarity fits on the shared frames' point maps):

- window size from this machine's RAM (BUDGET of it for the model; MODEL_GB for weights and
  activations of the backbone, PER_VIEW_GB per frame, both from the 30-frame peak),
  or FLOORPLAN_LOCAL_WINDOW;
- a child process per window, so all of its memory goes back to the system when it ends;
  run at low priority (nice) so the laptop stays usable;
- on Apple GPUs the child gets a hard memory cap (PYTORCH_MPS_HIGH_WATERMARK_RATIO), so a
  window that does not fit fails with an error instead of swapping the machine to death;
- a failed window (out of memory, or killed) retries the whole set with half the window,
  down to MIN_WINDOW.

Slower than one pass (the weights load once per window, ~10-20 s) and slightly less
accurate (fewer views per pass), so the plan says when it ran this way.

Weights: fetched from Hugging Face on first use, or ahead of time with
`uv run python -m floorplan.mvs_local --fetch` (needs `uv sync --extra video`).
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

from floorplan.mvs import MODELS, Reconstruction

WINDOW_ENV = "FLOORPLAN_LOCAL_WINDOW"
BUDGET = 0.5  # share of RAM the model may use; the rest stays with the system
MODEL_GB = 5.5  # Pi3X weights (5.4 GB, float32) + fixed activations
PER_VIEW_GB = 0.25  # (12.8 GB - MODEL_GB) / 30 frames
MIN_WINDOW, MAX_WINDOW = 4, 30
MPS_HIGH, MPS_LOW = "0.8", "0.6"  # shares of the GPU's recommended working set
NICE = 10
WORKER_MODULE = "floorplan.mvs_local"  # the child's entry point (tests swap in a fake model)


class WorkerFailed(RuntimeError):
    pass


def ram_gb() -> float:
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30


def window_for(gb: float) -> int:
    n = int((gb * BUDGET - MODEL_GB) / PER_VIEW_GB)
    return max(MIN_WINDOW, min(MAX_WINDOW, n))


def overlap_for(window: int) -> int:
    return max(2, window // 3)


def reconstruct_safe(frames: list[Image.Image], model: str, worker=None) -> Reconstruction:
    """frames -> Reconstruction, window by window in child processes, smaller on failure."""
    from floorplan.chunks import chain, windows

    run_one = worker or _worker
    # never below MIN_WINDOW: a window of 2 or less cannot overlap the next one (chunks)
    window = max(MIN_WINDOW, int(os.environ.get(WINDOW_ENV) or window_for(ram_gb())))
    while True:
        try:
            start = time.perf_counter()
            if len(frames) <= window:
                _say(f"reconstructing {len(frames)} frames in one pass on this machine")
                rec = run_one(frames, model)
            else:
                n_win = len(windows(len(frames), window, overlap_for(window)))
                _say(f"reconstructing {len(frames)} frames on this machine in {n_win} windows "
                     f"of {window} (low-memory mode, slow)")  # fmt: skip
                count = iter(range(1, n_win + 1))

                def one(idx: list[int], count=count, n_win=n_win) -> Reconstruction:
                    _say(f"  window {next(count)} of {n_win}")
                    return run_one([frames[i] for i in idx], model)

                rec, _ = chain(len(frames), one, window, overlap_for(window))
            _say(f"done in {time.perf_counter() - start:.0f} s")
            return rec
        except WorkerFailed as err:
            if window <= MIN_WINDOW:
                raise RuntimeError(f"local reconstruction failed even at {window} frames: "
                                   f"{err}") from err  # fmt: skip
            window = max(MIN_WINDOW, window // 2)
            _say(f"window failed ({err}); retrying with {window} frames per window")


def _say(msg: str) -> None:
    print(f"floorplan: {msg}", file=sys.stderr, flush=True)


def _worker(frames: list[Image.Image], model: str) -> Reconstruction:
    """One window in a fresh child process (all its memory is returned when it exits)."""
    with tempfile.TemporaryDirectory(prefix="floorplan_mvs_") as tmp:
        src, dst = Path(tmp) / "frames.npz", Path(tmp) / "rec.npz"
        np.savez(src, *[np.asarray(f.convert("RGB")) for f in frames])
        env = {
            **os.environ,
            "PYTORCH_ENABLE_MPS_FALLBACK": "1",
            "PYTORCH_MPS_HIGH_WATERMARK_RATIO": os.environ.get(
                "PYTORCH_MPS_HIGH_WATERMARK_RATIO", MPS_HIGH
            ),
            "PYTORCH_MPS_LOW_WATERMARK_RATIO": os.environ.get(
                "PYTORCH_MPS_LOW_WATERMARK_RATIO", MPS_LOW
            ),
        }
        res = subprocess.run(
            [sys.executable, "-m", WORKER_MODULE, "--worker", str(src), str(dst), model],
            env=env, capture_output=True, text=True, preexec_fn=lambda: os.nice(NICE),
        )  # fmt: skip
        if res.returncode != 0 or not dst.exists():
            why = f"killed by signal {-res.returncode}" if res.returncode < 0 else (
                res.stderr.strip().splitlines() or ["no output"])[-1]  # fmt: skip
            raise WorkerFailed(why[:300])
        with np.load(dst) as z:
            return Reconstruction(z["view_points"], z["view_keep"], z["cam_poses"],
                                  float(z["seconds"]), model)  # fmt: skip


def _child(src: Path, dst: Path, model: str) -> None:
    from floorplan.mvs import _infer

    z = np.load(src)
    frames = [Image.fromarray(z[k]) for k in sorted(z.files, key=lambda k: int(k[4:]))]
    rec = _infer(frames, model)
    np.savez(dst, view_points=rec.view_points, view_keep=rec.view_keep,
             cam_poses=rec.cam_poses, seconds=rec.seconds)  # fmt: skip


def fetch(model: str = "pi3x") -> None:
    from huggingface_hub import snapshot_download

    snapshot_download(MODELS[model])
    print(f"{MODELS[model]} cached")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--worker"]:
        _child(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
    elif sys.argv[1:2] == ["--fetch"]:
        fetch(sys.argv[2] if len(sys.argv) > 2 else "pi3x")
    else:
        print(__doc__)
