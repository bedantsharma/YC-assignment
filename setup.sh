#!/bin/sh
# One-time setup on a Mac (Apple Silicon): installs everything the pipeline needs.
#   ./setup.sh            everything (~15 min on a good connection, ~7 GB of downloads)
#   ./setup.sh --lite     LiDAR tier only (~2 min)
set -e
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "== Installing uv (the Python package manager this project uses)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

if [ "$1" = "--lite" ]; then
  echo "== Installing the pipeline (LiDAR tier only)"
  uv sync
else
  echo "== Installing the pipeline with the video/photo model and the offline damage model"
  uv sync --extra video --extra offline
  echo "== Downloading the offline damage model (Florence-2-base, 0.5 GB)"
  uv run python -m floorplan.damage_local --fetch
  echo "== Downloading the reconstruction model (Pi3X, 5.4 GB) for runs without Kaggle"
  uv run python -m floorplan.mvs_local --fetch pi3x
fi
# ffmpeg: the system one if present (e.g. Homebrew), else the copy bundled with the video
# extra (imageio-ffmpeg), so no Homebrew is needed
echo "== Done. Run a capture with:  ./run.sh <capture folder or video file>"
