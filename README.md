# floorplan

Turn handheld iPhone captures of a home into a dimensioned floor plan: walls, wall lengths,
floor area, ceiling height and openings, with a confidence interval on each measurement.

Three input tiers produce the same output, with wider intervals as the input gets thinner:

| Tier | Input |
|---|---|
| LiDAR | depth + camera poses + intrinsics (iPhone/iPad Pro, e.g. via Stray Scanner) |
| Video | a handheld walkthrough clip from any iPhone 15 or newer |
| Photos | 2–8 stills per room, one folder per room |

Results on a real home with ground truth ([docs/benchmark_report.md](docs/benchmark_report.md)):
LiDAR room sides within 5 cm (median) of the architect's drawing, beat or tie Polycam on 6 of
8 dimensions; ceilings within 1-2 cm; doors and passages detected (windows not yet); damage,
flags and repair scope not built. How it works and where it fails:
[docs/technical_report.md](docs/technical_report.md).

Status: LiDAR tier works end to end; drift correction is opt-in (`--drift`); the video tier
works end to end on a whole home (`uv sync --extra video`; Pi3X by default, whose weights
are **CC BY-NC (non-commercial)**, or `--model mapanything` for Apache 2.0 weights; model
comparison in [docs/model_research.md](docs/model_research.md), whole home and scale in
[docs/video_scale.md](docs/video_scale.md)); the photo tier runs end to end on room folders
(same model; single rooms with 5+ photos work, the whole-home stitch is weak:
[docs/photo_tier.md](docs/photo_tier.md)). See
[ROADMAP.md](ROADMAP.md) for progress and [requirements.md](requirements.md) for the full
scope.

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
| C | Own home capture, all tiers + tape measurements | `data/home_c/` (`lidar/`, `video/`, `photos/<room>/`, `polycam/`, `notes/`) | [capture checklist](docs/friend_capture_checklist.md) |

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
# Process one capture (tier inferred from the folder; --tier to override;
# --drift re-aligns poses on the walls, see docs/drift_ablation.md)
uv run floorplan run data/raw/c7d28f72c6
uv run floorplan run data/raw/c7d28f72c6 --tier video
# Video of a whole home: more frames, reconstructed in chained windows of 30
uv run floorplan run data/home_c/lidar/c_home_01 --tier video --frames 90
# Photos: one folder per room (2-8 photos each), folder name = room label
uv run floorplan run data/home_c/photos_sim/c_damage_01/k8p

# Fuse every Stray Scanner capture and plot top-down views to outputs/topdown_overview.png
uv run scripts/fuse_topdown.py

# Download an ARKitScenes venue (default 421337 with 1 laser station)
scripts/fetch_arkitscenes.sh [visit_id] [n_laser_stations]

# Crop and thin its laser scan for hand measurement in CAD (E57 / LAS / PLY)
uv run scripts/prepare_laser_gt.py

# Home C vs ground truth (data/gt/home_c.json): every method we tested (Polycam, our
# LiDAR / video / photo tiers, raw third-party models, SpatialLM) in one table, room by
# room, with signed errors, and the head-to-head vs Polycam; rewrites
# docs/gt_comparison.md. Rerun after any change.
uv run scripts/gt_table.py
# Quick check of specific plans against the ground truth and Polycam
uv run scripts/compare_gt_c.py [plan.json ...]
# 90% interval coverage per tier; the full benchmark report; regenerate everything
uv run scripts/calibration.py
uv run scripts/benchmark.py
scripts/reproduce.sh
```

## Output format

Each capture produces `plan.json`, written by `floorplan.output.write_json`, which refuses to
write a result with broken cross-references. Lengths are metres, areas m², plan coordinates
are metres in a top-down frame.

> **Note on the schema.** The brief mentions "JSON to the published schema", but no schema was
> published and Cozmo asked us to ignore that reference. There is therefore **no JSON Schema
> file** in this repo. The format is defined in code by the dataclasses in
> [`src/floorplan/output.py`](src/floorplan/output.py), tested in
> [`tests/test_output.py`](tests/test_output.py), and documented by the table below.

**Every measured number** is `{"value", "lo", "hi", "unit"}`: the estimate and its
confidence interval (coverage given by `interval_coverage`, default 0.9).

| Field | Contents |
|---|---|
| `format_version` | Output format version (currently `0.1`) |
| `capture` | `id`, `tier` (`lidar` / `video` / `photo`), `source` path, `device` |
| `rooms[]` | `id`, `label`, `polygon` (corner points, counter-clockwise), `floor_area`, `ceiling_height` (`null` if the ceiling was never captured), `walls[]`, `openings[]`, `low_confidence_area` (part of the floor area bounded by a wall that was never scanned, `null` if none; `floor_area.lo` is already widened by it) |
| `rooms[].walls[]` | `id`, `start`, `end` (points), `length`, `height`, `observed` (`false`: no wall surface seen, e.g. an open side; its interval is wide) |
| `rooms[].openings[]` | `id`, `wall_id`, `kind` (`door` / `window` / `passage`), `width`, `height`, `connects_to` (room id) |
| `adjacency[]` | `room_a`, `room_b`, `opening_id`: which rooms connect, and through which opening |
| `surfaces[]` | `id`, `room_id`, `kind` (`wall` / `floor` / `ceiling`), `wall_id`, `area` |
| `damage[]` | `id`, `surface_id`, `damage_class`, `score` (detector confidence 0–1), `region` (u0, v0, u1, v1 metres on the surface), `area` |
| `flags[]` | Concealed-damage flags: `id`, `rule_id`, `rule` (text of the rule that fired), `surface_id`, `damage_ids` |
| `scope[]` | Repair line items: `id`, `surface_id`, `action`, `quantity`, `reason_ids` (damage / flag ids) |
| `footprint_area` | Whole-property floor area |
| `plan_rotation_deg` | Plan frame = capture's world frame rotated about the vertical by minus this angle, so walls run along x and y |
| `drift_correction` | Drift-correction method used (multi-room captures), or `null` |
| `interval_coverage` | Target coverage of every interval (0.9 = 90%) |
| `timing_s` | Seconds per pipeline stage |
| `warnings` | Anything the pipeline wants a human to know (e.g. "ceiling not observed") |

## Development

```bash
uv run ruff check --fix .   # lint
uv run ruff format .        # format
uv run pytest               # tests
```

## Documents

- [docs/technical_report.md](docs/technical_report.md): technical report (architecture,
  accuracy, drift, error budget, calibration, fix loop, failure modes, disclosure)
- [docs/benchmark_report.md](docs/benchmark_report.md): every gate at every tier (generated by
  `scripts/benchmark.py`; `scripts/reproduce.sh` regenerates everything)
- [docs/openings.md](docs/openings.md): door and passage detection
- [COMPLIANCE.md](COMPLIANCE.md): compliance matrix. Every requirement in the brief (64 rows)
  mapped to the file that implements it, the artifact that proves it, and its status (done,
  in progress, partial, not started, not done). Start here to check what is covered
- [requirements.md](requirements.md): scope, scoring, Cozmo's answers, open questions
- [ROADMAP.md](ROADMAP.md): time-boxed plan and current status
- [docs/data_plan.md](docs/data_plan.md): which dataset feeds which experiment
- [docs/device_matrix.md](docs/device_matrix.md): which tier runs on which iPhone, and its
  measured accuracy
- [docs/friend_capture_checklist.md](docs/friend_capture_checklist.md): capture instructions
- [docs/home_c_new_captures.md](docs/home_c_new_captures.md): Camera-app videos and Polycam on home C
- [docs/lidar_model_research.md](docs/lidar_model_research.md): pretrained LiDAR models (survey + SpatialLM bake-off)
- [docs/gt_comparison.md](docs/gt_comparison.md): every method vs home C's ground truth (generated by `scripts/gt_table.py`)
- [docs/fix_declaration.md](docs/fix_declaration.md): the fix-loop declaration (walls short vs ground truth; 29 → 5 cm)
