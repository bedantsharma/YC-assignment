# floorplan

Turn handheld iPhone captures of a home into a dimensioned floor plan: walls, wall lengths,
floor area, ceiling height and openings, with a confidence interval on each measurement.

Three input tiers produce the same output, with wider intervals as the input gets thinner:

| Tier | Input |
|---|---|
| LiDAR | depth + camera poses + intrinsics (iPhone/iPad Pro, e.g. via Stray Scanner) |
| Video | a handheld walkthrough clip from any iPhone 15 or newer |
| Photos | 2–8 stills per room, one folder per room |

Status: data acquisition and scaffolding. See [ROADMAP.md](ROADMAP.md) for progress and
[requirements.md](requirements.md) for the full scope.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:bedantsharma/YC-assignment.git
cd YC-assignment
uv sync
```

## Data

Captures are large and not committed. Hand-measured ground truth lives in `data/gt/` and is
committed. How each dataset is used: [docs/data_plan.md](docs/data_plan.md).

| ID | Dataset | Location | Get it |
|---|---|---|---|
| A | Cozmo's 3 Stray Scanner captures of one apartment | `data/raw/<capture-id>/` | provided by Cozmo |
| B | ARKitScenes venue 421337: 3 captures + laser scan | `data/arkitscenes/` | `scripts/fetch_arkitscenes.sh` (~4.6 GB) |
| C | Own home capture, all tiers + tape measurements | `data/home_c/` | [capture checklist](docs/friend_capture_checklist.md) |

### Stray Scanner capture format (dataset A)

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

### ARKitScenes format (dataset B)

```
data/arkitscenes/raw/Validation/<video-id>/
  <video-id>.mov            RGB video
  lowres_depth/*.png        256x192 16-bit depth in millimetres
  confidence/*.png          0 = low, 2 = high
  lowres_wide.traj          per-frame pose: timestamp, axis-angle rotation, translation (m)
  lowres_wide_intrinsics/   per-frame .pincam: width height fx fy cx cy
data/arkitscenes/laser/<visit-id>/<id>.ply   Faro laser-scanner point cloud (ground truth)
```

## Usage

```bash
# Fuse every Stray Scanner capture and plot top-down views to outputs/topdown_overview.png
uv run scripts/fuse_topdown.py

# Download an ARKitScenes venue (default 421337 with 1 laser station)
scripts/fetch_arkitscenes.sh [visit_id] [n_laser_stations]
```

## Development

```bash
uv run ruff check --fix .   # lint
uv run ruff format .        # format
```

## Documents

- [requirements.md](requirements.md): scope, scoring, Cozmo's answers, open questions
- [ROADMAP.md](ROADMAP.md): time-boxed plan and current status
- [docs/data_plan.md](docs/data_plan.md): which dataset feeds which experiment
- [docs/friend_capture_checklist.md](docs/friend_capture_checklist.md): capture instructions
