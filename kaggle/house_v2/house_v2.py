"""Video tier on the friend's second whole-house clip (c_home_v2), on both Kaggle T4s.

The first house clip (c_home_v1, 295 s, ceiling sweeps) folded rooms onto each other
(docs/home_c_new_captures.md). c_home_v2 is a new 260 s eye-level walk, transcoded on the
laptop to upright 540x960 (the pipeline's own frame size), so the laptop replays the same
pixels. No model runs on the laptop (user, Oct 4).

Kaggle's T4 option gives two GPUs and one pipeline run uses one. So the runs go in two
queues, one process per GPU (CUDA_VISIBLE_DEVICES), each a fresh `floorplan run` with the
unchanged pipeline from the copy of src/floorplan in bedantsharma/floorplan-house-v2.
More frames = denser sampling = fewer seconds of walking per 30-frame window.

Output: plans/f<n>/..., recon_cache/*.npz (replay), gpu_mem.csv, summary.json, log.txt.
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

PI3 = "git+https://github.com/yyfz/Pi3@9fa3ddb3f8d53041f8b2738df404f62223bbaa7b"
MAPANYTHING_REV = "3d10cf7a3016fc0f9bb13a071ee66c47b10be0d9"
VIDEO = "c_home_v2"
QUEUES = {0: [300, 90], 1: [240, 150]}  # GPU -> frame counts, longest first
OUT = Path("/kaggle/working")
LOG = OUT / "log.txt"
_lock = threading.Lock()


def log(msg: str) -> None:
    with _lock:
        print(msg, flush=True)
        with LOG.open("a") as f:
            f.write(msg + "\n")


def sh(cmd, **kw) -> int:
    return subprocess.run(cmd, shell=isinstance(cmd, str), **kw).returncode


def watch_gpus(stop: threading.Event) -> None:
    """Memory used per GPU every 10 s: evidence both T4s were busy, and the peak."""
    with (OUT / "gpu_mem.csv").open("w") as f:
        f.write("t_s,gpu,mem_mib,util_pct\n")
        t0 = time.perf_counter()
        while not stop.wait(10):
            q = subprocess.run(
                ["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True,
            ).stdout  # fmt: skip
            for line in q.strip().splitlines():
                f.write(f"{time.perf_counter() - t0:.0f},{line.replace(' ', '')}\n")
            f.flush()


def worker(gpu: int, counts: list[int], video: Path, env: dict, rows: list) -> None:
    for n in counts:
        start = time.perf_counter()
        try:
            res = subprocess.run(
                [sys.executable, "-m", "floorplan.cli", "run", str(video), "--tier", "video",
                 "--frames", str(n), "--up", "top", "--out", str(OUT / "plans" / f"f{n}")],
                env={**env, "CUDA_VISIBLE_DEVICES": str(gpu)}, capture_output=True, text=True,
            )  # fmt: skip
            code, out = res.returncode, res.stdout + res.stderr[-4000:]
        except Exception as e:  # one failure must not hide the others
            code, out = -1, repr(e)
        secs = round(time.perf_counter() - start, 1)
        log(f"== GPU {gpu} {VIDEO} f{n} exit {code} {secs}s\n{out}")
        with _lock:
            rows.append({"video": VIDEO, "frames": n, "gpu": gpu, "exit": code, "seconds": secs})


def main() -> None:
    sh("nvidia-smi -L || echo NO nvidia-smi")
    probe = subprocess.run(
        [sys.executable, "-c", "import torch; print(torch.cuda.device_count())"],
        capture_output=True, text=True,
    ).stdout.strip()  # fmt: skip
    n_gpu = int(probe) if probe.isdigit() else 0
    log(f"GPUs visible to torch: {n_gpu}")
    if n_gpu == 0:
        log("NO GPU in this session (CPU image); nothing to run")
        sys.exit(1)
    queues = QUEUES if n_gpu >= 2 else {0: sorted(sum(QUEUES.values(), []))}
    if not shutil.which("ffmpeg"):
        sh("apt-get -qq update && apt-get -qq install -y ffmpeg")
    log(f"ffmpeg: {shutil.which('ffmpeg')}")

    pip = [sys.executable, "-m", "pip", "install", "-q"]
    # MapAnything (its image preprocessing) from a clone: it reads configs/ from the repo
    repo = Path("/kaggle/tmp/map-anything")
    sh(["git", "clone", "-q", "https://github.com/facebookresearch/map-anything", str(repo)])
    sh(["git", "-C", str(repo), "checkout", "-q", MAPANYTHING_REV])
    for spec in (["-e", str(repo)], [PI3], ["scikit-image", "pillow-heif"]):
        if sh([*pip, *spec]) != 0:
            log(f"FAILED pip install {spec}")
            sys.exit(1)
    # fetch the weights once, before two processes race for the same HF cache
    fetch = "from huggingface_hub import snapshot_download; snapshot_download('yyfz233/Pi3X')"
    if sh([sys.executable, "-c", fetch]):
        log("FAILED to download Pi3X weights")
        sys.exit(1)

    src = Path("/kaggle/tmp/src")  # folders may arrive as zips (kaggle --dir-mode zip)
    for z in Path("/kaggle/input").rglob("*.zip"):
        shutil.unpack_archive(z, src / z.stem)
    roots = (Path("/kaggle/input"), src)
    data = next(p for d in roots for p in d.rglob("floorplan/pipeline.py")).parent.parent
    video = next(p for d in roots for p in d.rglob(f"{VIDEO}.mp4"))
    log(f"code from {data}; video {video}; queues {queues}")
    env = {
        **os.environ,
        # installed in this process: the run subprocesses see them on a fresh start
        "PYTHONPATH": f"{data}:{repo}",
        "FLOORPLAN_RECON_CACHE": str(OUT / "recon_cache"),
    }
    # hash of the decoded frames: the laptop's replay needs the same pixels (cache key);
    # compare with the same line run locally before trusting a replay
    frames_sha = (
        "import hashlib, sys, numpy as np; from floorplan.video import sample_frames; "
        "h = hashlib.sha1(); [h.update(np.asarray(f).tobytes()) for f in "
        "sample_frames(__import__('pathlib').Path(sys.argv[1]), 90, 'top')]; print(h.hexdigest())"
    )
    sha = subprocess.run(
        [sys.executable, "-c", frames_sha, str(video)], env=env, capture_output=True, text=True
    )
    log(f"frames sha1 (90 frames): {sha.stdout.strip()} {sha.stderr[-500:]}")
    stop, rows = threading.Event(), []
    mon = threading.Thread(target=watch_gpus, args=(stop,), daemon=True)
    mon.start()
    threads = [
        threading.Thread(target=worker, args=(g, counts, video, env, rows))
        for g, counts in queues.items()
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stop.set()
    mon.join()
    (OUT / "summary.json").write_text(json.dumps(sorted(rows, key=lambda r: r["frames"]), indent=2))
    log("done")


main()
