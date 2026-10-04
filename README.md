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
8 dimensions; ceilings within 1-2 cm; doors and passages detected (windows not yet); damage regions,
concealed-damage flags and repair scope on every tier. How it works and where it fails:
[docs/technical_report.md](docs/technical_report.md).

Status: LiDAR tier works end to end; drift correction is opt-in (`--drift`); the video tier
works end to end on a whole home (`uv sync --extra video`; Pi3X by default, whose weights
are **CC BY-NC (non-commercial)**, or `--model mapanything` for Apache 2.0 weights; model
comparison in [docs/model_research.md](docs/model_research.md), whole home and scale in
[docs/video_scale.md](docs/video_scale.md)); the photo tier runs end to end on room folders
(same model; on the friend's real photos rooms come out within a median 19 cm with every
photo, some rooms fail with 8 or fewer, and the whole-home stitch is weak:
[docs/photo_tier.md](docs/photo_tier.md)). Damage detection runs on all three tiers: Gemini 3.1 Pro (hosted), or Florence-2-base on
the laptop when offline (`uv sync --extra offline`, then
`uv run python -m floorplan.damage_local --fetch` once); the staged hole's size is inside the
90% interval on every tier ([docs/damage_hole.md](docs/damage_hole.md),
[docs/damage_models.md](docs/damage_models.md)). See
[ROADMAP.md](ROADMAP.md) for progress and [requirements.md](requirements.md) for the full
scope.

## Quick start (no Python knowledge needed)

Step by step for a non-engineer, with pictures of the results:
[docs/plain_guide.md](docs/plain_guide.md). In short, in the Terminal:

```bash
./setup.sh
```

```bash
./run.sh <capture folder or video file> --damage
```

`setup.sh` installs uv and everything else once (`--lite`: LiDAR tier only); `run.sh` runs
one capture and opens its plan.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:bedantsharma/YC-assignment.git
cd YC-assignment
uv sync                                   # LiDAR tier
uv sync --extra video --extra offline     # + video / photo model, offline damage model
```

### Where the video / photo model runs

The video and photo tiers need a large model (Pi3X, 5.4 GB of weights). `--recon` (or
`FLOORPLAN_RECON_BACKEND`) chooses where it runs; results are cached in
`outputs/recon_cache/` (`FLOORPLAN_RECON_CACHE`), so a rerun replays without the model.

| `--recon` | What happens |
|---|---|
| `auto` (default) | every model pass of the run goes to Kaggle's GPUs in one job (private dataset + private notebook under your Kaggle account; needs `~/.kaggle/kaggle.json` and network); if that fails, runs on this machine |
| `kaggle` | Kaggle only; an error if it fails |
| `local` | this machine only, in low-memory mode: small windows of frames, one child process each, retried smaller if one runs out of memory (`src/floorplan/mvs_local.py`) |

`FLOORPLAN_KAGGLE_TIMEOUT_MIN` caps the wait for Kaggle (default 40). `FLOORPLAN_LOCAL_WINDOW`
fixes the local window size (default from the machine's RAM: 10 frames on 16 GB).

## Data

Captures are large and not committed. Hand-measured ground truth lives in `data/gt/` and is
committed. How each dataset is used: [docs/data_plan.md](docs/data_plan.md).

**Raw-data bundle (home C + model replay caches, 2.8 GB).** Home C is a private home, so
the download link is given in the submission, not here. One command downloads it, checks
the SHA-256 sums and unpacks it in place; then `scripts/reproduce.sh` regenerates every
reported number with no GPU and no network:

```bash
scripts/fetch_data.sh <bundle URL from the submission>
```

| Zip | Contents |
|---|---|
| `floorplan_home_c_raw.zip` (1.05 GB) | home C: 3 LiDAR recordings (Stray Scanner), 4 Camera-app videos, photos per room and the sets derived from them, Polycam 7.0.4 screenshots (street address blacked out) |
| `floorplan_replay_cache.zip` (1.76 GB) | the Kaggle model outputs `reproduce.sh` replays |

Built by `uv run scripts/make_bundle.py`. The architect's drawing photo is left out
(address and stamp); its numbers are in `data/gt/home_c.json`. Dataset A is Cozmo's own;
B is public (`scripts/fetch_arkitscenes.sh`).

| ID | Dataset | Location | Get it |
|---|---|---|---|
| A | Cozmo's 3 Stray Scanner captures of one apartment | `data/raw/<capture-id>/` | provided by Cozmo |
| B | ARKitScenes venue 421337: 3 captures + laser scan; architect's measurements in `data/gt/arkitscenes_421337.json` | `data/arkitscenes/` | `scripts/fetch_arkitscenes.sh` (~4.6 GB) |
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
# Friend's real photos (iPhone ProRAW converted to JPEG; sets of all / 8 / 5 per room)
uv run scripts/make_photo_subsets.py
uv run floorplan run data/home_c/photo_sets/k8
# Replay a Kaggle run on the laptop without the model (frames decoded on the laptop are
# shipped to Kaggle, so both sides use the same pixels; see src/floorplan/video.py)
FLOORPLAN_FRAMES_CACHE=data/home_c/frames FLOORPLAN_RECON_CACHE=outputs/kaggle_house_v2/recon_cache \
  FLOORPLAN_RECON_CACHE_ONLY=1 uv run floorplan run data/home_c/video/c_home_v2.mp4 --tier video --frames 300 --up top

# Damage (hosted Gemini; credentials from the environment, see "Damage detection" below)
# Detection only on photos: outputs/damage_photos/detections.json + overlays
uv run floorplan damage data/home_c/photos/room1 --crack-pass
# Full damage stage (any tier): damage[], flags[], scope[] in plan.json, overlays
uv run floorplan run data/home_c/lidar/c_damage_01 --damage
# Offline (no network, no key): Florence-2-base on the laptop
FLOORPLAN_DAMAGE_DETECTOR=florence uv run floorplan run data/home_c/lidar/c_damage_01 --damage
# Staged hole vs the tape on every tier -> docs/damage_hole.md
uv run scripts/damage_hole_check.py --md
# Change the model (default gemini-3.1-pro-preview); each model's answers are cached apart
FLOORPLAN_GEMINI_MODEL=gemini-3.8-flash uv run floorplan damage data/home_c/photos/room1
# Replay cached Gemini answers with no network (a cache miss is an error)
FLOORPLAN_DAMAGE_CACHE_ONLY=1 uv run floorplan run data/home_c/lidar/c_damage_01 --damage

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

## Damage detection

Damage is found by Google's Gemini (a **hosted** model, called over the network), one call
per image, plus an optional second call per image that traces cracks as polylines
(`--crack-pass`). Sizes do not come from Gemini: each detection is outlined in the image and
projected onto the measured wall plane with the frame's pose (`src/floorplan/damage_geom.py`).

Credentials are read from the environment by `google-genai`; the code never stores them.

```bash
# Vertex AI with an API key
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT=<project-id>
export GOOGLE_CLOUD_LOCATION=global
export GOOGLE_API_KEY=<key>
# or the Gemini Developer API (AI Studio key): only GOOGLE_API_KEY
```

| Variable | Effect |
|---|---|
| `FLOORPLAN_GEMINI_MODEL` | model name (default `gemini-3.1-pro-preview`; also tested `gemini-3.8-flash`, `gemini-3.6-flash`) |
| `FLOORPLAN_DAMAGE_CACHE` | where answers are cached (default `data/damage_cache/`, committed) |
| `FLOORPLAN_DAMAGE_CACHE_ONLY=1` | never call the network; a missing answer is an error |
| `FLOORPLAN_DAMAGE_DETECTOR` | `auto` (default: Gemini, Florence-2 on the laptop if Gemini fails after retries), `gemini`, `florence` |

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
| `damage[]` | `id`, `surface_id`, `damage_class`, `score` (detector confidence 0–1), `region` (u0, v0, u1, v1 metres on the surface; wall: u along the wall from its start corner, which is the right-hand corner seen from inside, v above the floor), `area`, `centre` (u, v), `length` (cracks), `width_band` (cracks), `views` (images it was seen in), `note` |
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
- [docs/damage_research.md](docs/damage_research.md): damage detection research and plan (models, datasets, sizing on the wall, rules, scope items)
- [docs/damage_models.md](docs/damage_models.md): Gemini 3.1 Pro vs 3.8 / 3.6 Flash vs Florence-2 on the staged room's photos
- [docs/damage_hole.md](docs/damage_hole.md): the staged hole's measured size vs the tape, every tier and detector

## License

Proprietary, all rights reserved: see [LICENSE](LICENSE). Cozmo AI / Brynz Tech may clone,
run and reproduce it to evaluate the assessment; no other use or copying without written
permission. Third-party dependencies and model weights keep their own licences.
