"""Score video-tier plans of home C (Camera-app videos) against our LiDAR plan and Polycam.

A Camera-app video has no poses, so its plan sits in its own frame. Its rooms are placed
onto the LiDAR plan by the best of four 90 degree rotations plus the translation that
maximises footprint overlap (FFT cross-correlation of the rasterised floors), then matched
to the LiDAR rooms by IoU. Room names follow data/gt/home_c_rooms.json; Polycam numbers
come from data/gt/home_c_polycam.json (a competitor, not ground truth). The LiDAR is the
provisional reference until tape measurements arrive.

Usage: uv run scripts/score_video_c.py <video plan.json> [--lidar outputs/c_home_01_lidar/plan.json]
"""

import argparse
import json
from pathlib import Path

import numpy as np
from matplotlib.path import Path as PolyPath
from scipy.signal import fftconvolve

RES = 0.05
LABELS = Path("data/gt/home_c_rooms.json")
POLYCAM = Path("data/gt/home_c_polycam.json")


def raster(polys: list[np.ndarray], lo: np.ndarray, shape: tuple) -> np.ndarray:
    yy, xx = np.mgrid[: shape[0], : shape[1]]
    cells = np.column_stack([xx.ravel(), yy.ravel()]) * RES + lo + RES / 2
    m = np.zeros(len(cells), bool)
    for p in polys:
        m |= PolyPath(p).contains_points(cells)
    return m.reshape(shape)


def rot(p: np.ndarray, k: int) -> np.ndarray:
    a = np.pi / 2 * k
    return p @ np.array([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]])


def place(video: list[np.ndarray], lidar: list[np.ndarray]) -> tuple[list[np.ndarray], float]:
    """Video polygons moved onto the LiDAR frame (best rotation + translation), and the IoU."""
    allp = np.concatenate(lidar)
    lo = allp.min(0) - 3
    shape = tuple((np.ceil((allp.max(0) + 3 - lo) / RES)).astype(int)[::-1])
    ref = raster(lidar, lo, shape).astype(float)
    best = (-1.0, None)
    for k in range(4):
        pr = [rot(p, k) for p in video]
        c = np.concatenate(pr)
        vlo = c.min(0)
        vshape = tuple((np.ceil((c.max(0) - vlo) / RES) + 1).astype(int)[::-1])
        v = raster([p - vlo + lo for p in pr], lo, vshape).astype(float)
        corr = fftconvolve(ref, v[::-1, ::-1], mode="full")
        iy, ix = np.unravel_index(np.argmax(corr), corr.shape)
        shift = np.array([ix - (v.shape[1] - 1), iy - (v.shape[0] - 1)]) * RES
        moved = [p - vlo + lo + shift for p in pr]
        inter = corr[iy, ix]
        iou = inter / (ref.sum() + v.sum() - inter)
        if iou > best[0]:
            best = (iou, moved)
    return best[1], float(best[0])


def dims(p: np.ndarray) -> list[float]:
    return sorted(np.ptp(p, axis=0).round(2).tolist(), reverse=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan", type=Path)
    ap.add_argument("--lidar", type=Path, default=Path("outputs/c_home_01_lidar/plan.json"))
    args = ap.parse_args()
    vid = json.loads(args.plan.read_text())
    lid = json.loads(args.lidar.read_text())
    poly = json.loads(POLYCAM.read_text())
    match = poly["match_to_lidar_c_home_01"]
    vrooms = [np.asarray(r["polygon"]) for r in vid["rooms"]]
    lrooms = [np.asarray(r["polygon"]) for r in lid["rooms"]]
    if not vrooms:
        print("no rooms in the video plan")
        return
    placed, iou = place(vrooms, lrooms)

    names = {}  # LiDAR room id -> label name, by overlap with the hand-drawn boxes
    if lid["capture"]["id"] == "c_home_01":
        for r, p in zip(lid["rooms"], lrooms, strict=True):
            c = p.mean(0)
            for name, (x0, y0, x1, y1) in json.loads(LABELS.read_text())["rooms"].items():
                if x0 <= c[0] <= x1 and y0 <= c[1] <= y1:
                    names[r["id"]] = name
    else:  # a single-room scan of the damage room
        names = {lid["rooms"][0]["id"]: "room1"}

    allp = np.concatenate(lrooms + placed)
    lo = allp.min(0) - 1
    shape = tuple((np.ceil((allp.max(0) + 1 - lo) / RES)).astype(int)[::-1])
    lm = [raster([p], lo, shape) for p in lrooms]
    vm = [raster([p], lo, shape) for p in placed]
    print(f"{args.plan}: {len(vrooms)} video rooms, footprint IoU vs LiDAR {iou:.2f}")
    fp = vid["footprint_area"]
    ref = lid["footprint_area"]["value"]
    print(f"footprint {fp['value']:.1f} [{fp['lo']:.1f}, {fp['hi']:.1f}] m2 vs LiDAR {ref:.1f}, "
          f"Polycam {poly['total_area_m2']} (gross)")  # fmt: skip
    print("room     | video area [90%]       | LiDAR | Polycam | video dims  | LiDAR dims  "
          "| Polycam dims | ceil video [90%]  | LiDAR ceil | IoU")  # fmt: skip
    used = set()
    for i, r in enumerate(lid["rooms"]):
        ious = [(lm[i] & v).sum() / max((lm[i] | v).sum(), 1) for v in vm]
        j = int(np.argmax(ious))
        if ious[j] < 0.2 or j in used:
            print(f"{names.get(r['id'], r['id']):8} | not found in the video plan")
            continue
        used.add(j)
        v = vid["rooms"][j]
        name = names.get(r["id"], r["id"])
        pc = poly["rooms"][match[name].split()[0]] if name in match else {}
        pdims = sorted([pc["width"], pc["depth"]], reverse=True) if pc else "-"
        a, c, lc = v["floor_area"], v["ceiling_height"], r["ceiling_height"]
        ctxt = f"{c['value']:.2f} [{c['lo']:.2f},{c['hi']:.2f}]" if c else "none"
        print(
            f"{name:8} | {a['value']:5.1f} [{a['lo']:5.1f}, {a['hi']:5.1f}] | "
            f"{r['floor_area']['value']:5.1f} | {pc.get('area_m2', '-'):>7} | "
            f"{dims(placed[j])} | {dims(lrooms[i])} | {pdims} | {ctxt:17} | "
            f"{lc['value'] if lc else '-':.2f} | {ious[j]:.2f}"
        )
    extra = [vid["rooms"][j]["id"] for j in range(len(vrooms)) if j not in used]
    if extra:
        print(f"video rooms with no LiDAR match: {extra}")


if __name__ == "__main__":
    main()
