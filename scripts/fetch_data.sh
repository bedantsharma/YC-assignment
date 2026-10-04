#!/bin/bash
# Download the raw-data bundle (home C captures + model replay caches, ~2.8 GB), check it,
# and unpack it at the repo root (data/home_c/..., outputs/.../recon_cache).
#
#   scripts/fetch_data.sh <bundle URL>
#
# The URL is given in the submission (not in this public repo: the bundle is a private home).
# Built by scripts/make_bundle.py; contents in its MANIFEST.md.
set -eo pipefail
cd "$(dirname "$0")/.."
url=${1:?usage: scripts/fetch_data.sh <bundle URL from the submission>}
url=${url%/}
dl=outputs/bundle_download
mkdir -p "$dl"
for f in SHA256SUMS MANIFEST.md floorplan_home_c_raw.zip floorplan_replay_cache.zip; do
  echo "== $f"
  curl -fL --retry 3 -C - -o "$dl/$f" "$url/$f"
done
echo "== checking"
(cd "$dl" && shasum -a 256 -c SHA256SUMS)
for z in floorplan_home_c_raw.zip floorplan_replay_cache.zip; do
  echo "== unpacking $z"
  unzip -q -n "$dl/$z" -d .
done
echo "== done: data/home_c and the replay caches are in place; run scripts/reproduce.sh"
