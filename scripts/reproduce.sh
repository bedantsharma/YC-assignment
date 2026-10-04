#!/usr/bin/env bash
# Regenerate every reported number from the raw captures (README "Reproduce").
#
# LiDAR: all 9 captures run live. Video and photo: the reconstruction model runs on Kaggle
# (kaggle/video_runs, kaggle/cache_runs); this replays its cached output (outputs/*/
# recon_cache), so no model runs here. Then the comparison tables and the reports.
#
# Usage: scripts/reproduce.sh [video dir (default data/home_c/video)]
set -euo pipefail
VIDEOS=${1:-data/home_c/video}
HOME_RGB=${HOME_RGB:-data/home_c/lidar/c_home_01/rgb.mp4}

uv run scripts/lidar_summary.py

export FLOORPLAN_RECON_CACHE_ONLY=1
export FLOORPLAN_RECON_CACHE=outputs/kaggle_video_runs/recon_cache
for n in 30 60; do
  for v in c_damage_v1 c_damage_v2; do
    uv run --extra video floorplan run "$VIDEOS/$v.mp4" --tier video --frames $n --out outputs/video_c/f$n
  done
done
for n in 90 150; do
  uv run --extra video floorplan run "$VIDEOS/c_home_v1.mp4" --tier video --frames $n --out outputs/video_c/f$n
done

export FLOORPLAN_RECON_CACHE=outputs/kaggle_cache_runs/recon_cache
if [ -d "$FLOORPLAN_RECON_CACHE" ]; then
  tmp=$(mktemp -d)
  ln -s "$(cd "$(dirname "$HOME_RGB")" && pwd)/$(basename "$HOME_RGB")" "$tmp/c_home_01.mp4"
  uv run --extra video floorplan run "$tmp/c_home_01.mp4" --tier video --frames 90 --out outputs
  for c in c_home_01 c_damage_01 c_damage_02; do
    for k in k8 k8p; do
      uv run --extra video floorplan run "data/home_c/photos_sim/$c/$k" --out "outputs/photo_runs/${c}_$k"
    done
  done
fi

uv run scripts/gt_table.py > /dev/null
uv run scripts/benchmark.py > /dev/null
echo "regenerated: docs/gt_comparison.md, docs/benchmark_report.md"
