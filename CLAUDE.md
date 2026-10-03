# floorplan

Phone captures of a home → dimensioned floor plan (walls, wall lengths, floor area, ceiling
height) with a confidence interval on every measurement. Built for the Cozmo AI "Applied AI"
take-home (brief: `Applied AI.pdf`, gitignored). All three input tiers (LiDAR, video, photos)
are required. Scope: `requirements.md`; plan and status: `ROADMAP.md` (tick items off as they
land); datasets: `docs/data_plan.md`. Deadline: Mon Oct 5, 10:00 IST.

## Commands

- `uv sync`: install dependencies (Python 3.12, managed by uv; never use pip directly)
- `uv add <pkg>` / `uv add --dev <pkg>`: add dependencies
- `uv run ruff check --fix . && uv run ruff format . && uv run pytest`: run before every commit
- `uv run floorplan run <capture> [--tier lidar|video|photo]`: process one capture into
  `outputs/<id>_<tier>/plan.json` and `plan.png`
- `uv run scripts/fuse_topdown.py`: fuse all captures, write `outputs/topdown_overview.png`
- `scripts/fetch_arkitscenes.sh [visit_id] [n_laser]`: download an ARKitScenes venue
- `uv run scripts/md_to_pdf.py <doc.md> [--skip "Section"]`: render a doc to PDF (PDFs are gitignored)
- `uv run scripts/prepare_laser_gt.py`: crop + thin B's laser scan for hand measurement in CAD

## Layout

- `src/floorplan/`: the pipeline package
  - `cli.py`: `floorplan run <capture> [--tier] [--out]` (one command per capture)
  - `pipeline.py`: `run()` chains the stages; add new stages here
  - `capture.py`: format detection + loaders; converts every LiDAR source to the common frame
  - `cloud.py`: depth frames → fused, voxel-downsampled world point cloud
  - `levels.py`: floor / ceiling heights from height histograms
  - `plan2d.py`: wall orientation, wall / observed grids, enclosure test, room segmentation
  - `rooms.py`: room outline → rectilinear polygon snapped to measured wall faces
  - `lidar.py`: point cloud → output `Room`s with intervals (shared geometry backend)
  - `drift.py`: opt-in pose drift correction (`--drift`, off by default)
  - `video.py`: upright frames from a video (orientation), vertical from wall normals
  - `mvs.py`: frames → metric cloud + camera poses (Pi3X default, MapAnything fallback)
  - `chunks.py`: > 30 frames in overlapping windows, chained by similarity fits
  - `intervals.py`: video scale-bias correction and per-axis interval widening
  - `render.py`: `Result` → dimensioned `plan.png`
  - `output.py`: result type and JSON writer (every number is a `Measurement` with an interval)
- `tests/`: pytest tests
- `COMPLIANCE.md`: requirement → file → artifact → status; update a row whenever work lands
- `scripts/`: exploration and one-off analysis scripts
- `data/raw/<capture-id>/`: Cozmo's Stray Scanner captures, dataset A (gitignored)
- `data/arkitscenes/`: ARKitScenes venue 421337 + laser scan, dataset B (gitignored)
- `data/home_c/`: friend's iPhone 16 Pro capture of a home, dataset C (gitignored):
  `lidar/c_home_NN/` (Stray Scanner), `video/`, `photos/<room>/`, `polycam/`, `notes/`
- `data/gt/`: hand-measured ground truth files (committed)
- `docs/`: data plan, capture checklist; later the capture protocol and reports
- `outputs/`: generated plots and results (gitignored)

## Data conventions (verified against the captures)

**Common frame** (what `capture.load_lidar` returns for every source): metres, **z up**,
poses camera-to-world on OpenCV camera coordinates, intrinsics at depth resolution. Geometry
code only ever sees this frame. Raw-format notes below are for the loaders only.


- `depth/*.png` is 16-bit depth in **millimetres** at 256x192; `confidence/*.png` is 0/1/2.
  Use only confidence 2 for geometry.
- `odometry.csv` holds camera-to-world poses; quaternion order is `qx, qy, qz, qw`
  (matches `scipy.spatial.transform.Rotation.from_quat`).
- Back-project depth with the **OpenCV camera convention** (x right, y down, z forward) and
  apply the pose directly. The ARKit convention (x, -y, -z) produces a smeared cloud.
- World `y` is vertical (up). Floor sits around y ≈ -1.4 to -1.5 m in each capture.
- Scale `camera_matrix.csv` intrinsics from 1920x1440 down to the 256x192 depth resolution.
- The three captures walk the **same multi-room apartment**. `c7d28f72c6` is the most
  complete and the only one with the ceiling visible (~3.07 m, tentative).
- Dataset A has no ground truth, so state accuracy claims on it as "consistent with LiDAR".
- ARKitScenes (B) differs from Stray Scanner: `.traj` poses are axis-angle + translation and
  **world-to-camera** (invert them; verified by fusion sharpness), sampled at ~12 Hz vs 60 Hz
  depth (matched by timestamp, 10 ms tolerance); world is already z-up; intrinsics are
  per-frame `.pincam` files; video is a separate `.mov`.
- Never measure ground truth with our own detection code: hand-measure into `data/gt/`.
- Video/photo tiers on a LiDAR recording read **only the RGB video**: never its depth, poses,
  intrinsics or IMU (see `docs/data_plan.md`). Video-tier benchmark numbers use Camera-app video.
- Keep one room of the friend's capture (C) untouched until the walk-in rehearsal.

## Working rules

- Commit small and often with descriptive messages: commit history is graded, and a repo
  that appears in one or two commits scores zero on process.
- Every reported number must be regenerable by a single command from `data/raw/`.
- Prefer numpy/scipy; justify any heavy dependency (e.g. open3d) before adding it.

## Remote GPU runs (Kaggle)

Big models (multi-GB weights) run on Kaggle, not on the user's laptop: `kaggle/<job>/`
holds the script + `kernel-metadata.json`; `uvx kaggle kernels push -p kaggle/<job>
--accelerator NvidiaTeslaT4`, then `kernels status` / `kernels output`. Data goes up only as
a **private** dataset, and only with the user's OK (C's videos are approved). The legacy
token in `~/.kaggle/kaggle.json` works.

**Laptop (16 GB M4): one model job at a time.** Two model runs at once pushed memory
pressure into the red. Check `ps` for another `floorplan run` / model script first; use
the wait for code or docs, never a second run.

Each failed push costs ~5–10 min. The bake-off took 6 pushes because of setup mistakes
that a local dry run would have caught. **Before every push:**

1. **Dry-run the setup locally** in a throwaway scratch venv (`uv venv`, same installs,
   then the script's imports and config composition), then delete the venv. **Never
   build a model locally** (`from_pretrained`, `init_model_from_config`): that downloads
   multi-GB weights onto the user's laptop, which the user does not want. Stop right
   before model construction; only that step and the GPU work stay untested.
2. **Never install a package inside the running script and then import it**, especially
   `pip install -e`: the process scanned `site-packages` at startup and won't see it.
   Install, then `sys.path.insert(0, <clone>)`, or install in a first cell/process and
   run the work in a second `subprocess` (cleanest).
3. **GPU:** request `NvidiaTeslaT4`. `NvidiaL4` silently ran on **CPU** for this account
   (no `nvidia-smi`, CPU-only torch). Check for the GPU first and exit with a clear message.
4. **Precision on T4 (pre-Ampere):** use **fp16**, not bf16. With bf16, PyTorch's attention
   falls back to the full matrix (86 GB for 30 views). Pick by
   `torch.cuda.get_device_capability()[0] >= 8`.
5. **Kaggle's Python is new (3.13.15):** packages capped at `<=3.13` refuse to install;
   install them separately with `--ignore-requires-python`, never in the same
   `pip install` as the essentials.
6. **Packages that load configs from the repo** (MapAnything's `init_model_from_config`
   reads `configs/`): install from a git clone, not from PyPI/git+URL.
7. Wrap each model run in try/except and log the traceback, so one failure doesn't hide
   the others, and read the **whole** log before the next push.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **YC-assignment** (811 symbols, 1111 relationships, 13 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/YC-assignment/context` | Codebase overview, check index freshness |
| `gitnexus://repo/YC-assignment/clusters` | All functional areas |
| `gitnexus://repo/YC-assignment/processes` | All execution flows |
| `gitnexus://repo/YC-assignment/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
