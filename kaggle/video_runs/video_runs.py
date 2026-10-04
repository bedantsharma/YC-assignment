"""Video tier on Kaggle: our own pipeline (`floorplan run --tier video`) on a T4.

No model runs on the laptop (user, Oct 4). This kernel runs the unchanged pipeline from a
copy of src/floorplan shipped in the private dataset bedantsharma/floorplan-video-c2 (with
home C's Camera-app videos), and keeps every model output in FLOORPLAN_RECON_CACHE so the
laptop replays the geometry without the model (`FLOORPLAN_RECON_CACHE_ONLY=1`).

Output: plans/<tag>/<video>_video/plan.json + plan.png, recon_cache/*.npz, log.txt.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PI3 = "git+https://github.com/yyfz/Pi3@9fa3ddb3f8d53041f8b2738df404f62223bbaa7b"
MAPANYTHING_REV = "3d10cf7a3016fc0f9bb13a071ee66c47b10be0d9"
RUNS = [  # (video stem, frames); 30 = one model pass, more = chained windows of 30
    ("c_damage_v1", 30),
    ("c_damage_v2", 30),
    ("c_home_v1", 90),
    ("c_damage_v1", 60),
    ("c_damage_v2", 60),
    ("c_home_v1", 150),
]
OUT = Path("/kaggle/working")
LOG = OUT / "log.txt"


def log(msg: str) -> None:
    print(msg, flush=True)
    with LOG.open("a") as f:
        f.write(msg + "\n")


def sh(cmd, **kw) -> int:
    return subprocess.run(cmd, shell=isinstance(cmd, str), **kw).returncode


def main() -> None:
    sh("nvidia-smi -L || echo NO nvidia-smi")
    gpu = subprocess.run(
        [sys.executable, "-c", "import torch; print(torch.cuda.is_available())"],
        capture_output=True, text=True,
    ).stdout.strip()  # fmt: skip
    if gpu != "True":
        log("NO GPU in this session (CPU image); nothing to run")
        sys.exit(1)
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

    src = Path("/kaggle/tmp/src")  # folders may arrive as zips (kaggle --dir-mode zip)
    for z in Path("/kaggle/input").rglob("*.zip"):
        shutil.unpack_archive(z, src / z.stem)
    roots = (Path("/kaggle/input"), src)
    data = next(p for d in roots for p in d.rglob("floorplan/pipeline.py")).parent.parent
    videos = {p.stem: p for d in roots for p in d.rglob("*.mp4")}
    log(f"code from {data}; videos {sorted(videos)}")
    env = {
        **os.environ,
        # installed in this process: the run subprocesses see them on a fresh start
        "PYTHONPATH": f"{data}:{repo}",
        "FLOORPLAN_RECON_CACHE": str(OUT / "recon_cache"),
    }
    rows = []
    for stem, n in RUNS:
        tag = f"f{n}"
        start = time.perf_counter()
        res = subprocess.run(
            [sys.executable, "-m", "floorplan.cli", "run", str(videos[stem]), "--tier", "video",
             "--frames", str(n), "--out", str(OUT / "plans" / tag)],
            env=env, capture_output=True, text=True,
        )  # fmt: skip
        secs = round(time.perf_counter() - start, 1)
        log(f"== {stem} {tag} exit {res.returncode} {secs}s\n{res.stdout}{res.stderr[-4000:]}")
        rows.append({"video": stem, "frames": n, "exit": res.returncode, "seconds": secs})
    (OUT / "summary.json").write_text(json.dumps(rows, indent=2))
    log("done")


main()
