"""Exploration: fuse each Stray Scanner capture into a point cloud and plot top-down views.

Usage: uv run scripts/fuse_topdown.py [--data data/raw] [--out outputs/topdown_overview.png]
"""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation

DEPTH_W, DEPTH_H = 256, 192
RGB_W, RGB_H = 1920, 1440


def fuse(capture: Path, stride: int = 6, max_depth: float = 3.5) -> np.ndarray:
    """Back-project high-confidence depth into world coordinates (OpenCV camera convention)."""
    with open(capture / "odometry.csv") as f:
        rows = list(csv.reader(f))[1:]
    odom = np.array([[float(x) for x in r[:9]] for r in rows])
    K = np.loadtxt(capture / "camera_matrix.csv", delimiter=",")
    K = K * np.array([[DEPTH_W / RGB_W], [DEPTH_H / RGB_H], [1]])
    uu, vv = np.meshgrid(np.arange(DEPTH_W), np.arange(DEPTH_H))
    points = []
    for i in range(0, len(odom), stride):
        z = np.array(Image.open(capture / "depth" / f"{i:06d}.png")).astype(float) / 1000
        conf = np.array(Image.open(capture / "confidence" / f"{i:06d}.png"))
        m = (conf == 2) & (z > 0.1) & (z < max_depth)
        x = (uu[m] - K[0, 2]) * z[m] / K[0, 0]
        y = (vv[m] - K[1, 2]) * z[m] / K[1, 1]
        cam = np.stack([x, y, z[m]], 1)
        rot = Rotation.from_quat(odom[i, 5:9]).as_matrix()
        points.append(cam @ rot.T + odom[i, 2:5])
    return np.concatenate(points)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data/raw"))
    ap.add_argument("--out", type=Path, default=Path("outputs/topdown_overview.png"))
    args = ap.parse_args()

    captures = sorted(p for p in args.data.iterdir() if (p / "odometry.csv").exists())
    fig, ax = plt.subplots(len(captures), 3, figsize=(18, 6 * len(captures)), squeeze=False)
    for k, capture in enumerate(captures):
        P = fuse(capture)
        y = P[:, 1]
        h, e = np.histogram(y, bins=np.arange(y.min(), y.max(), 0.01))
        floor = e[np.argmax(h)]

        H, xe, ze = np.histogram2d(P[:, 0], P[:, 2], bins=500)
        ax[k, 0].imshow(np.log1p(H.T), origin="lower", extent=[xe[0], xe[-1], ze[0], ze[-1]])
        ax[k, 0].set_title(f"{capture.name}: all points, top-down")

        # world y is vertical; floor sits below the camera, so wall band is floor + 0.9..1.6 m
        band = (y > floor + 0.9) & (y < floor + 1.6)
        H, xe, ze = np.histogram2d(P[band, 0], P[band, 2], bins=500)
        ax[k, 1].imshow(
            np.log1p(H.T), origin="lower", extent=[xe[0], xe[-1], ze[0], ze[-1]], cmap="gray_r"
        )
        ax[k, 1].set_title("wall-height slice")

        ax[k, 2].plot(h, e[:-1])
        ax[k, 2].set_xscale("log")
        ax[k, 2].set_title("point count per height")
        for a in ax[k, :2]:
            a.set_aspect("equal")
        print(f"{capture.name}: {len(P):,} points, floor at y={floor:.2f}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(args.out, dpi=60)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
