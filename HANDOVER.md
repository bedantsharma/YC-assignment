# Handover (Sun Oct 4, after the graded fix)

Cozmo AI take-home: iPhone captures → dimensioned floor plans with intervals. Deadline
**Mon Oct 5, 10:00 IST**. Read in this order: this file, [NEXT-SESSION.md](NEXT-SESSION.md),
`CLAUDE.md` (commands, layout, data conventions, **Kaggle rules**), the status section of
`ROADMAP.md`.

Git: pushed through `2fa5f9e`; later commits are local (push only when the user asks).
82 tests pass. Every output number is `{value, lo, hi, unit}`.

## Headline: the graded fix is shipped; we beat or tie Polycam on 75%

`data/gt/home_c.json` (architect's drawing for 4 rooms, friend's tape for ceilings, doors,
windows, closet, kitchen cabinets, the damage hole; ceiling 11 ft by user decision).
`uv run scripts/gt_table.py` writes [docs/gt_comparison.md](docs/gt_comparison.md): every
method vs the truth, plus the head-to-head.

**Fix 09** ([docs/fix_declaration.md](docs/fix_declaration.md), tags `fixloop-before` /
`fixloop-after`): drift smears each wall into a band 10-40 cm thick and the old snap took
its inner edge; furniture counted as wall. Walls are now placed at the median of the points
**2.3 m to ceiling − 0.3 m** behind each edge, own side of interior walls
(`rooms._centre_of_wall`); the nearest-face snap is kept where no ceiling was seen. LiDAR vs
truth: median **29 → 5 cm** (Polycam 6); area interval holds the truth in 3 of 6 rooms
(was 0). Head-to-head: beat or tie **6 of 8 (75%)**. The video scale bias had been fitted to
the short LiDAR; re-measured (Pi3X 0.964 → 0.890), Camera-app damage clips at 60 frames are
+5 cm. Predictions met within 3 cm on LiDAR; the first video prediction was wrong (recorded).

## State of each tier

| Tier | Status vs ground truth | Command |
|---|---|---|
| LiDAR | Works end to end (9 captures); walls median 5 cm vs truth (worst −23 cm, an unscanned wall), ceilings ±1 cm | `uv run floorplan run <capture>` |
| Video | Damage-room clips work (60 frames: +5 cm, in-sample for the scale bias); 5-min whole-house Camera-app clip fails | `uv sync --extra video`; model runs on **Kaggle** (`kaggle/video_runs`), laptop replays the cache |
| Photo | Works per room on video stills (median 41 cm off); stitch fails; real photos not run yet | `uv run floorplan run <folder of room folders>` (model on Kaggle) |

### LiDAR tier

- Segmentation (`plan2d.py`): counter fronts are not walls; door lintels split rooms;
  unscanned-wall floor kept as a flagged low-confidence zone; rooms touching > 2 m merge.
- Walls (fix 09): median of the points above 2.3 m behind each edge; per-wall diagnostic
  `uv run scripts/diag_walls.py [--upper] [capture ...]`. Side effect: B's room grows
  1.2-2.2 m² (furniture no longer wall) and its 3 scans agree less (02b; unverified).
- Drift correction (`--drift`) built and ablated, **off by default (user decision)**
  ([docs/drift_ablation.md](docs/drift_ablation.md)); brief G5 needs the report to say so.
- Fix loop ([docs/fix_loop.md](docs/fix_loop.md)): Fix 01, 01c, 02 (ceiling), **09 (the
  graded one)** shipped with tags.

### Video tier (`video.py`, `mvs.py`, `chunks.py`, `intervals.py`)

RGB only → upright frames → Pi3X (default; `--model mapanything` = Apache fallback) →
> 30 frames in chained windows (30, 10 shared) → vertical from wall normals → per-model
scale bias divided out → shared `build_plan` → intervals widened (5% / 2% + 5 cm).
Write-ups: [docs/video_scale.md](docs/video_scale.md), [docs/home_c_new_captures.md](docs/home_c_new_captures.md).

- **Reconstruction cache** (`mvs.py`): `FLOORPLAN_RECON_CACHE=<dir>` stores each model
  pass keyed by model + frame pixels; `FLOORPLAN_RECON_CACHE_ONLY=1` makes a miss an
  error. Kaggle fills it, the laptop replays (frames decode identically on both).
- **Chain fix** (`chunks.fit_shared`): when a link's fit over all shared frames is broken
  (> 10 cm), fit only the shared frames that agree. Broken link 0.54/153 cm → 0.95/0.8 cm;
  healthy links untouched.
- Scale bias (`intervals.SCALE_BIAS`) re-measured against the fixed LiDAR (Pi3X 0.890 /
  0.914, MapAnything 0.877 / 1.035). Horizontal varies by room (0.80-0.99): ±10% per room.
- Camera-app damage-room clips (464×832, chat-compressed), 60 frames: +6/+6 and +5/+4 cm
  vs the truth. 30 frames too few for a 2-min clip (+20/+16 cm).
- Every plan has a replay cache now (`outputs/kaggle_video_runs/recon_cache`,
  `outputs/kaggle_cache_runs/recon_cache`; job `kaggle/cache_runs`, dataset
  `floorplan-video-c2` holds the fixed code and the stills). `scripts/reproduce.sh`
  regenerates every number; `scripts/benchmark.py` writes `docs/benchmark_report.md`.
- Photo intervals widened to the tier's measured error on C (`RESIDUAL_REL` photo 14% /
  5.5%); coverage of sides: LiDAR 91%, video 92%, photo 80% (`scripts/calibration.py`).
- Openings: `openings.py` (doors, passages; windows not detected; door 34 cm narrow).
- Whole-house clip (5 min, ceiling sweeps): windows fold rooms onto each other; no usable
  plan. The LiDAR recording's own 22 s video gives 4 of 4 rooms.

### Photo tier (`photos.py`, pipeline `_run_photos`)

Each folder reconstructed alone (Pi3X), levelled, scale corrected, line-of-sight carving,
enclosure 0.5, folder name = room label ([docs/photo_tier.md](docs/photo_tier.md)). Tested
only on stills cut from the videos (`data/home_c/photos_sim/`). Stitching rooms fails
(joint reconstruction 1-2 m off): rooms laid out side by side, warned.

## Models (all runs on Kaggle)

- Video/photo geometry: **Pi3X** (CC BY-NC, user's choice) over MapAnything (Apache) and
  Depth Anything 3 (out of memory at 8 photos) ([docs/model_research.md](docs/model_research.md),
  [docs/photo_tier.md](docs/photo_tier.md)). Raw, through our builder, all are short.
- LiDAR models ([docs/lidar_model_research.md](docs/lidar_model_research.md)): survey of
  SpatialLM, RoomFormer, Sonata, SceneScript, RoomPlan. SpatialLM 1.1 tested (Qwen-0.5B,
  Llama-1B, 3 seeds, on both T4s): within 0-15 cm when sane, but 5 of 12 runs broken, heights
  +5 to +35 cm, whole home needs a 13 GB allocation (more than one T4). Not adopted;
  a candidate for doors/windows.
- Kaggle assets (all private): datasets `floorplan-home-c`, `floorplan-photos-c`,
  `floorplan-video-c2` (Camera-app clips + a copy of `src/floorplan`), `floorplan-lidar-c`
  (coloured LiDAR clouds); kernels `floorplan-model-bakeoff`, `floorplan-photo-bakeoff`,
  `floorplan-video-runs`, `floorplan-lidar-bakeoff` (`kaggle/<job>/`). Kaggle's T4 option
  gives **two T4s**; a model only uses the second if the code puts it there.

## Data and ground truth

- A = Cozmo's apartment, 3 Stray captures, no ground truth.
- B = ARKitScenes room + laser scan; architect's blind measurements still pending
  (`data/gt/arkitscenes_421337.yaml`).
- C = friend's home: LiDAR `c_home_01`, `c_damage_01/02`; Camera-app videos
  `data/home_c/video/`; Polycam screenshots `data/home_c/polycam/` (numbers in
  `data/gt/home_c_polycam.json`); drawing photo `data/home_c/notes/` (address and stamp
  visible: never commit); **ground truth `data/gt/home_c.json`**; room labels
  `data/gt/home_c_rooms.json`. Room names: kitchen = kitchen; dining_living = our `hall`
  = Polycam Dining + Bedroom 3; drawing = `room2` = Polycam Bedroom 1; bedroom (staged
  damage room) = `room1` = Polycam Bedroom 2.
- Still wanted from the friend, in one message: originals of videos/photos via
  Drive/iCloud (chat compression), Polycam app version + any export; optionally a 1-2 min
  eye-level house video. Photos arrived; the user is sorting them by room.

## Hard rules (from the user and the brief)

- Never call something done when it is scaffolding. Report failures and wrong predictions.
- Commit small and often (graded); push only when the user asks.
- Keep ROADMAP status, COMPLIANCE rows, README and CLAUDE.md in sync with each change.
- Ground truth is transcribed by hand, never produced by our own code.
- Video/photo tiers on a LiDAR recording read only the RGB video.
- Every geometry change: `uv run scripts/lidar_summary.py` (all 9 captures, compare with
  `docs/fix_declaration.md` §5) and `uv run scripts/gt_table.py`.
- **No model runs on the laptop, ever** (user, Oct 4): Kaggle, dry-run the setup locally
  first (CLAUDE.md), replay the cache locally.
- Data goes to Kaggle only as private datasets.

## Gotchas

- ffmpeg in the sandbox cannot open the friend's original files in `data/home_c/video/`
  (macOS file protection, `Operation not permitted`); a copy in the session scratchpad
  works.
- GitNexus index is stale and misses Python call edges; grep to confirm callers.
- Absolute height thresholds break on low scans (A's `c00a170fe1`); prefer shape rules.
- Fused clouds are cached as `outputs/cache/<id>.npy` (damage rooms; not `c_home_01`).
- Plain `uv sync` removes the `video` extra; use `uv sync --extra video` (replay needs it).
