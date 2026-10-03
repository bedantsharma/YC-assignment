# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "matplotlib", "laspy", "pye57"]
# ///
"""Make the ARKitScenes laser scan small enough to measure by hand in CAD tools.

Crops the station's cloud to the scanned room (drops points seen through windows), thins it
to one point per 5 mm cell (keeps real points, no averaging), and writes PLY, LAS and E57
plus a top-down overview image. Coordinates stay in the original metres, unshifted.

Usage: uv run scripts/prepare_laser_gt.py [--ply data/arkitscenes/laser/421337/170078.ply]
"""

import argparse
from pathlib import Path

import laspy
import matplotlib
import numpy as np
import pye57

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PLY_DTYPE = np.dtype(
    [("x", "<f8"), ("y", "<f8"), ("z", "<f8"), ("r", "u1"), ("g", "u1"), ("b", "u1"),
     ("a", "u1"), ("quality", "<f8"), ("radius", "<f8")]
)  # fmt: skip
MARGIN_M = 0.5  # crop box = robust room extent plus this on every side


def load(ply: Path) -> np.ndarray:
    head = ply.read_bytes()[:4096]
    offset = head.index(b"end_header\n") + len(b"end_header\n")
    return np.memmap(ply, dtype=PLY_DTYPE, mode="r", offset=offset)


def crop_box(v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    sample = np.column_stack([v["x"][::50], v["y"][::50], v["z"][::50]])
    lo, hi = np.percentile(sample, 1, axis=0), np.percentile(sample, 99, axis=0)
    return lo - MARGIN_M, hi + MARGIN_M


def thin(xyz: np.ndarray, cell: float) -> np.ndarray:
    """Indices of the first point in each cell."""
    c = np.floor((xyz - xyz.min(axis=0)) / cell).astype(np.int64)
    span = c.max(axis=0) + 1
    keys = (c[:, 0] * span[1] + c[:, 1]) * span[2] + c[:, 2]
    return np.unique(keys, return_index=True)[1]


def write_ply(path: Path, xyz: np.ndarray, rgb: np.ndarray) -> None:
    rec = np.empty(len(xyz), [("x", "<f8"), ("y", "<f8"), ("z", "<f8"),
                              ("red", "u1"), ("green", "u1"), ("blue", "u1")])  # fmt: skip
    rec["x"], rec["y"], rec["z"] = xyz.T
    rec["red"], rec["green"], rec["blue"] = rgb.T
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"comment ARKitScenes 421337 laser station, cropped and thinned; metres\n"
        f"element vertex {len(xyz)}\nproperty double x\nproperty double y\nproperty double z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n"
    )
    with open(path, "wb") as f:
        f.write(header.encode())
        f.write(rec.tobytes())


def write_las(path: Path, xyz: np.ndarray, rgb: np.ndarray) -> None:
    header = laspy.LasHeader(point_format=2, version="1.2")
    header.scales = np.array([0.0001] * 3)  # 0.1 mm
    header.offsets = np.floor(xyz.min(axis=0))
    las = laspy.LasData(header)
    las.x, las.y, las.z = xyz.T
    las.red, las.green, las.blue = (rgb.astype(np.uint16) * 257).T
    las.write(path)


def write_e57(path: Path, xyz: np.ndarray, rgb: np.ndarray) -> None:
    path.unlink(missing_ok=True)
    with pye57.E57(str(path), mode="w") as e57:
        e57.write_scan_raw(
            {
                "cartesianX": xyz[:, 0], "cartesianY": xyz[:, 1], "cartesianZ": xyz[:, 2],
                "colorRed": rgb[:, 0], "colorGreen": rgb[:, 1], "colorBlue": rgb[:, 2],
            },
            name="arkitscenes_421337_170078",
        )  # fmt: skip


def slice_sketch(path: Path, xyz: np.ndarray, floor_z: float) -> None:
    """Large wall slice with a 0.5 m grid, for numbering walls and openings on paper."""
    band = (xyz[:, 2] > floor_z + 1.0) & (xyz[:, 2] < floor_z + 1.2)
    fig, ax = plt.subplots(figsize=(9, 8))
    ax.scatter(xyz[band, 0], xyz[band, 1], s=0.08, c="k")
    ax.set_title("Laser scan, horizontal slice 1.0-1.2 m above floor (top-down, metres)")
    ax.set_xticks(np.arange(np.floor(xyz[:, 0].min()), xyz[:, 0].max(), 0.5))
    ax.set_yticks(np.arange(np.floor(xyz[:, 1].min()), xyz[:, 1].max(), 0.5))
    ax.set_aspect("equal")
    ax.grid(alpha=0.35)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def overview(path: Path, xyz: np.ndarray, floor_z: float) -> None:
    band = (xyz[:, 2] > floor_z + 1.0) & (xyz[:, 2] < floor_z + 1.2)
    fig, ax = plt.subplots(1, 2, figsize=(16, 8))
    ax[0].scatter(xyz[::20, 0], xyz[::20, 1], s=0.05, c=xyz[::20, 2], cmap="viridis")
    ax[0].set_title("all points, top-down (colour = height)")
    ax[1].scatter(xyz[band, 0], xyz[band, 1], s=0.05, c="k")
    ax[1].set_title("slice 1.0-1.2 m above floor: walls and openings")
    for a in ax:
        a.set_aspect("equal")
        a.grid(alpha=0.3)
        a.set_xlabel("x (m)")
        a.set_ylabel("y (m)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ply", type=Path, default=Path("data/arkitscenes/laser/421337/170078.ply"))
    ap.add_argument("--out", type=Path, default=Path("outputs/laser_gt"))
    ap.add_argument("--cell", type=float, default=0.005, help="thinning cell size, metres")
    ap.add_argument("--sketch", type=Path, default=Path("docs/img/arkitscenes_421337_slice.png"))
    args = ap.parse_args()

    v = load(args.ply)
    lo, hi = crop_box(v)
    xyz_all = np.column_stack([v["x"], v["y"], v["z"]])
    keep = np.all((xyz_all >= lo) & (xyz_all <= hi), axis=1)
    xyz = xyz_all[keep]
    rgb = np.column_stack([v["r"][keep], v["g"][keep], v["b"][keep]])
    idx = thin(xyz, args.cell)
    xyz, rgb = xyz[idx], rgb[idx]
    print(f"{len(v):,} points -> {keep.sum():,} in crop -> {len(xyz):,} after thinning")
    print("crop box: " + ", ".join(f"{a} {lo[k]:.2f}..{hi[k]:.2f}" for k, a in enumerate("xyz")))

    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / "arkitscenes_421337_room"
    write_ply(stem.with_suffix(".ply"), xyz, rgb)
    write_las(stem.with_suffix(".las"), xyz, rgb)
    write_e57(stem.with_suffix(".e57"), xyz, rgb)
    floor_z = float(np.percentile(xyz[:, 2], 2))
    overview(args.out / "overview.png", xyz, floor_z)
    args.sketch.parent.mkdir(parents=True, exist_ok=True)
    slice_sketch(args.sketch, xyz, floor_z)
    print(f"  {args.sketch}")
    for f in sorted(args.out.iterdir()):
        print(f"  {f}  {f.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
