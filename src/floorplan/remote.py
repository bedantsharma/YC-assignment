"""Run the reconstruction model on Kaggle's free GPUs (the default; mvs.py falls back to
this machine when anything here fails).

One job per run, however many frame sets it needs (a long video's windows, every photo
folder): the sets are written as JPEGs into a **private** Kaggle dataset
(`<user>/floorplan-recon-input`, a new version per run, together with a copy of
src/floorplan), the GPU job `<user>/floorplan-recon` (kaggle_kernel.py) reconstructs each
with the pipeline's own model code, and its outputs are downloaded into the reconstruction
cache under the names the laptop computed from the original pixels.

Images are shrunk to UPLOAD_LONG_SIDE and saved as quality-95 JPEG before upload (the model
works at ~518 px anyway): 35 photos as PNG took 5 min to upload, as JPEG about 1 min.

Needs: Kaggle credentials (~/.kaggle/kaggle.json, or KAGGLE_USERNAME / KAGGLE_KEY), the
`kaggle` command or `uvx`, and network. Typical wall clock: 1-2 min upload, 3-5 min setup
on Kaggle, 1-3 min of GPU work, 1 min download. FLOORPLAN_KAGGLE_TIMEOUT_MIN caps the wait.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from PIL import Image

DATASET, KERNEL = "floorplan-recon-input", "floorplan-recon"
UPLOAD_LONG_SIDE = 1536
UPLOAD_QUALITY = 95  # JPEG: ~5x smaller than PNG; the model works at ~518 px
TIMEOUT_ENV = "FLOORPLAN_KAGGLE_TIMEOUT_MIN"
TIMEOUT_MIN = 40
POLL_S = 20
STALE_RETRIES = 2


class Unavailable(RuntimeError):
    pass


def run(jobs: list[tuple[Path, list[Image.Image]]], model: str) -> float:
    """Reconstruct every (cache path, frames) on Kaggle; returns wall-clock seconds.
    Raises if Kaggle is unusable or the job fails; sets it did not finish stay missing."""
    start = time.perf_counter()
    user = username()
    cli = command()
    _online()
    deadline = start + 60 * float(os.environ.get(TIMEOUT_ENV, TIMEOUT_MIN))
    token = uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix="floorplan_kaggle_") as tmp:
        tmp = Path(tmp)
        data, kernel, out = tmp / "data", tmp / "kernel", tmp / "out"
        _say(f"Kaggle: uploading {sum(len(f) for _, f in jobs)} images in {len(jobs)} sets")
        _write_dataset(data, jobs, model, token, f"{user}/{DATASET}")
        exists = _cli(cli, "datasets", "status", f"{user}/{DATASET}", check=False)[0] == 0
        if exists:
            _cli(cli, "datasets", "version", "-p", str(data), "-m", f"run {token}",
                 "--dir-mode", "zip")  # fmt: skip
        else:
            _cli(cli, "datasets", "create", "-p", str(data), "--dir-mode", "zip")
        _wait(lambda: _cli(cli, "datasets", "status", f"{user}/{DATASET}")[1].strip()
              .endswith("ready"), deadline, "dataset processing")  # fmt: skip

        _write_kernel(kernel, user, token)
        status = {"s": ""}

        def finished() -> bool:
            text = _cli(cli, "kernels", "status", f"{user}/{KERNEL}")[1].lower()
            status["s"] = text
            return any(w in text for w in ("complete", "error", "cancel"))

        for attempt in range(STALE_RETRIES + 1):
            # "ready" can still describe the previous version for a moment: the job checks
            # the run token and stops on a stale dataset, then we push again
            time.sleep(POLL_S)
            _cli(cli, "kernels", "push", "-p", str(kernel), "--accelerator", "NvidiaTeslaT4")
            _say("Kaggle: GPU job started (setup takes a few minutes)")
            _wait(finished, deadline, "GPU job")
            shutil.rmtree(out, ignore_errors=True)
            out.mkdir()
            _cli(cli, "kernels", "output", f"{user}/{KERNEL}", "-p", str(out), check=False)
            log = out / "log.txt"
            if not (log.exists() and "stale dataset" in log.read_text()):
                break
            _say(f"Kaggle: job saw the previous upload; retrying ({attempt + 1})")
        got = {p.name: p for p in out.rglob("*.npz")}
        for path, _ in jobs:
            if path.name in got:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(got[path.name], path)
        missing = [p.name for p, _ in jobs if not p.exists()]
        if missing:
            tail = ""
            if (out / "log.txt").exists():
                tail = (out / "log.txt").read_text().strip().splitlines()[-1][:200]
            raise RuntimeError(
                f"Kaggle job ended ({status['s'].strip()[-40:]}) without {len(missing)} of "
                f"{len(jobs)} sets; last log line: {tail}"
            )
    secs = time.perf_counter() - start
    _say(f"Kaggle: done in {secs / 60:.1f} min")
    return secs


def username() -> str:
    if os.environ.get("KAGGLE_USERNAME"):
        return os.environ["KAGGLE_USERNAME"]
    cred = Path(os.environ.get("KAGGLE_CONFIG_DIR", Path.home() / ".kaggle")) / "kaggle.json"
    if not cred.exists():
        raise Unavailable("no Kaggle credentials (~/.kaggle/kaggle.json)")
    return json.loads(cred.read_text())["username"]


def command() -> list[str]:
    if shutil.which("kaggle"):
        return ["kaggle"]
    if shutil.which("uvx"):
        return ["uvx", "kaggle"]
    raise Unavailable("no kaggle command (install uv, or `pip install kaggle`)")


def _online() -> None:
    try:
        socket.create_connection(("www.kaggle.com", 443), timeout=5).close()
    except OSError as err:
        raise Unavailable("no network to kaggle.com") from err


def _write_dataset(data: Path, jobs, model: str, token: str, slug: str) -> None:
    data.mkdir(parents=True)
    for path, frames in jobs:
        d = data / path.stem
        d.mkdir()
        for i, f in enumerate(frames):
            im = f.convert("RGB")
            if max(im.size) > UPLOAD_LONG_SIDE:
                im = im.copy()
                im.thumbnail((UPLOAD_LONG_SIDE, UPLOAD_LONG_SIDE), Image.LANCZOS)
            if UPLOAD_QUALITY:
                im.save(d / f"{i:04d}.jpg", quality=UPLOAD_QUALITY)
            else:  # lossless
                im.save(d / f"{i:04d}.png", compress_level=1)
    code = Path(__file__).resolve().parent
    shutil.copytree(code, data / "floorplan", ignore=shutil.ignore_patterns("__pycache__"))
    jobs_json = {"token": token, "model": model, "sets": [p.stem for p, _ in jobs]}
    (data / "jobs.json").write_text(json.dumps(jobs_json))
    meta = {"title": "floorplan recon input", "id": slug, "licenses": [{"name": "other"}]}
    (data / "dataset-metadata.json").write_text(json.dumps(meta))


def _write_kernel(kernel: Path, user: str, token: str) -> None:
    kernel.mkdir(parents=True)
    script = (Path(__file__).parent / "kaggle_kernel.py").read_text()
    (kernel / "recon.py").write_text(script.replace("__TOKEN__", token))
    meta = {
        "id": f"{user}/{KERNEL}",
        "title": KERNEL,
        "code_file": "recon.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": "true",
        "enable_gpu": "true",
        "enable_internet": "true",
        "machine_shape": "NvidiaTeslaT4",
        "dataset_sources": [f"{user}/{DATASET}"],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    (kernel / "kernel-metadata.json").write_text(json.dumps(meta, indent=2))


def _cli(cli: list[str], *args: str, check: bool = True) -> tuple[int, str]:
    res = subprocess.run([*cli, *args], capture_output=True, text=True, timeout=900)
    text = res.stdout + res.stderr
    if check and res.returncode != 0:
        raise RuntimeError(f"kaggle {args[0]} {args[1]} failed: {text.strip()[-200:]}")
    return res.returncode, text


def _wait(done, deadline: float, what: str) -> None:
    while not done():
        if time.perf_counter() > deadline:
            raise TimeoutError(f"Kaggle {what} not finished within {TIMEOUT_ENV} minutes")
        time.sleep(POLL_S)


def _say(msg: str) -> None:
    print(f"floorplan: {msg}", file=sys.stderr, flush=True)
