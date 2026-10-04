# Handover (Sun Oct 4, ~17:00 IST)

Cozmo AI take-home: iPhone captures → dimensioned floor plans with intervals. Deadline
**Mon Oct 5, 10:00 IST**. Read in this order: this file, [NEXT-SESSION.md](NEXT-SESSION.md),
`CLAUDE.md` (commands, layout, data conventions, **Kaggle rules**), the status section of
`ROADMAP.md`.

Git: pushed through `2fa5f9e` (Sun ~17:00); later commits are local (push only when the
user asks). 80 tests pass. Every output number is `{value, lo, hi, unit}`.

## Headline: ground truth is in, and our walls are short

`data/gt/home_c.json` (architect's drawing for 4 rooms, friend's tape for ceilings, doors,
windows, closet, kitchen cabinets, the damage hole; ceiling 11 ft by user decision).
`uv run scripts/gt_table.py` writes [docs/gt_comparison.md](docs/gt_comparison.md): every
method vs the truth. Polycam is 6 cm off (median); our LiDAR tier 29 cm, every side short,
areas −11 to −30%, truth outside our interval in all 6 room measurements; ceilings within
1 cm. Everything that goes through our plan builder is short; SpatialLM (own wall finder)
is not. **This is the graded fix for the next session** (plan in NEXT-SESSION.md).

## State of each tier

| Tier | Status vs ground truth | Command |
|---|---|---|
| LiDAR | Works end to end (9 captures); walls 11-53 cm short, ceilings ±1 cm | `uv run floorplan run <capture>` |
| Video | Damage-room clips work (as short as LiDAR); 5-min whole-house Camera-app clip fails | `uv sync --extra video`; model runs on **Kaggle** (`kaggle/video_runs`), laptop replays the cache |
| Photo | Works per room on video stills (median 41 cm off); stitch fails; real photos not run yet | `uv run floorplan run <folder of room folders>` (model on Kaggle) |

### LiDAR tier

- Segmentation (`plan2d.py`): counter fronts are not walls; door lintels split rooms;
  unscanned-wall floor kept as a flagged low-confidence zone; rooms touching > 2 m merge.
- **Why rooms come out short** (evidence in `docs/home_c_new_captures.md`,
  `docs/lidar_model_research.md`): walls appear 2-3 times, 15-50 cm apart (drift), and we
  snap to the inner copy; kitchen upper cabinets (1 ft deep) and wardrobes count as wall.
- Drift correction (`--drift`) built and ablated, **off by default (user decision)**
  ([docs/drift_ablation.md](docs/drift_ablation.md)); brief G5 needs the report to say so.
- Fix loop ([docs/fix_loop.md](docs/fix_loop.md)): Fix 01, 01c, 02 (ceiling) shipped with
  tags; Fix 02's wall half not shipped (PR #1 closed). Practice runs; the graded fix is next.

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
- Camera-app damage-room clips (464×832, chat-compressed), 60 frames: within 5 cm of our
  LiDAR, so also ~30 cm short of the truth. 30 frames too few for a 2-min clip.
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
  `docs/fix_loop.md`) and `uv run scripts/gt_table.py`.
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
