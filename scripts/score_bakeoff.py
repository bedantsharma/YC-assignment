"""Score the Kaggle model bake-off locally against the LiDAR of the same recordings.

Each model's points and camera poses (outputs/bakeoff/<capture>__<model>__<n>.npz, from
`kaggle kernels output bedantsharma/floorplan-model-bakeoff`) go through the video tier's
RGB-only steps (vertical from wall normals, z up) and the shared `build_plan`. Reference,
for evaluation only: the LiDAR plan of the same recording and ARKit camera centres at the
same frame times (scale and trajectory error after a similarity fit).

Usage: uv run scripts/score_bakeoff.py [--dir outputs/bakeoff]
"""

import argparse
import json
from pathlib import Path

import numpy as np

from floorplan.capture import load_lidar
from floorplan.lidar import build_plan
from floorplan.pipeline import run
from floorplan.video import duration, estimate_up, z_up

FPS = 60  # Stray rgb.mp4: frame index = time * 60 = depth / pose index


def umeyama(src: np.ndarray, dst: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    mu_s, mu_d = src.mean(0), dst.mean(0)
    a, b = src - mu_s, dst - mu_d
    u, d, vt = np.linalg.svd(b.T @ a / len(src))
    sign = np.eye(3)
    sign[2, 2] = np.sign(np.linalg.det(u @ vt))
    r = u @ sign @ vt
    s = float(np.trace(np.diag(d) @ sign) / a.var(0).sum())
    return s, r, mu_d - s * r @ mu_s


def rooms_text(rooms) -> str:
    return "; ".join(
        f"{r.floor_area.value:.1f} m², walls {' '.join(f'{w.length.value:.2f}' for w in r.walls)}"
        for r in rooms
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=Path("outputs/bakeoff"))
    args = ap.parse_args()

    lidar_plans, rows = {}, []
    for f in sorted(args.dir.glob("*.npz")):
        cap, model, n = f.stem.split("__")
        n = int(n)
        src = Path("data/home_c/lidar") / cap
        if cap not in lidar_plans:
            lidar_plans[cap] = run(src, "lidar")
        d = np.load(f)
        pts, poses = d["points"].astype(float), d["poses"]

        times = np.linspace(0.5, duration(src / "rgb.mp4") - 0.5, n)
        ref = load_lidar(src).poses
        idx = np.clip((times * FPS).round().astype(int), 0, len(ref) - 1)
        s, r, t = umeyama(poses[:, :3, 3], ref[idx, :3, 3])
        ate = np.linalg.norm(s * poses[:, :3, 3] @ r.T + t - ref[idx, :3, 3], axis=1)

        plan = build_plan(z_up(pts, estimate_up(pts, poses)))
        lid = lidar_plans[cap]
        area = sum(r_.floor_area.value for r_ in plan.rooms)
        lid_area = sum(r_.floor_area.value for r_ in lid.rooms)
        ceil = [r_.ceiling_height.value for r_ in plan.rooms if r_.ceiling_height]
        rows.append(
            {
                "capture": cap,
                "model": model,
                "frames": n,
                "scale_vs_arkit": round(s, 3),
                "ate_median_m": round(float(np.median(ate)), 3),
                "rooms": len(plan.rooms),
                "lidar_rooms": len(lid.rooms),
                "area": round(area, 2),
                "lidar_area": round(lid_area, 2),
                "area_err_pct": round(100 * (area - lid_area) / lid_area, 1) if lid_area else None,
                "ceiling": round(float(np.median(ceil)), 2) if ceil else None,
                "plan": rooms_text(plan.rooms),
                "lidar_plan": rooms_text(lid.rooms),
            }
        )

    cols = ["capture", "model", "frames", "scale_vs_arkit", "ate_median_m", "rooms"]
    cols += ["lidar_rooms", "area", "lidar_area", "area_err_pct", "ceiling"]
    print("\n| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for r in rows:
        print("| " + " | ".join(str(r[c]) for c in cols) + " |")
    print()
    for r in rows:
        print(
            f"{r['capture']} {r['model']} {r['frames']}: {r['plan']}\n    LiDAR: {r['lidar_plan']}"
        )
    (args.dir / "scores.json").write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
