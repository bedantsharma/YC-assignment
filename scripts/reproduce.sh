#!/usr/bin/env bash
# Regenerate every reported number from the raw captures (README "Reproduce").
#
# LiDAR: all 9 captures run live. Video and photo: the reconstruction model runs on Kaggle
# (kaggle/video_runs, kaggle/cache_runs); this replays its cached output (outputs/*/
# recon_cache), so no model runs here. Then damage (cached model answers), the comparison
# tables and the reports. Raw data and caches: scripts/fetch_data.sh <URL from submission>.
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

# The friend's real photos (all / 8 / 5 per room)
export FLOORPLAN_RECON_CACHE=outputs/recon_cache_photos
for k in all k8 k5; do
  uv run --extra video floorplan run "data/home_c/photo_sets/$k" --out outputs/photo_real
done

# Damage: every model answer replays from data/damage_cache (no network, no weights)
export FLOORPLAN_DAMAGE_CACHE_ONLY=1
for c in c_damage_01 c_damage_02; do
  uv run floorplan run "data/home_c/lidar/$c" --damage --out outputs/damage_lidar
  FLOORPLAN_DAMAGE_DETECTOR=florence uv run floorplan run "data/home_c/lidar/$c" --damage \
    --out outputs/damage_lidar_offline
done
export FLOORPLAN_RECON_CACHE=outputs/kaggle_video_runs/recon_cache
for v in c_damage_v1 c_damage_v2; do
  uv run --extra video floorplan run "$VIDEOS/$v.mp4" --tier video --frames 60 --damage \
    --out outputs/damage_video
done
export FLOORPLAN_RECON_CACHE=outputs/recon_cache_photos
uv run --extra video floorplan run data/home_c/photo_sets/k8 --damage --out outputs/damage_photo
uv run scripts/damage_hole_check.py --md > /dev/null
# docs/damage_models.md (scripts/damage_compare.py) also replays from the cache, but its
# timing column was measured on the live run, so it is not regenerated here.

uv run scripts/gt_table.py > /dev/null
uv run scripts/calibration.py > /dev/null
uv run scripts/benchmark.py > /dev/null
echo "regenerated: docs/gt_comparison.md, docs/benchmark_report.md, docs/damage_hole.md"
