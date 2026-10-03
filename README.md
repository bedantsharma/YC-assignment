# floorplan

Turn handheld iPhone captures of a home into a dimensioned floor plan: walls, wall lengths,
floor area, and ceiling height, with a confidence interval on each measurement.

The current focus is the **LiDAR tier**: captures exported by the
[Stray Scanner](https://apps.apple.com/app/stray-scanner/id1557051662) iOS app.
Video and photo tiers come later.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:bedantsharma/YC-assignment.git
cd YC-assignment
uv sync
```

## Data

Captures are not committed (each is hundreds of MB). Put each one in its own folder under
`data/raw/`:

```
data/raw/<capture-id>/
  rgb.mp4            1920x1440 @ 60 fps video
  depth/000000.png   256x192 16-bit PNG, depth in millimetres (looks black in image viewers)
  confidence/        256x192 8-bit PNG, 0 = low, 1 = medium, 2 = high
  odometry.csv       per-frame camera-to-world pose (x, y, z, qx, qy, qz, qw) + intrinsics
  camera_matrix.csv  3x3 intrinsics for the RGB resolution
  imu.csv            accelerometer + gyro samples
```

World frame: `y` is vertical (up). Depth back-projects with the OpenCV camera convention
(x right, y down, z forward) and the odometry pose applies directly.

## Usage

```bash
# Fuse every capture and plot top-down views to outputs/topdown_overview.png
uv run scripts/fuse_topdown.py
```

## Development

```bash
uv run ruff check .     # lint
uv run ruff format .    # format
```
