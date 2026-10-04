"""Figures for the slide deck (docs/img/deck/), from outputs that reproduce.sh regenerates.

- cloud_top.png / cloud_3d.png: home C's whole-home LiDAR scan as a coloured point cloud
  (outputs/lidar_clouds/c_home_01.ply from scripts/export_clouds.py), ceiling removed
- head_to_head.png: our LiDAR vs Polycam, error per room dimension (docs/gt_comparison.md)
- hole.jpg: the staged hole as the damage detector outlined it (LiDAR keyframe)
- plan_*.png: the plans our pipeline drew (copied from outputs/), apartment_a.png: Cozmo's
  apartment, top-down point density per capture (scripts/fuse_topdown.py)

    uv run scripts/deck_figures.py
"""

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

OUT = Path("docs/img/deck")
CLOUD = Path("outputs/lidar_clouds/c_home_01.ply")
HOLE = Path("outputs/damage_lidar/c_damage_01_lidar/damage/frame_003174.jpg")
HOLE_BOX = (150, 750, 700, 1300)  # crop around the hole in that keyframe (px)


def read_ply(path: Path) -> tuple[np.ndarray, np.ndarray]:
    raw = path.read_bytes()
    end = raw.index(b"end_header\n") + len(b"end_header\n")
    n = int(re.search(rb"element vertex (\d+)", raw[:end]).group(1))
    rec = np.frombuffer(raw[end:], dtype=[("p", "<f4", 3), ("c", "u1", 3)], count=n)
    return rec["p"].astype(float), rec["c"] / 255.0


def clouds() -> None:
    p, c = read_ply(CLOUD)
    floor = np.percentile(p[:, 2], 2)
    keep = p[:, 2] < floor + 2.2  # below the ceiling, so the rooms are visible from above
    p, c = p[keep], c[keep]
    order = np.argsort(p[:, 2])  # draw low points first: walls on top of the floor
    fig, ax = plt.subplots(figsize=(8, 8), dpi=150)
    ax.scatter(p[order, 0], p[order, 1], c=c[order], s=0.15, linewidths=0)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(OUT / "cloud_top.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    pick = np.random.default_rng(0).choice(len(p), min(len(p), 400_000), replace=False)
    q, k = p[pick], c[pick]
    fig = plt.figure(figsize=(10, 7), dpi=150)
    ax = fig.add_subplot(projection="3d")
    ax.scatter(q[:, 0], q[:, 1], q[:, 2], c=k, s=0.2, linewidths=0)
    ax.view_init(elev=50, azim=-60)
    span = np.ptp(q, axis=0)
    ax.set_box_aspect(span)
    ax.axis("off")
    fig.savefig(OUT / "cloud_3d.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    for name in ("cloud_top.png", "cloud_3d.png"):
        autocrop(OUT / name)


def autocrop(path: Path, pad: int = 20) -> None:
    """Trim the white margin matplotlib leaves around 3D axes."""
    im = Image.open(path).convert("RGB")
    a = np.asarray(im)
    ys, xs = np.nonzero((a < 245).any(axis=2))
    box = (max(0, xs.min() - pad), max(0, ys.min() - pad),
           min(im.width, xs.max() + pad), min(im.height, ys.max() + pad))  # fmt: skip
    im.crop(box).save(path)


def head_to_head() -> None:
    text = Path("docs/gt_comparison.md").read_text().split("## Head-to-head")[1]
    rows = [
        line.split("|")[1:-1]
        for line in text.splitlines()
        if line.startswith("| ") and re.search(r"\| (win|loss|tie) \|", line)
    ]
    labels = [f"{r[0].strip()}\n{r[1].strip()}" for r in rows]
    ours = [float(r[5]) for r in rows]
    poly = [float(r[6]) for r in rows]
    x = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=150)
    ax.bar(x - 0.2, ours, 0.4, label=f"Ours (median {np.median(ours):.0f} cm)", color="#1f4e79")
    ax.bar(x + 0.2, poly, 0.4, label=f"Polycam (median {np.median(poly):.0f} cm)",
           color="#c9a227")  # fmt: skip
    ax.set_xticks(x, labels, fontsize=9)
    ax.set_ylabel("error vs architect's drawing (cm)")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "head_to_head.png", facecolor="white")
    plt.close(fig)


PLANS = {
    "plan_lidar.png": "outputs/c_home_01_lidar/plan.png",
    "plan_video.png": "outputs/c_home_01_video/plan.png",
    "plan_photo.png": "outputs/photo_real/k8_photo/plan.png",
    "plan_damage_room.png": "outputs/damage_lidar/c_damage_01_lidar/plan.png",
    "apartment_a.png": "outputs/topdown_overview.png",
}


# pipeline stages on Cozmo's apartment capture c7d28f72c6, cut from the exploration figures
# (outputs/topdown_overview.png from scripts/fuse_topdown.py; outputs/figures/coverage.png)
STAGES = {
    "stage_points.png": ("outputs/topdown_overview.png", (30, 746, 340, 1055)),
    "stage_heat.png": ("outputs/figures/coverage.png", (28, 28, 404, 374)),
    "stage_walls.png": ("outputs/figures/coverage.png", (28, 424, 404, 772)),
    "stage_plan.png": ("outputs/c7d28f72c6_lidar/plan.png", None),
    "run_arkit.png": ("outputs/42444946_lidar/plan.png", None),
}


def plans() -> None:
    for name, src in PLANS.items():
        Image.open(src).save(OUT / name)
    for name, (src, box) in STAGES.items():
        im = Image.open(src).convert("RGB")
        (im.crop(box) if box else im).save(OUT / name)


def hole() -> None:
    Image.open(HOLE).crop(HOLE_BOX).save(OUT / "hole.jpg", quality=90)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    head_to_head()
    plans()
    hole()
    clouds()
    print(f"-> {OUT}")
