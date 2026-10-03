# Handover (Sat Oct 3, ~22:20 IST)

Cozmo AI take-home: iPhone captures → dimensioned floor plans with intervals. Deadline
**Mon Oct 5, 10:00 IST**. Read in this order: this file, [NEXT-SESSION.md](NEXT-SESSION.md),
`CLAUDE.md` (commands, layout, data conventions), the status section of `ROADMAP.md`.

## State

- **LiDAR tier works** end to end: `uv run floorplan run <capture>` → `plan.json` +
  `plan.png`. 61 tests pass. Video and photo tiers are **stubs** (warning only); the
  model for them is chosen (MapAnything, `docs/model_spike.md`), installed only in a
  scratch venv so far.
- **Drift correction** exists but is **opt-in** (`--drift`): mixed ablation
  (`docs/drift_ablation.md`); **off by default, decided by the user** (it made the
  `c_home_01` kitchen much worse).
- **Room segmentation** (`src/floorplan/plan2d.py`) now: counter fronts are not walls
  (shape rule); door lintels split rooms; seen floor bounded by an unscanned wall is
  attached ≤ 1 m deep as a low-confidence zone (`rooms[].low_confidence_area`, warning,
  widened `floor_area.lo`); rooms touching > 2 m with no wall merge.
- **Data on disk** (gitignored): A = Cozmo's apartment, 3 Stray captures, no ground truth.
  B = ARKitScenes room, 3 captures + laser scan. C = friend's home:
  `data/home_c/lidar/c_home_01` (whole home), `c_damage_01/02` (damaged room, one ~3 in
  hole, twice). C has **no tape measurements, Polycam, Camera-app video or photos**, and
  none are expected.
- **Ground truth:** only `data/gt/home_c_rooms.json` (room identity labels, not
  dimensions). B's laser measurements are with the user's architect (blind); they land in
  `data/gt/arkitscenes_421337.yaml`.
- **Fix loop:** `docs/fix_loop.md` has the fix map and the entries. Shipped: Fix 01
  (`fix01-before` → `fix01-after`, `c_home_01` rooms found 2/4 → 4/4) and Fix 01c
  (`fix01c-before` → `fix01c-after`, hall fragment gone, hall IoU 0.59 → 0.79, 2.9 m²
  flagged), Fix 02 ceiling (`fix02-before` → `fix02-after`). Latest 9-capture table:
  the fix 02 entry. A's changes are unverified.
- **Cozmo answered:** hosted model APIs allowed; head-to-head on our own data (needs a
  Polycam export we don't have, so it's at risk).

## Hard rules (from the user and the brief)

- Never call something done when it is scaffolding. Report failures and wrong predictions.
- Commit small and often (graded); push only when the user asks.
- Keep ROADMAP status, COMPLIANCE rows, README and CLAUDE.md in sync with each change.
- Ground truth is measured by hand, blind, never by our own code.
- Video/photo tiers on a LiDAR recording read only the RGB video.
- Every geometry change: run `uv run scripts/lidar_summary.py` (all 9 captures) and
  compare with the last table in `docs/fix_loop.md`. A fix that helps one capture and
  breaks another is not done.
- Don't blame the capture for code bugs in write-ups (the user asked once; declined with
  evidence).

## Gotchas

- GitNexus misses Python call edges (`impact` reports 0 callers for `segment_rooms`; the
  real caller is `lidar.build_plan`). Grep to confirm.
- Absolute height thresholds break on low scans (A's `c00a170fe1` never sees above 1.7 m).
  Prefer shape rules.
- Fusing a capture takes 8–20 s; cache clouds as `.npy` in a scratch dir when iterating
  (`outputs/cache/<id>.npy`, used by `scripts/diag_repeat.py`).
- Stray `rgb.mp4` frames are stored **sideways** (portrait capture): multi-view models need
  them rotated 90° clockwise first.
- MapAnything venv: clone `facebookresearch/map-anything`, `uv venv`, `uv pip install
  torch torchvision -e . -e <this repo>`; weights 4.9 GB in the HF cache; 12.8 GB peak RAM
  for 30 frames.
