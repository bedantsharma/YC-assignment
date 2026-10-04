"""LiDAR bake-off on Kaggle: pretrained point-cloud layout models on home C's fused LiDAR.

No model runs on the laptop (user, Oct 4). Input: private dataset bedantsharma/floorplan-
lidar-c: coloured fused clouds (scripts/export_clouds.py; metres, z up, 2 cm voxels).
Models (docs/lidar_model_research.md): SpatialLM 1.1 (Qwen-0.5B and Llama-1B; Sonata
point encoder) in "arch" mode: walls, doors, windows. Generation samples (temperature
0.6), so each cloud runs with 3 seeds to show the spread.

SpatialLM pins Python <= 3.12 and torch 2.4; Kaggle runs 3.13, so it gets its own uv venv
(Python 3.11). Flash attention needs Ampere; the T4 is Turing, so Sonata runs with
enable_flash=False (plain attention, same weights).
Two GPUs (Kaggle "T4 x2"): the language model stays on cuda:0 and the Sonata point
encoder (what ran out of memory in run 1) moves to cuda:1, so each gets a full 15 GB.
Runs 2-3 repeat only what failed in run 1 (whole home, and every Llama-1B run).
Output: <cloud>__<model>__s<seed>.txt (SpatialLM layout language), log.txt, summary.json.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

SPATIALLM_REV = "8913c44d84a450c53e9340b13317f8cf7144a738"
MODELS = ["manycore-research/SpatialLM1.1-Qwen-0.5B", "manycore-research/SpatialLM1.1-Llama-1B"]
SEEDS = [0, 1, 2]
REQS = [
    "torch==2.4.1", "torchvision==0.19.1", "transformers==4.46.1", "tokenizers>=0.19.0,<0.20.4",
    "safetensors>=0.4.5", "einops", "numpy<2", "scipy", "scikit-learn", "toml",
    "huggingface_hub>=0.25.0,<1.0", "shapely", "bbox", "terminaltables", "open3d==0.18.0",
    "addict", "timm", "spconv-cu120", "accelerate", "tqdm",
]  # fmt: skip
SCATTER = "https://data.pyg.org/whl/torch-2.4.0+cu124/torch_scatter-2.1.2+pt24cu124-cp311-cp311-linux_x86_64.whl"
OUT = Path("/kaggle/working")
TMP = Path("/kaggle/tmp")
LOG = OUT / "log.txt"


def log(msg: str) -> None:
    print(msg, flush=True)
    with LOG.open("a") as f:
        f.write(msg + "\n")


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if res.returncode:
        log(f"FAILED {' '.join(cmd[:6])} ...\n{res.stdout[-3000:]}\n{res.stderr[-3000:]}")
    return res


def setup() -> Path:
    TMP.mkdir(parents=True, exist_ok=True)
    sh([sys.executable, "-m", "pip", "install", "-q", "uv"])
    venv = TMP / "venv"
    if sh([sys.executable, "-m", "uv", "venv", "-q", "-p", "3.11", str(venv)]).returncode:
        sys.exit(1)
    py = venv / "bin" / "python"
    base = [sys.executable, "-m", "uv", "pip", "install", "-q", "-p", str(py)]
    idx = ["--extra-index-url", "https://download.pytorch.org/whl/cu124",
           "--index-strategy", "unsafe-best-match"]  # fmt: skip
    if sh([*base, *idx, *REQS]).returncode or sh([*base, SCATTER]).returncode:
        sys.exit(1)
    repo = TMP / "SpatialLM"
    sh(["git", "clone", "-q", "https://github.com/manycore-research/SpatialLM", str(repo)])
    sh(["git", "-C", str(repo), "checkout", "-q", SPATIALLM_REV])
    for f in ("spatiallm_qwen.py", "spatiallm_llama.py"):  # T4: no flash attention
        p = repo / "spatiallm" / "model" / f
        s = p.read_text()
        # the encoder may sit on another GPU: move its input there, make that GPU current
        # (spconv / torch_scatter launch on the current device; run 2 hit device asserts)
        # and bring the output back
        call = "            encoded_features = self.point_backbone(input_dict)\n"
        s = s.replace(
            call,
            "            pb = next(self.point_backbone.parameters()).device\n"
            "            input_dict = {k: v.to(pb) if torch.is_tensor(v) else v\n"
            "                          for k, v in input_dict.items()}\n"
            "            with torch.cuda.device(pb):\n"
            "                encoded_features = self.point_backbone(input_dict).to(device)\n",
        )
        p.write_text(
            s.replace(
                "enable_fourier_encode=True,", "enable_fourier_encode=True, enable_flash=False,"
            )
        )
    inf = repo / "inference.py"
    s = inf.read_text()
    two_gpus = (
        '    model.to("cuda")\n'
        "    if torch.cuda.device_count() > 1:\n"
        '        model.point_backbone.to("cuda:1")\n'
    )
    inf.write_text(s.replace('    model.to("cuda")\n', two_gpus))
    check = (
        "import torch, spconv.pytorch, torch_scatter, open3d; "
        "print(torch.__version__, torch.cuda.is_available(), torch.cuda.device_count(), "
        "torch.cuda.get_device_name(0))"
    )
    gpu = sh([str(py), "-c", check])
    log(f"venv: {gpu.stdout.strip()} {gpu.stderr[-500:]}")
    if "True" not in gpu.stdout:
        log("NO GPU (or broken torch) in the venv; nothing to run")
        sys.exit(1)
    return repo


def main() -> None:
    sh(["nvidia-smi", "-L"])
    repo = setup()
    py = TMP / "venv" / "bin" / "python"
    clouds = sorted(Path("/kaggle/input").rglob("*.ply"))
    log(f"clouds: {[c.name for c in clouds]}")
    rows = []
    for model in MODELS:
        for cloud in clouds:
            if "Qwen" in model and cloud.stem != "c_home_01":
                continue  # run 1 already has these
            for seed in SEEDS:
                tag = f"{cloud.stem}__{model.split('/')[-1]}__s{seed}"
                start = time.perf_counter()
                res = subprocess.run(
                    [str(py), "inference.py", "--point_cloud", str(cloud), "--output",
                     str(OUT / f"{tag}.txt"), "--model_path", model, "--detect_type", "arch",
                     "--inference_dtype", "float32", "--seed", str(seed)],
                    cwd=repo, capture_output=True, text=True,
                    env={
                        **os.environ,
                        "PYTHONPATH": str(repo),
                        "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
                    },
                )  # fmt: skip
                secs = round(time.perf_counter() - start, 1)
                ok = res.returncode == 0 and (OUT / f"{tag}.txt").exists()
                log(f"== {tag} exit {res.returncode} {secs}s"
                    + ("" if ok else f"\n{res.stdout[-2000:]}\n{res.stderr[-4000:]}"))  # fmt: skip
                rows.append({"tag": tag, "ok": ok, "seconds": secs})
    (OUT / "summary.json").write_text(json.dumps(rows, indent=2))
    log("done")


main()
