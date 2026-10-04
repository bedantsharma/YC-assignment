"""Staged hole in home C's bedroom vs our damage output (LiDAR tier).

Truth (data/gt/home_c.json, the friend's tape): 2.5 in hole, centre 4.66 ft up, 7.5 ft
from the right-hand wall seen facing the damaged wall. Our wall coordinates: u along the
wall from its start corner, which seen from inside the room is the right-hand corner, and
v above the floor, so the truth is (u, v) = (2.286, 1.420) on the damaged wall.

The hole we report is the `hole` item whose centre is nearest that point on any wall; the
script prints it, whether each interval holds the truth, and every other damage item (the
false alarms, or other real damage such as the small holes at the wiring).

    uv run scripts/damage_hole_check.py [plan.json ...]
"""

import json
import math
import sys
from pathlib import Path

GT = json.loads(Path("data/gt/home_c.json").read_text())
HOLE = GT["rooms"]["bedroom"]["measured"]["damage"]
U, V = HOLE["from_right_wall_m"], HOLE["centre_height_m"]
AREA = math.pi * (HOLE["diameter_m"] / 2) ** 2
DEFAULT = [f"outputs/damage_lidar/{c}_lidar/plan.json" for c in ("c_damage_01", "c_damage_02")]


def check(path: Path) -> None:
    plan = json.loads(path.read_text())
    dmg = plan["damage"]
    print(f"\n== {path}  ({len(dmg)} damage items, {len(plan['flags'])} flags, "
          f"{len(plan['scope'])} scope items)")  # fmt: skip
    holes = [d for d in dmg if d["damage_class"] == "hole" and d["surface_id"].endswith(".face")]
    if not holes:
        print("   no hole on a wall")
    else:
        best = min(holes, key=lambda d: math.hypot(d["centre"][0] - U, d["centre"][1] - V))
        a = best["area"]
        u, v = best["centre"]
        diam = 2 * math.sqrt(a["value"] / math.pi)
        print(f"   staged hole -> {best['id']} on {best['surface_id']}, seen in "
              f"{len(best['views'])} views, score {best['score']}")  # fmt: skip
        print(f"   centre u {u:.3f} m (truth {U:.3f}, {100 * (u - U):+.1f} cm), "
              f"v {v:.3f} m (truth {V:.3f}, {100 * (v - V):+.1f} cm)")  # fmt: skip
        inside = a["lo"] <= AREA <= a["hi"]
        print(f"   area {1e4 * a['value']:.1f} cm2 [{1e4 * a['lo']:.1f}, {1e4 * a['hi']:.1f}] "
              f"vs truth {1e4 * AREA:.1f} cm2: {'inside' if inside else 'OUTSIDE'} the "
              f"interval; equivalent diameter {100 * diam:.1f} cm (truth "
              f"{100 * HOLE['diameter_m']:.2f})")  # fmt: skip
    for d in dmg:
        if holes and d is best:
            continue
        a = d["area"]
        print(f"   other: {d['id']} {d['damage_class']} on {d['surface_id']} at "
              f"({d['centre'][0]:.2f}, {d['centre'][1]:.2f}) area {1e4 * a['value']:.0f} cm2, "
              f"{len(d['views'])} views, score {d['score']} | {d['note'][:60]}")  # fmt: skip
    for f in plan["flags"]:
        print(f"   flag {f['rule_id']} on {f['surface_id']}: {f['damage_ids']}")
    for s in plan["scope"]:
        q = s["quantity"]
        print(f"   scope {s['action']} | {s['surface_id']} | {q['value']} {q['unit']} "
              f"[{q['lo']}, {q['hi']}]")  # fmt: skip


if __name__ == "__main__":
    for p in sys.argv[1:] or DEFAULT:
        check(Path(p))
