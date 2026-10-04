"""Calibration (brief G10): how often each tier's 90% intervals contain home C's truth.

Checks per room matched to the ground truth (data/gt/home_c.json), as in gt_table.py:

- side: the room's longest wall along each plan axis vs the truth's side on that axis (the
  axis with the larger extent is the long side); skipped where that wall is shorter than 90%
  of the room's extent (a notched side: no single wall spans it). The wall-length interval
  is the one in plan.json, which comes from the two walls at its ends.
- ceiling: where the ceiling was taped (bedroom, dining & living).
- area: reported separately: the truth's areas are the drawing's nominal rectangles, while
  the bedroom has a closet and the drawing room a pooja niche, so area misses are expected.

Target: about 90% of sides and ceilings inside. Prints one table per tier and the misses.

Usage: uv run scripts/calibration.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import gt_table as gt  # noqa: E402

PLANS = [  # (tier, plan.json, how rooms are matched, as in gt_table.plan_rows)
    ("lidar", "outputs/c_home_01_lidar/plan.json", "lidar"),
    ("lidar", "outputs/c_damage_01_lidar/plan.json", "single"),
    ("lidar", "outputs/c_damage_02_lidar/plan.json", "single"),
    ("video", "outputs/c_home_01_video/plan.json", "place"),
    *[
        ("video", f"outputs/video_c/f{n}/{v}_video/plan.json", "single")
        for v in ("c_damage_v1", "c_damage_v2")
        for n in (30, 60)
    ],
    *[
        ("photo", f"outputs/photo_runs/{c}_{k}/{k}_photo/plan.json", how)
        for c, how in (
            ("c_home_01", "folders"),
            ("c_damage_01", "single"),
            ("c_damage_02", "single"),
        )  # fmt: skip
        for k in ("k8", "k8p")
    ],
]


def matched(plan: dict, how: str) -> list[tuple[str, dict]]:
    rooms = plan["rooms"]
    if how == "single":
        return [("bedroom", r) for r in rooms[:1]]
    if how == "folders":
        return [(gt.BY_LABEL.get(r["label"]), r) for r in rooms]
    if how == "lidar":
        return [(gt.box_room(np.asarray(r["polygon"])), r) for r in rooms]
    lid = [np.asarray(r["polygon"]) for r in gt.LIDAR_HOME["rooms"]]
    placed, _ = gt.place([np.asarray(r["polygon"]) for r in rooms], lid)
    return [(gt.box_room(q), r) for q, r in zip(placed, rooms, strict=True)]


def checks(key: str, room: dict) -> list[tuple[str, float, dict]]:
    g = gt.GT["rooms"][key]
    poly = np.asarray(room["polygon"])
    ext = np.ptp(poly, axis=0)
    long_axis = int(np.argmax(ext))
    sides = {
        long_axis: max(g["width_m"], g["depth_m"]),
        1 - long_axis: min(g["width_m"], g["depth_m"]),
    }
    out = []
    for axis, truth in sides.items():
        along = [w for w in room["walls"] if abs(w["end"][axis] - w["start"][axis]) > 1e-6]
        w = max(along, key=lambda w: w["length"]["value"], default=None)
        if w and w["length"]["value"] > 0.9 * ext[axis]:  # a notched side has no full wall
            out.append(("long" if axis == long_axis else "short", truth, w["length"]))
    c = g.get("measured", {}).get("ceiling_height_m")
    if c and room["ceiling_height"]:
        out.append(("ceiling", c, room["ceiling_height"]))
    out.append(("area", g["area_m2"], room["floor_area"]))
    return out


def main() -> None:
    import json

    per_tier: dict[str, dict[str, list]] = {}
    misses = []
    for tier, path, how in PLANS:
        p = Path(path)
        if not p.exists():
            continue
        plan = json.loads(p.read_text())
        seen = set()
        for key, room in matched(plan, how):
            if key is None or key in seen:
                continue
            seen.add(key)
            for kind, truth, m in checks(key, room):
                inside = m["lo"] <= truth <= m["hi"]
                group = "area" if kind == "area" else "side" if kind in ("long", "short") else kind
                per_tier.setdefault(tier, {}).setdefault(group, []).append(
                    (inside, (m["hi"] - m["lo"]) / 2, m["value"] - truth)
                )
                if not inside and group != "area":
                    got = f"{m['value']:.2f} [{m['lo']:.2f}, {m['hi']:.2f}]"
                    misses.append(f"{tier:5} {p.parent.parent.name}/{p.parent.name:28} {key:13} "
                                  f"{kind:7} truth {truth:.2f} got {got}")  # fmt: skip
    print("| Tier | Check | Inside the 90% interval | Mean half-width | Mean abs. error |")
    print("|---|---|---|---|---|")
    for tier, groups in per_tier.items():
        for group, rows in groups.items():
            ins = sum(r[0] for r in rows)
            unit = "m²" if group == "area" else "m"
            print(f"| {tier} | {group} | {ins} of {len(rows)} ({100 * ins / len(rows):.0f}%) | "
                  f"{np.mean([r[1] for r in rows]):.2f} {unit} | "
                  f"{np.mean([abs(r[2]) for r in rows]):.2f} {unit} |")  # fmt: skip
    print("\nMisses (sides and ceilings):")
    print("\n".join(misses) or "none")


if __name__ == "__main__":
    main()
