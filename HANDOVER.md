# Handover (Sat Oct 3, 23:40 IST)

Cozmo AI take-home: iPhone captures → dimensioned floor plans with intervals. Deadline
**Mon Oct 5, 10:00 IST**. Read in this order: this file, [NEXT-SESSION.md](NEXT-SESSION.md),
`CLAUDE.md` (commands, layout, data conventions, **Kaggle rules**), the status section of
`ROADMAP.md`.

## State of each tier

| Tier | Status | Command |
|---|---|---|
| LiDAR | **Works** end to end, 9 captures | `uv run floorplan run <capture>` |
| Video | **Works** end to end on one room; whole home fails (1 of 4 rooms) | `uv sync --extra video`, then `uv run floorplan run <capture or .mp4> --tier video` |
| Photo | **Stub** (warning only) | – |

64 tests pass. Every output number is `{value, lo, hi, unit}`.

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

### Video tier (`src/floorplan/video.py`, `mvs.py`, `intervals.py`)

RGB only (isolation rule). Up side of the frame from rotation metadata, else frame
brightness (6/6 right on the Stray captures vs ARKit) → 30 upright frames → MapAnything →
vertical from wall normals → shared `build_plan` → intervals widened by 3% scale + 5 cm
(provisional). `c_damage_01`: 11.87 vs 13.13 m² LiDAR; long wall 3.89 vs 4.24 m;
95 s and 12.3 GB peak on the M4.

## Model findings (the main result of this session)

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
| Runs on the M4 | MapAnything (proven) | Pi3X peaked 12.6 GB on the T4: probably fits, untested |
| License | MapAnything (Apache 2.0) | Pi3X and DA3-nested are CC BY-NC |
| Depth Anything 3 | not measured | failed on a missing `addict` dependency |

Other findings:
- Stray `rgb.mp4` frames are stored **sideways**; sideways input collapses every model.
- Giving the model the true focal length, or re-projecting its depth with it, did **not**
  fix the short walls (made them worse).
- Same weights and frames: 11.43 m² (T4, fp16) vs 11.87 m² (M4, MPS): 4% from numerics.
- **Recommendation (not yet adopted):** Pi3X for video/photo geometry, MapAnything as the
  Apache fallback behind a flag; disclose the non-commercial license. Conditions: Pi3X
  must run on the M4 for the walk-in, and a scale correction is needed either way.

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
- Disk: MapAnything weights (4.9 GB) are in the local HF cache; the user does not want
  more multi-GB models on the laptop: big models run on Kaggle.

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

## Gotchas

- GitNexus misses Python call edges; grep to confirm callers.
- Absolute height thresholds break on low scans (A's `c00a170fe1` never sees above 1.7 m).
  Prefer shape rules.
- Fused clouds are cached as `outputs/cache/<id>.npy` (used by `scripts/diag_repeat.py`).
- Plain `uv sync` removes the `video` extra; use `uv sync --extra video`.
