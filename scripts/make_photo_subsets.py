"""Photo-tier test sets from the friend's real photos of home C (data/home_c/photos/<room>/).

The friend took 26-33 photos per room; the brief's photo contract is 2-8 per room. Each set
keeps K photos per room, evenly spaced in shooting order (file name = iPhone counter), so
the pick is a fixed rule, not a hand choice. `all` keeps every photo.

The photos arrive as iPhone ProRAW (.DNG), which PIL cannot read; they were converted once
on the laptop with macOS sips to sRGB JPEG, long side 1920:
  sips -s format jpeg -s formatOptions 92 -Z 1920 \
       -m "/System/Library/ColorSync/Profiles/sRGB Profile.icc" IMG.DNG --out IMG.jpg

Output: data/home_c/photo_sets/<set>/<room>/*.jpg + manifest.json.
Usage: uv run scripts/make_photo_subsets.py [--k 8 5]
"""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np

SRC = Path("data/home_c/photos")
OUT = Path("data/home_c/photo_sets")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, nargs="+", default=[8, 5])
    args = ap.parse_args()
    rooms = {d.name: sorted(d.glob("*.jpg")) for d in sorted(SRC.iterdir()) if d.is_dir()}
    rooms = {name: photos for name, photos in rooms.items() if photos}
    sets = {"all": None, **{f"k{k}": k for k in args.k}}
    for name, k in sets.items():
        manifest = {}
        for room, photos in rooms.items():
            idx = range(len(photos)) if k is None or k >= len(photos) else (
                np.linspace(0, len(photos) - 1, k).round().astype(int)
            )  # fmt: skip
            dst = OUT / name / room
            shutil.rmtree(dst, ignore_errors=True)
            dst.mkdir(parents=True)
            for i in idx:
                shutil.copy2(photos[i], dst / photos[i].name)
            manifest[room] = [photos[i].name for i in idx]
        (OUT / name / "manifest.json").write_text(json.dumps(manifest, indent=1))
        print(name, {r: len(v) for r, v in manifest.items()})


if __name__ == "__main__":
    main()
