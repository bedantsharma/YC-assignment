#!/usr/bin/env bash
# Download one ARKitScenes venue: its repeat captures (LiDAR depth, confidence, poses,
# intrinsics, video) plus laser-scanner ground truth.
#
# Usage: scripts/fetch_arkitscenes.sh [visit_id] [n_laser_stations]
#   defaults: visit 421337 (3 captures), 1 laser station (~1.9 GB each)
set -euo pipefail

VISIT="${1:-421337}"
N_LASER="${2:-1}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)/data/arkitscenes"
BASE=https://docs-assets.developer.apple.com/ml-research/datasets/arkitscenes/v1
mkdir -p "$ROOT/raw"
cd "$ROOT"

[ -f download_data.py ] || curl -sfL -O https://raw.githubusercontent.com/apple/ARKitScenes/main/download_data.py
[ -f raw/metadata.csv ] || curl -sf -o raw/metadata.csv "$BASE/raw/metadata.csv"
[ -f raw/laser_mapping.csv ] || curl -sf -o raw/laser_mapping.csv \
    "$BASE/raw/laser_scanner_point_clouds/laser_scanner_point_clouds_mapping.csv"

# Videos of this visit, one "video_id split" per line (macOS bash 3.2: no mapfile)
awk -F, -v v="$VISIT" '$2==v || $2==v".0" {print $1" "$4}' raw/metadata.csv |
while read -r vid split; do
    echo "capture $vid ($split)"
    uv run --with pandas python download_data.py raw --split "$split" --video_id "$vid" \
        --download_dir "$ROOT" \
        --raw_dataset_assets mov lowres_depth confidence lowres_wide.traj lowres_wide_intrinsics \
        </dev/null
done

# Laser stations: the mapping lists some stations twice under different ids; keep the first N
mkdir -p "laser/$VISIT"
awk -F, -v v="$VISIT" '$2==v {print $1}' raw/laser_mapping.csv | head -n "$N_LASER" |
while read -r id; do
    for ext in .ply _pose.txt; do
        out="laser/$VISIT/$id$ext"
        [ -f "$out" ] || curl -sfL -o "$out" "$BASE/raw/laser_scanner_point_clouds/$VISIT/$id$ext" ||
            echo "warning: $id$ext not available"
    done
done
echo "done: $ROOT"
