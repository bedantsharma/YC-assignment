"""Photo tier on the friend's hall photos (home C), on both Kaggle T4s; same job as kaggle/photos_c.

Sets from scripts/make_photo_subsets.py (data/home_c/photo_sets/<set>/<room>/*.jpg):
`all` (26-33 per room), `k8` and `k5` (the brief's 2-8 per room, evenly spaced in shooting
order). Rooms: hall only (24 photos, Oct 4); the other rooms are cached from kaggle/photos_c.
No model runs on the laptop (user, Oct 4): every model output is kept in
FLOORPLAN_RECON_CACHE for the laptop to replay (`FLOORPLAN_RECON_CACHE_ONLY=1`).

Two queues, one process per GPU (CUDA_VISIBLE_DEVICES), each a fresh `floorplan run` with
the unchanged pipeline from the copy of src/floorplan in bedantsharma/floorplan-photos-hall.

Output: photo_runs/<set>/..., recon_cache/*.npz, gpu_mem.csv, summary.json, log.txt.
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
QUEUES = {0: ["all"], 1: ["k8", "k5"]}  # GPU -> photo sets
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


def worker(gpu: int, names: list[str], sets: dict, env: dict, rows: list) -> None:
    for name in names:
        start = time.perf_counter()
        try:
            res = subprocess.run(
                [sys.executable, "-m", "floorplan.cli", "run", str(sets[name]), "--tier",
                 "photo", "--out", str(OUT / "photo_runs" / name)],
                env={**env, "CUDA_VISIBLE_DEVICES": str(gpu)}, capture_output=True, text=True,
            )  # fmt: skip
            code, out = res.returncode, res.stdout + res.stderr[-4000:]
        except Exception as e:  # one failure must not hide the others
            code, out = -1, repr(e)
        secs = round(time.perf_counter() - start, 1)
        log(f"== GPU {gpu} {name} exit {code} {secs}s\n{out}")
        with _lock:
            rows.append({"set": name, "gpu": gpu, "exit": code, "seconds": secs})


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
    sets = {p.parent.name: p.parent for d in roots for p in d.rglob("manifest.json")}
    log(f"code from {data}; photo sets {sorted(sets)}; queues {queues}")
    env = {
        **os.environ,
        # installed in this process: the run subprocesses see them on a fresh start
        "PYTHONPATH": f"{data}:{repo}",
        "FLOORPLAN_RECON_CACHE": str(OUT / "recon_cache"),
    }
    stop, rows = threading.Event(), []
    mon = threading.Thread(target=watch_gpus, args=(stop,), daemon=True)
    mon.start()
    threads = [
        threading.Thread(target=worker, args=(g, names, sets, env, rows))
        for g, names in queues.items()
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stop.set()
    mon.join()
    (OUT / "summary.json").write_text(json.dumps(sorted(rows, key=lambda r: r["set"]), indent=2))
    log("done")


main()
