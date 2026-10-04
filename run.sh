#!/bin/bash
# Process one capture and open the plan:  ./run.sh <capture> [options]
#   ./run.sh data/home_c/lidar/c_damage_01 --damage        a Stray Scanner folder (LiDAR)
#   ./run.sh walkthrough.mov --frames 60 --damage           a video
#   ./run.sh photos_folder --damage                         a folder with one subfolder per room
# Options are those of `uv run floorplan run --help`. Results: outputs/<name>_<tier>/
set -eo pipefail
cd "$(dirname "$0")"
[ -n "$1" ] || { sed -n 2,6p "$0"; exit 2; }
export PATH="$HOME/.local/bin:$PATH"
uv run floorplan run "$@" | tee /tmp/floorplan_last.txt
plan=$(sed -n 's/.*-> \(.*plan\.json\).*/\1/p' /tmp/floorplan_last.txt | head -1)
[ -n "$plan" ] && command -v open >/dev/null 2>&1 && open "$(dirname "$plan")/plan.png"
exit 0
