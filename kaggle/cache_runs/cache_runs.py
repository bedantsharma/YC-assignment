"""Replay caches for the plans that had none (fix declaration, docs/fix_declaration.md):
the c_home_01 LiDAR recording's own video (video tier, 90 frames, RGB only) and the photo
tier on stills taken from home C's videos (data/home_c/photos_sim/<capture>/<k8|k8p>).

No model runs on the laptop (user, Oct 4). Same setup as kaggle/video_runs: the unchanged
pipeline from the copy of src/floorplan in bedantsharma/floorplan-video-c2 (now also with
the stills), c_home_01.mp4 from bedantsharma/floorplan-home-c; every model output is kept
in FLOORPLAN_RECON_CACHE for the laptop to replay (`FLOORPLAN_RECON_CACHE_ONLY=1`).

Output: plans/..., recon_cache/*.npz, summary.json, log.txt.
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
CAPTURES = ("c_home_01", "c_damage_01", "c_damage_02")
PHOTO_SETS = ("k8", "k8p")
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
    photos = {
        (p.parent.parent.name, p.parent.name): p.parent
        for d in roots
        for p in d.rglob("manifest.json")
        if p.parent.name in PHOTO_SETS and p.parent.parent.name in CAPTURES
    }
    log(f"code from {data}; videos {sorted(videos)}; photo sets {sorted(photos)}")
    runs = [
        (
            "c_home_01_video_f90",
            [
                str(videos["c_home_01"]),
                "--tier",
                "video",
                "--frames",
                "90",
                "--out",
                str(OUT / "plans"),
            ],
        )
    ]
    for (cap, k), folder in sorted(photos.items()):
        runs.append((f"{cap}_{k}", [str(folder), "--out", str(OUT / "photo_runs" / f"{cap}_{k}")]))
    env = {
        **os.environ,
        # installed in this process: the run subprocesses see them on a fresh start
        "PYTHONPATH": f"{data}:{repo}",
        "FLOORPLAN_RECON_CACHE": str(OUT / "recon_cache"),
    }
    rows = []
    for tag, args in runs:
        start = time.perf_counter()
        try:
            res = subprocess.run(
                [sys.executable, "-m", "floorplan.cli", "run", *args],
                env=env, capture_output=True, text=True,
            )  # fmt: skip
            code, out = res.returncode, res.stdout + res.stderr[-4000:]
        except Exception as e:  # one failure must not hide the others
            code, out = -1, repr(e)
        secs = round(time.perf_counter() - start, 1)
        log(f"== {tag} exit {code} {secs}s\n{out}")
        rows.append({"run": tag, "exit": code, "seconds": secs})
    (OUT / "summary.json").write_text(json.dumps(rows, indent=2))
    log("done")


main()
