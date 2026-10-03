"""Run the LiDAR tier on every LiDAR capture on disk and print one summary table.

Used for before/after comparisons in the fix loop (docs/fix_loop.md): rooms found, room
areas and ceilings per capture. Writes each plan to outputs/<id>_lidar/ as `floorplan run`
does.

Usage: uv run scripts/lidar_summary.py [--out outputs]
"""

import argparse
import json
import sys
from pathlib import Path

from floorplan.cli import main as floorplan

CAPTURES = [
    *sorted(Path("data/raw").glob("*/")),
    *sorted(Path("data/arkitscenes/raw/Validation").glob("*/")),
    *sorted(Path("data/home_c/lidar").glob("*/")),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("outputs"))
    args = ap.parse_args()

    rows = []
    for cap in CAPTURES:
        if floorplan(["run", str(cap), "--tier", "lidar", "--out", str(args.out)]) != 0:
            sys.exit(f"failed on {cap}")
        plan = json.loads((args.out / f"{cap.name}_lidar" / "plan.json").read_text())
        rooms = plan["rooms"]
        areas = " ".join(f"{r['floor_area']['value']:.1f}" for r in rooms)
        ceils = " ".join(
            f"{r['ceiling_height']['value']:.2f}" if r["ceiling_height"] else "-" for r in rooms
        )
        rows.append((cap.name, len(rooms), areas, ceils))
    print("\n| Capture | Rooms | Areas (m²) | Ceilings (m) |\n|---|---|---|---|")
    for name, n, areas, ceils in rows:
        print(f"| {name} | {n} | {areas} | {ceils} |")


if __name__ == "__main__":
    main()
