"""Drift-correction ablation: every LiDAR capture with drift correction off and on.

Wall-face spread is the sharpness measure: drift puts a revisited wall in two places, which
widens the face the wall snaps to, and with it the wall's interval. Reported per capture:
rooms, total area, and the median / 90th percentile of wall half-intervals (cm, observed
walls only), off -> on. Writes plans to outputs/drift_off/ and outputs/drift_on/.

Usage: uv run scripts/drift_ablation.py
"""

import json
import sys
from pathlib import Path

import numpy as np

from floorplan.cli import main as floorplan

CAPTURES = [
    *sorted(Path("data/raw").glob("*/")),
    *sorted(Path("data/arkitscenes/raw/Validation").glob("*/")),
    *sorted(Path("data/home_c/lidar").glob("*/")),
]


def stats(plan: dict) -> tuple[int, float, float, float, str]:
    rooms = plan["rooms"]
    half = [
        100 * (w["length"]["hi"] - w["length"]["value"])
        for r in rooms
        for w in r["walls"]
        if w["observed"]
    ]
    area = sum(r["floor_area"]["value"] for r in rooms)
    drift = next((w for w in plan["warnings"] if w.startswith("drift:")), "")
    med, p90 = (np.median(half), np.percentile(half, 90)) if half else (np.nan, np.nan)
    return len(rooms), area, med, p90, drift.removeprefix("drift: ")


def main() -> None:
    rows = []
    for cap in CAPTURES:
        res = {}
        for mode, flag in (("off", []), ("on", ["--drift"])):
            out = Path(f"outputs/drift_{mode}")
            args = ["run", str(cap), "--tier", "lidar", "--out", str(out), *flag]
            if floorplan(args) != 0:
                sys.exit(f"failed on {cap}")
            res[mode] = stats(json.loads((out / f"{cap.name}_lidar" / "plan.json").read_text()))
        rows.append((cap.name, res["off"], res["on"]))

    print("\n| Capture | Rooms | Area (m²) | Wall ±, median (cm) | Wall ±, p90 (cm) | Correction |")
    print("|---|---|---|---|---|---|")
    for name, off, on in rows:
        print(
            f"| {name} | {off[0]} → {on[0]} | {off[1]:.1f} → {on[1]:.1f} "
            f"| {off[2]:.1f} → {on[2]:.1f} | {off[3]:.1f} → {on[3]:.1f} | {on[4]} |"
        )


if __name__ == "__main__":
    main()
