"""Score room segmentation against hand-labelled rooms (identity, not dimensions).

Each labelled room is matched one-to-one to the detected room with the highest IoU
(intersection over union of their plan areas). A labelled room counts as found if its
match has IoU >= 0.5. A detected room that covers >= 30% of two labelled rooms is a merge.

Usage: uv run scripts/score_rooms.py [--plan outputs/c_home_01_lidar/plan.json]
                                     [--labels data/gt/home_c_rooms.json]
"""

import argparse
import json
from pathlib import Path

import numpy as np
from matplotlib.path import Path as PolyPath

RES = 0.02
FOUND_IOU = 0.5
MERGE_COVER = 0.3


def raster(polygon: list, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    xx, yy = np.meshgrid(xs, ys)
    cells = np.column_stack([xx.ravel(), yy.ravel()])
    inside = PolyPath(np.asarray(polygon)).contains_points(cells)
    return inside.reshape(xx.shape)


def box(x0: float, y0: float, x1: float, y1: float) -> list:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def score(plan: dict, labels: dict) -> dict:
    truth = {name: box(*b) for name, b in labels["rooms"].items()}
    found = {r["id"]: r["polygon"] for r in plan["rooms"]}
    corners = np.concatenate([np.asarray(p) for p in [*truth.values(), *found.values()]])
    lo, hi = corners.min(axis=0) - 0.1, corners.max(axis=0) + 0.1
    xs, ys = np.arange(lo[0], hi[0], RES), np.arange(lo[1], hi[1], RES)
    t = {k: raster(p, xs, ys) for k, p in truth.items()}
    f = {k: raster(p, xs, ys) for k, p in found.items()}
    iou = {(a, b): (t[a] & f[b]).sum() / max((t[a] | f[b]).sum(), 1) for a in t for b in f}

    matches, used = {}, set()
    for (a, b), v in sorted(iou.items(), key=lambda kv: -kv[1]):
        if a not in matches and b not in used and v > 0:
            matches[a] = (b, v)
            used.add(b)
    merges = [b for b in f if sum((t[a] & f[b]).sum() >= MERGE_COVER * t[a].sum() for a in t) >= 2]
    n_found = sum(v >= FOUND_IOU for _, v in matches.values())
    return {"matches": matches, "merges": merges, "found": n_found, "n_truth": len(t),
            "n_detected": len(f), "unmatched": sorted(set(f) - used)}  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", type=Path, default=Path("outputs/c_home_01_lidar/plan.json"))
    ap.add_argument("--labels", type=Path, default=Path("data/gt/home_c_rooms.json"))
    args = ap.parse_args()
    plan = json.loads(args.plan.read_text())
    s = score(plan, json.loads(args.labels.read_text()))
    area = {r["id"]: r["floor_area"]["value"] for r in plan["rooms"]}
    print(f"{args.plan}: {s['n_detected']} rooms detected, {s['n_truth']} labelled")
    for name, (rid, v) in s["matches"].items():
        ok = "found" if v >= FOUND_IOU else "MISSED"
        print(f"  {name:8s} -> {rid:4s} IoU {v:.2f}  {area[rid]:6.2f} m2  {ok}")
    for name in sorted(set(json.loads(args.labels.read_text())["rooms"]) - set(s["matches"])):
        print(f"  {name:8s} -> none          MISSED")
    print(f"  merged rooms (cover 2+ labelled rooms): {s['merges'] or 'none'}")
    print(f"  unmatched detections (fragments/extra): {s['unmatched'] or 'none'}")
    print(f"ROOMS FOUND: {s['found']}/{s['n_truth']}")


if __name__ == "__main__":
    main()
