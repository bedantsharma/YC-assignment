# Handover (Sun Oct 4, ~04:00 IST)

Cozmo AI take-home: iPhone captures → dimensioned floor plans with intervals. Deadline
**Mon Oct 5, 10:00 IST**. Read in this order: this file, [NEXT-SESSION.md](NEXT-SESSION.md),
`CLAUDE.md` (commands, layout, data conventions, **Kaggle rules**), the status section of
`ROADMAP.md`.

## State of each tier

| Tier | Status | Command |
|---|---|---|
| LiDAR | **Works** end to end, 9 captures | `uv run floorplan run <capture>` |
| Video | **Works** on the whole home (Pi3X, chained windows, scale corrected) | `uv sync --extra video`, then `uv run floorplan run <capture or .mp4> --tier video [--frames 90] [--model mapanything]` |
| Photo | **Works per room**; whole-home stitch fails (rooms laid out side by side, warned) | `uv run floorplan run <folder of room folders>` |

78 tests pass. Every output number is `{value, lo, hi, unit}`.

### LiDAR tier

- Room segmentation (`src/floorplan/plan2d.py`): counter fronts are not walls (shape
  rule); door lintels split rooms; floor bounded by an unscanned wall is attached ≤ 1 m
  deep as a flagged low-confidence zone; rooms touching > 2 m with no wall merge.
- **Drift correction** (`--drift`, chunked 2D ICP on wall points) is built and ablated on
  all 9 captures but **off by default (user decision)**: it made `c_home_01`'s kitchen
  and A `c00a170fe1` worse ([docs/drift_ablation.md](docs/drift_ablation.md)). It did make
  the damage room's two scans agree on the short side (21 cm → 1 cm). Brief G5 fails on
  "poses used as-is", so the report must state the method, the ablation and why it's off.
- **Fix loop** ([docs/fix_loop.md](docs/fix_loop.md)): shipped Fix 01 (rooms found
  2/4 → 4/4), Fix 01c (hall fragment gone, IoU 0.59 → 0.79), Fix 02 ceiling (the damage
  room's three scans agree to 1 cm). Fix 02's wall half missed its prediction twice and is
  not shipped (closed, unmerged: [PR #1](https://github.com/bedantsharma/YC-assignment/pull/1)); the cause is most likely drift. Tags
  `fix01-before/after`, `fix01c-before/after`, `fix02-before/after`.

### Video tier (`video.py`, `mvs.py`, `chunks.py`, `intervals.py`)

RGB only (isolation rule). Up side of the frame from rotation metadata, else frame
brightness → N upright frames → **Pi3X** (default; `--model mapanything` for the Apache
fallback) → more than 30 frames go through **chained windows** (30 per window, 10 shared,
trimmed similarity fit on the shared frames' point maps) → vertical from wall normals →
**scale bias divided out** (per model, horizontal / vertical, fitted on the damage room)
→ shared `build_plan` → intervals widened per axis (Pi3X 5% horizontal, 2% vertical, 1σ,
+ 5 cm). Full write-up: [docs/video_scale.md](docs/video_scale.md).

- Pi3X on the M4: 119 s / 10.9 GB per 30 frames, after one fix (its heads only disable
  autocast on CUDA; on MPS the camera SVD got bf16 and failed). Matches the Kaggle T4 run.
- `c_home_01`, 90 frames: **4 of 4 rooms, 57.3 [52.2, 62.5] m² vs 59.8 m² LiDAR**; every
  room's LiDAR area and ceiling inside the video interval. ~8 min on the M4.
- Scale is not a global error: Pi3X's camera path is metric (1.00 vs ARKit) but surfaces
  come out short, more vertically (0.91) than horizontally (0.96). Held-out check on 3
  other rooms: ceiling error 5.6–9.1% → within 3.3%; √area mean 5.4% → 3.8%; the kitchen
  stays 8.5% short; longest walls differ by outline (up to −15.5%).
- Limits: fitted and checked in one home, vs LiDAR not tape.

### Photo tier (`photos.py`, pipeline `_run_photos`; built overnight Sun)

Write-up: [docs/photo_tier.md](docs/photo_tier.md). Each folder is reconstructed on its
own (Pi3X), levelled, scale corrected (photo bias: horizontal ×1.037, vertical ×1.075),
plan built with enclosure 0.5 and **line-of-sight carving** (`plan2d.carved_mask`), the
room its photos were taken from kept and named after the folder. Intervals 10% / 3%.
- Test input: no real photos, so stills from C's videos (`scripts/make_photo_sets.py`;
  time-slot and `--protocol` selections, folders `k8` / `k8p` in `data/home_c/photos_sim/`).
- Rooms with ≥ 4 photos looking across the room: −7% to +1% area vs LiDAR; 2–3 photos:
  25–45% small (warned). Kitchen time-slot set (close-ups): no room.
- **Stitching fails**: joint reconstruction placed rooms 1–2 m wrong in every run, so rooms
  are not placed (roadmap cut line). Compliance C4 partial, G7 not met.
- Found and fixed (photo only): the observed mask made area depend on the cloud's yaw
  (7.3 vs 11.1 m²); fix map 06.
- Bake-off round 2 (Kaggle, `kaggle/photo_bakeoff`): Pi3X best again; DA3-nested now
  installs (`addict`) but runs out of memory at 8 photos on a 16 GB GPU.

## Model findings (bake-off round 1)

Full write-ups: [docs/model_spike.md](docs/model_spike.md) (first local test),
[docs/model_research.md](docs/model_research.md) (Firecrawl survey + bake-off round 1).

Bake-off round 1: same 30 frames per recording on a Kaggle T4, scored locally against the
LiDAR of the same recording (`uv run scripts/score_bakeoff.py`):

| Category | Winner | Evidence |
|---|---|---|
| Camera positions | **Pi3X** | 6–7 cm error vs MapAnything 30 cm, both damage-room scans |
| Room dimensions | **Pi3X**, narrowly | long wall 4.10 / 4.08 vs LiDAR 4.24 / 4.26 m (MapAnything 3.84 / 3.97); area −11% / +1% vs −13% / −5% |
| Ceiling | MapAnything, narrowly | +2 to +7% vs Pi3X −9% |
| Metric scale | neither | both 1–7% off ARKit, biased differently vertically and horizontally |
| Whole home (30 frames) | neither | 1 room of 4 for both |
| Runs on the M4 | both | Pi3X 119 s / 10.9 GB, MapAnything 95 s / 12.3 GB (30 frames) |
| License | MapAnything (Apache 2.0) | Pi3X and DA3-nested are CC BY-NC |
| Depth Anything 3 | not measured | failed on a missing `addict` dependency |

Other findings:
- Stray `rgb.mp4` frames are stored **sideways**; sideways input collapses every model.
- Giving the model the true focal length, or re-projecting its depth with it, did **not**
  fix the short walls (made them worse).
- Same weights and frames: 11.43 m² (T4, fp16) vs 11.87 m² (M4, MPS): 4% from numerics.
- **Adopted (user, Sun 00:00):** Pi3X for video/photo geometry, MapAnything as the Apache
  fallback behind `--model`; the non-commercial license is disclosed in the README.

## Data and ground truth

- A = Cozmo's apartment, 3 Stray captures, no ground truth.
- B = ARKitScenes room, 3 captures + laser scan. **Kept: the only absolute ground truth.**
  The architect's blind laser measurements land in `data/gt/arkitscenes_421337.yaml`.
- C = friend's home: `c_home_01` (whole home), `c_damage_01/02` (damage room twice).
  **The user asks the friend for his house measurement plan on Sun Oct 4** → transcribe
  by hand into `data/gt/home_c.yaml`. Room identity labels: `data/gt/home_c_rooms.json`.
- Kaggle: private dataset `bedantsharma/floorplan-home-c` (C's three videos + the 30
  upright frames per recording); private notebook `bedantsharma/floorplan-model-bakeoff`
  (`kaggle/bakeoff/`). Legacy token works; request **T4** (L4 silently ran on CPU).
- Disk: Pi3X (5.4 GB, approved) and MapAnything (4.9 GB) weights are in the local HF cache;
  ~15 GB free. Kaggle also has `bedantsharma/floorplan-photos-c` (private: the k8 photo
  sets) and notebook `bedantsharma/floorplan-photo-bakeoff`. No further multi-GB models on the laptop: those run on Kaggle.

## Hard rules (from the user and the brief)

- Never call something done when it is scaffolding. Report failures and wrong predictions.
- Commit small and often (graded); push only when the user asks.
- Keep ROADMAP status, COMPLIANCE rows, README and CLAUDE.md in sync with each change.
- Ground truth is measured by hand, blind, never by our own code.
- Video/photo tiers on a LiDAR recording read only the RGB video.
- Every geometry change: run `uv run scripts/lidar_summary.py` (all 9 captures) and
  compare with the last table in `docs/fix_loop.md`.
- Don't blame the capture for code bugs in write-ups.
- No model weights downloaded to the laptop without asking; Kaggle setups are dry-run
  locally (no model construction) before each push (CLAUDE.md).
- **One model job at a time on the laptop** (16 GB): two at once pushed memory pressure
  into the red. Check `ps` before starting one.

## Gotchas

- GitNexus misses Python call edges; grep to confirm callers.
- Absolute height thresholds break on low scans (A's `c00a170fe1` never sees above 1.7 m).
  Prefer shape rules.
- Fused clouds are cached as `outputs/cache/<id>.npy` (used by `scripts/diag_repeat.py`).
- Plain `uv sync` removes the `video` extra; use `uv sync --extra video`.
