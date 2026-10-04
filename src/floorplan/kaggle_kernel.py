"""Kaggle GPU job for `remote.py` (never imported by the pipeline; uploaded as the kernel).

Reads the private dataset remote.py just uploaded: `jobs.json` (run token, model, the
frame sets by cache name), one folder of lossless PNG frames per set, and a copy of
src/floorplan. Reconstructs each set with the pipeline's own model code (mvs._infer) and
writes recon_cache/<cache name>.npz for the laptop to download. Sets are split over the
GPUs, one process per GPU. Installs follow kaggle/photos_hall (CLAUDE.md, Remote GPU runs).
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TOKEN = "__TOKEN__"  # replaced by remote.py: refuses a stale dataset version
PI3 = "git+https://github.com/yyfz/Pi3@9fa3ddb3f8d53041f8b2738df404f62223bbaa7b"
MAPANYTHING_REV = "3d10cf7a3016fc0f9bb13a071ee66c47b10be0d9"
OUT = Path("/kaggle/working")
WORKER = """
import sys, time
from pathlib import Path
from PIL import Image
from floorplan.mvs import _infer, save
out, model = Path(sys.argv[1]), sys.argv[2]
for d in sys.argv[3:]:
    d = Path(d)
    t = time.perf_counter()
    try:
        frames = [Image.open(p).convert("RGB") for p in sorted(d.glob("*.png"))]
        save(out / f"{d.name}.npz", _infer(frames, model))
        print(f"ok {d.name} {len(frames)} frames {time.perf_counter() - t:.0f}s", flush=True)
    except Exception as e:
        print(f"FAILED {d.name}: {e!r}", flush=True)
"""


def log(msg: str) -> None:
    print(msg, flush=True)
    with (OUT / "log.txt").open("a") as f:
        f.write(msg + "\n")


def sh(cmd) -> int:
    return subprocess.run(cmd).returncode


def main() -> None:
    probe = subprocess.run(
        [sys.executable, "-c", "import torch; print(torch.cuda.device_count())"],
        capture_output=True, text=True,
    ).stdout.strip()  # fmt: skip
    n_gpu = int(probe) if probe.isdigit() else 0
    log(f"GPUs: {n_gpu}")
    if n_gpu == 0:
        log("NO GPU in this session")
        sys.exit(1)

    src = Path("/kaggle/tmp/src")  # folders arrive as zips (kaggle --dir-mode zip)
    for z in Path("/kaggle/input").rglob("*.zip"):
        shutil.unpack_archive(z, src / z.stem)
    roots = (Path("/kaggle/input"), src)
    jobs_file = next(p for d in roots for p in d.rglob("jobs.json"))
    jobs = json.loads(jobs_file.read_text())
    if jobs["token"] != TOKEN:
        log(f"stale dataset: token {jobs['token']} != {TOKEN}")
        sys.exit(1)
    code = next(p for d in roots for p in d.rglob("floorplan/mvs.py")).parent.parent
    sets = []
    for name in jobs["sets"]:
        found = [p for d in roots for p in d.rglob(name) if p.is_dir() and any(p.glob("*.png"))]
        if not found:
            log(f"missing frames for {name}")
            continue
        sets.append(found[0])
    log(f"{len(sets)} sets, model {jobs['model']}, code from {code}")

    pip = [sys.executable, "-m", "pip", "install", "-q"]
    repo = Path("/kaggle/tmp/map-anything")
    sh(["git", "clone", "-q", "https://github.com/facebookresearch/map-anything", str(repo)])
    sh(["git", "-C", str(repo), "checkout", "-q", MAPANYTHING_REV])
    for spec in (["-e", str(repo)], [PI3], ["scikit-image", "pillow-heif"]):
        if sh([*pip, *spec]) != 0:
            log(f"FAILED pip install {spec}")
            sys.exit(1)
    fetch = "from huggingface_hub import snapshot_download; snapshot_download('yyfz233/Pi3X')"
    if sh([sys.executable, "-c", fetch]):
        log("FAILED to download Pi3X weights")
        sys.exit(1)

    cache = OUT / "recon_cache"
    cache.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": f"{code}:{repo}", "FLOORPLAN_RECON_BACKEND": "here"}
    procs = []
    for g in range(min(n_gpu, len(sets))):
        mine = [str(s) for s in sets[g::n_gpu]]
        cmd = [sys.executable, "-c", WORKER, str(cache), jobs["model"], *mine]
        procs.append(subprocess.Popen(
            cmd, env={**env, "CUDA_VISIBLE_DEVICES": str(g)},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        ))  # fmt: skip
    for p in procs:
        out, _ = p.communicate()
        log(out[-6000:])
    done = sorted(p.stem for p in cache.glob("*.npz"))
    (OUT / "summary.json").write_text(json.dumps({"done": done, "asked": jobs["sets"]}))
    log(f"done {len(done)} of {len(jobs['sets'])}")
    if not done:
        sys.exit(1)


if __name__ == "__main__":
    main()
