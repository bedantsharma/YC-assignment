# Roadmap

Deadline: **Mon Oct 5, 10:00 IST**. Start: Sat Oct 3, ~12:30 IST. About 45 working hours
including sleep. Scope and scoring are in [requirements.md](requirements.md).

## Status (Mon Oct 5, submission)

**Submission state:** every deliverable exists and is checked (COMPLIANCE.md: 47 done / met,
12 partial, 3 not met, 2 in progress = the live walk-in rehearsal). Raw-data bundle on Google
Cloud Storage (link in the submission), reproduce.sh verified end to end, fresh clone runs
LiDAR in about a minute, walk-in runbook + `floorplan check`. Video / photo model on Kaggle
by default. Details: HANDOVER.md (Oct 5 section).

## Earlier status (Sun Oct 4 evening)

Read this first when resuming (after [HANDOVER.md](HANDOVER.md) and
[NEXT-SESSION.md](NEXT-SESSION.md)). Details are in the phase sections below.

**Headline:** the graded fix is shipped ([docs/fix_declaration.md](docs/fix_declaration.md),
tags `fixloop-before` / `fixloop-after`). Against home C's ground truth our LiDAR tier went
from 29 cm (median, every side short) to **5 cm**; Polycam is 6 cm. **Head-to-head: beat or
tie on 6 of 8 dimensions (75%, target 70%)**. Camera-app damage-room videos (60 frames):
−30 → +5 cm after the video scale bias was re-measured (it had been fitted to the short
LiDAR). `uv run scripts/gt_table.py` ([docs/gt_comparison.md](docs/gt_comparison.md))
regenerates everything. **No model runs on the laptop (user)**: Kaggle runs, the laptop
replays cached outputs.

**Evening (Oct 4):** the friend's new eye-level house clip gives 4 of 4 rooms at every frame
count (footprint IoU 0.72-0.76; the old clip 0.42), but sides come out 20-50 cm long: one
scale error. Real photos (85, three rooms): median 19 cm with every photo, kitchen fails at
8 or fewer. ARK (B) ground truth arrived (approximate; face convention unresolved). Damage
research done; plan agreed (Gemini + small local fallback models). Kaggle runs now use both
T4s; video frames are decoded on the laptop so Kaggle's results replay. Details:
[HANDOVER.md](HANDOVER.md), next steps: [NEXT-SESSION.md](NEXT-SESSION.md).

**Finding (user decision, Oct 4): on what was scanned we now measure as accurately as
Polycam; the remaining large error is missing data, not geometry.** The one dimension we
clearly lose (dining & living short side, −23 cm vs Polycam's 3 cm) is bounded by a west
wall that has no points at any height in `c_home_01` (fix map 01c). No rescan is possible
(the friend can't redo it), so this stays as a capture limit: the plan flags that floor as
low confidence and widens the area interval, and the report states it rather than tuning
for it. The capture protocol already asks for every wall to be swept top to bottom.

### Progress at a glance

| Phase | Planned for | State |
|---|---|---|
| 0 Scaffolding | Sat 12:30 | **Done** (device matrix filled from the benchmark) |
| 1 Data | Sat 12:30 | **Done**: A, B, C in; C's ground truth, Polycam, videos (incl. a new house clip) and real photos in; B's architect measurements in (approximate) |
| 2 LiDAR backend | Sat 17:00 | **Done**: 9 captures end to end; 5 cm median vs ground truth after fix 09 |
| 3 Repeatability, drift | Sat 23:00 | **Done**: drift built + ablated (off); repeatability table in the benchmark report (gate not met: 0.4 / 4.6 cm) |
| 4 Video, photo | Sun 08:00 | **Done with gaps**: video works on room clips and the new house clip (scale 20-50 cm long); photo per room on real photos (median 19 cm), stitch fails |
| 5 Openings, damage, scope | Sun 14:00 | **Openings partial** (doors, passages); **damage done** on all three tiers (Gemini or Florence-2 + wall-plane sizing + rules + scope; staged hole inside the interval 7 of 7) |
| 6 Benchmark, fix loop | Sun 18:00 | **Done**: fix loop, head-to-head (75%), `scripts/benchmark.py` (real-photo and B rows in), calibration |
| 7 Reports, packaging | Mon 01:00 | **Done**: benchmark + technical report, reproduce script, raw-data bundle, fresh-clone test, slide deck; walk-in rehearsal still to do |

By score weight: walk-in (30%) runs all three tiers (photo per room); fix loop (25%) has
its failing gate (short walls) and evidence; benchmark (15%) has ground truth on C;
head-to-head (10%) met: 6 of 8 beat or tie (5 vs 6 cm median);
compliance (10%), capture route (5%) and commit history (5%) on track.

- **Done today (Sun)**
  - **After the fix**: Kaggle refilled the replay cache for every plan (`kaggle/cache_runs`);
    calibration per tier (`scripts/calibration.py`: 90% coverage of sides LiDAR 91%, video
    92%, photo 80% after widening photo to its measured error); doors and passages
    (`openings.py`, G1 not met); benchmark report (`scripts/benchmark.py`), technical report
    (5 pages), `scripts/reproduce.sh`, device matrix filled
  - **Graded fix** ([docs/fix_declaration.md](docs/fix_declaration.md)): walls measured
    above 2.3 m at the centre of the drift smear, own side of interior walls; LiDAR 29 →
    5 cm; video scale bias re-measured (Pi3X 0.964 → 0.890); head-to-head added to
    `gt_table.py`
  - Camera-app videos + Polycam ([docs/home_c_new_captures.md](docs/home_c_new_captures.md)):
    damage-room clips within 5 cm of our LiDAR; house clip fails (windows fold rooms);
    chained-window links repaired (`chunks.fit_shared`)
  - Reconstruction cache (`mvs.py`): Kaggle runs, laptop replays
  - LiDAR model survey + SpatialLM bake-off on two T4s
    ([docs/lidar_model_research.md](docs/lidar_model_research.md)): not adopted
  - Ground truth for C + `scripts/compare_gt_c.py` + `scripts/gt_table.py`
- **Waiting on**
  - User: Gemini API key (for damage detection)
  - Architect: outer vs inner wall faces on the ARK plan
- **Next, in order** (details: [NEXT-SESSION.md](NEXT-SESSION.md))
  1. Collect the house video rerun and photo replays; add house, photo and B rows to `gt_table.py`
  2. Phase 5 damage: Gemini boxes + SAM 2.1 tiny masks, projected onto walls; rules; scope
  3. Video scale on the new house clip (without overfitting the benchmark)
  4. Presentation format; walk-in plan for the image tiers; fresh-clone test

## Principles

- **Data first.** Our own captures and tape measurements block benchmarking, the photo and
  video tiers, damage, and the fix loop. Capture them on Saturday afternoon while the light is
  good.
- **One backend, three front ends.** Build the geometry backend once on LiDAR (cleanest
  data), then feed it video and photo reconstructions.
- **Always have something that runs end to end.** From Phase 2 on, `floorplan run <capture>`
  must produce JSON + a plan, even if parts are stubbed. The walk-in test (30%) rewards a
  pipeline that never crashes.
- **Freeze the "before" for the fix loop.** The fix loop (25%) needs a regenerable before
  run, so we tag the commit before fixing anything.
- **Time-box hard things.** Each phase has a cut line: if time runs out, cut below the line
  and record the gap in the compliance matrix.
- **Commit at every working step** (process evidence, 5%).

## Phase 0: Scaffolding (Sat 12:30–14:00, 1.5 h)

Why first: cheap, guaranteed marks (compliance 10%, capture route 5%), and the output format fixes
the interface every later phase writes to.

- [x] JSON output format (our own; no published schema, and no formal JSON Schema file):
      rooms, walls, openings, surfaces, damage, flags, scope items; every number as
      `{value, lo, hi, unit}`. Fields documented in the README; `src/floorplan/output.py`
- [x] Compliance matrix (`COMPLIANCE.md`): 64 requirements, statuses updated as work lands
- [x] Capture protocol draft (`docs/capture_protocol.md`) for all three tiers, including
      the doorway-overlap photo rule (~15 photos per room, minimum 4)
- [x] Device matrix scaffolding (`docs/device_matrix.md`): hardware per tier fixed
- [x] Device matrix accuracy numbers: filled from the benchmark in Phase 6
- [x] CLI skeleton: `floorplan run <capture_dir> --tier {lidar,video,photo} --out outputs/`
- [x] Loaders for Stray Scanner and ARKitScenes (common z-up frame, verified on real data),
      video and photo folders (paths only: isolation rule enforced)

Exit: `uv run floorplan run data/raw/c7d28f72c6` writes a valid (mostly empty) JSON.

## Phase 1: Data acquisition (Sat 12:30–16:00)

Why now: everything from Phase 4 on needs ground truth, and daylight matters for photos.
Sources and how each is used: [docs/data_plan.md](docs/data_plan.md).

- [x] Dataset A: Cozmo's 3 Stray Scanner captures in `data/raw/` (verified, fuses cleanly)
- [x] Dataset B: ARKitScenes venue 421337, 3 captures + 1 laser station (4.6 GB,
      `scripts/fetch_arkitscenes.sh`)
- [x] Capture checklist written and sent to the friend
      ([md](docs/friend_capture_checklist.md), PDF)
- [x] Dataset C, friend's home on an iPhone 16 Pro: LiDAR (whole home,
      damage room ×2), Camera-app videos (damage room ×2, whole house), Polycam
      screenshots, ground truth and real photos per room in
- [x] Check B's laser station covers every wall: yes, all four walls are visible (some
      parts in furniture shadow at 1.1 m, visible at other heights); no second station needed
- [x] Laser cloud prepared for hand measurement (`scripts/prepare_laser_gt.py`: cropped,
      thinned to 5 mm, E57 / LAS / PLY) with
      [the measurement sheet](docs/laser_measurement_sheet.md);
      zip in `outputs/laser_scan_for_measuring.zip`
- [x] Send the zip to the architect; she measures blind (without seeing our output)
- [x] Her measurements → `data/gt/arkitscenes_421337.json` (approximate; outer vs inner faces to confirm)
- [x] Friend's house: architect's drawing + tape measurements → `data/gt/home_c.json`
      (Sun Oct 4; ceiling 11 ft by user decision); held-out room still to pick

Exit: all three datasets on disk, both ground-truth files complete.

## Phase 2: LiDAR geometry backend (Sat 17:00–23:00, 6 h)

Why: the core of every tier and the walk-in test. LiDAR first because its data is cleanest,
so bugs are in our code, not the input.

- [x] Fused, voxel-downsampled, confidence-filtered point cloud (`cloud.py`)
- [x] Floor and ceiling levels from height histograms, per room (`levels.py`)
- [x] Wall evidence = vertical extent per grid cell (drops furniture); Manhattan orientation
      from histogram sharpness (`plan2d.py`)
- [x] Room segmentation: enclosure ray test (drops floor seen through windows) + watershed
      split at doorways (`plan2d.py`)
- [x] Per room: rectilinear polygon snapped to wall faces, wall lengths, floor area, ceiling
      height (`rooms.py`, `lidar.py`)
- [x] Provisional intervals from surface spreads (±1.645σ; calibrate in Phase 6)
- [x] Render the plan (`render.py`) + write JSON; wired into `floorplan run`

Result (Sat evening): dataset A gives 6 / 5 / 3 rooms, B one ~4 × 5 m room (ceiling 3.05 m),
8–23 s per capture. Not yet compared with ground truth.

Known issues found on real data (to address in Phases 3 and 6):
- Open-plan spaces are split where the watershed happens to meet, not at a real boundary
- Small spurious steps (0.3–0.5 m) where furniture or clutter touches a wall
- Tall furniture against a wall (wardrobes) counts as wall, so the room shrinks
- A floor-to-ceiling opening into unscanned space can notch the room outline
- c7d28f72c6 r2 and r3 report ceilings of 2.3–2.4 m: possibly real lowered ceilings, or a
  cabinet top; check against the video
- No drift correction yet; openings (doors, windows) not detected yet

Exit: all three provided captures produce a plan with recognisable rooms.
Cut line: if room segmentation fights back, output a single whole-floor polygon plus walls.

## Phase 3: Repeatability and drift (Sat 23:00–Sun 01:00, 2 h)

Why: two benchmark gates that need no ground truth, using the three provided captures.

- [ ] Align the three captures (ICP on the 2D wall map) and match rooms and walls
- [x] Repeatability table: same wall across captures, spread in cm and % (benchmark report;
      C and B scans)
- Drift probe (`uv run scripts/drift_probe.py <capture>`, Sat 21:05): revisited walls
  move between time chunks by up to 8.8 cm (`c_home_01`) and 12.9 cm (A `c7d28f72c6`),
  but single-room scans already show 4–6 cm and ±1–2° per chunk (probe noise: partial
  views, furniture). So drift here is at most ~5–10 cm and the probe cannot resolve it;
  the ablation needs a sharper measure (wall-face spread before/after)
- [~] Drift handling: **built, off by default** (`--drift`; chunked 2D ICP on wall points,
      not the planned plane snap). Ablation on all 9 captures in
      [docs/drift_ablation.md](docs/drift_ablation.md): damage-room repeat scans agree to
      1 cm on the short side (was 21 cm), but A `c00a170fe1` walls lose support. Still to
      do: trace that regression; ablation figure of the stitched footprint
- [x] **Tag `fixloop-before`** once the first full benchmark numbers exist

Exit: `scripts/benchmark_lidar.py` prints the repeatability table and drift ablation.

Sleep: Sun 01:00–08:00.

## Phase 4: Video and photo tiers (Sun 08:00–14:00, 6 h)

Why: Cozmo expects all three tiers working, and the walk-in tier is chosen on the day.

- [x] **1 h spike:** run a pretrained multi-view reconstruction model (candidates: VGGT,
      MASt3R, MapAnything) on 30 frames from a provided `rgb.mp4`; check it runs on this Mac
      and compare its geometry to LiDAR. Pick the model by result, not reputation.
      **Done Sat 21:45 ([docs/model_spike.md](docs/model_spike.md)):** MapAnything runs
      (52 s / 30 frames, 12.8 GB peak); with upright frames scale 1.03 vs ARKit, cloud 5.8 cm
      median from LiDAR, but room 11.1 vs 13.1 m². Sideways frames collapse it. VGGT and
      MASt3R not tried
- [x] Metric scale: model's metric output, plus a per-model horizontal / vertical bias
      fitted on the damage room and checked on 3 held-out rooms (ceiling within 3.3%,
      √area mean error 3.8%; [docs/video_scale.md](docs/video_scale.md)). Provisional until
      ground truth
- [x] Video tier: sample frames → reconstruction → same backend as Phase 2. Pi3X default,
      MapAnything fallback; > 30 frames go through chained windows (4 of 4 rooms on
      `c_home_01`, 57.3 vs 59.8 m² LiDAR)
- [x] Photo tier ([docs/photo_tier.md](docs/photo_tier.md), Sun night): Firecrawl survey +
      Kaggle bake-off round 2 (Pi3X again; DA3 out of memory at 8 photos). Each folder
      reconstructed alone, line-of-sight carving, folder = room label. Rooms with ≥ 4 good
      photos within −7% to +1% of LiDAR area. **Joint reconstruction placed rooms 1–2 m
      wrong, so rooms are not stitched** (cut line taken; documented)
- [x] Tier-specific interval widening: video (5% / 2%) and photo (14% / 5.5%) per axis, 1σ;
      calibrated against home C's ground truth (`scripts/calibration.py`)
- [x] Run on the provided captures (LiDAR as reference) and on our own captures (tape as
      reference)

Exit: one command per tier works on our own captures.
Cut line: if joint photo reconstruction fails, reconstruct per room and place rooms using
the doorway photos; if that fails too, document the photo stitch as failing.

## Phase 5: Openings, damage, scope (Sun 14:00–18:00, 4 h)

- [~] Openings: gaps in each wall line in the 2D map + depth discontinuities → widths
      (`openings.py`: doors and passages; windows not detected, gate G1 not met)
- [x] One shared detector (agreed Sat; built as Gemini 3.1 Pro hosted + Florence-2-base
      offline): open-vocabulary (YOLO-World / Grounding DINO;
      hosted vision model as fallback) on RGB keyframes, with a text list of classes. Box →
      depth pixels in the box → 3D with the frame's pose (same frame index as the depth; no
      IMU work needed) → footprint on the plan. Built once, used for:
  - [x] Damage (LiDAR tier; run on Gemini and Florence-2, docs/damage_hole.md): Gemini
        boxes, model-free masks, outline rays onto the wall plane, Monte Carlo 90% interval,
        views merged (`src/floorplan/damage*.py`, `floorplan run --damage`)
  - [~] Damage keyframes, agreed Oct 4 (LiDAR built; video pauses still to do; before:
        40 even time slots, sharpest of 3, all sent to Gemini):
    - [x] Protocol: pause ~3 s about 1 m in front of each damage during the LiDAR / video
          walk; photo tier: 1-2 close-ups per damage *inside the room's folder* (a loose
          close-up has no pose or scale, so it cannot be sized)
    - [x] Pause detection (LiDAR): still camera or gaze dwell (image centre stays on one
          close spot) → 2 frames per pause (`damage_frames.py`); video: from pixels, to do
    - [x] Coverage keyframes (LiDAR): greedy cover of 0.25 m wall patches, 2 views each
          within 3 m and 60 deg; unseen surfaces warned
    - [x] Two-view rule (`damage_frames.confirm`): an item reported in one keyframe while
          2+ keyframes looked at that spot is dropped (listed in warnings); one reported
          where no other keyframe could see is kept as unconfirmed. c_damage_02: 14 → 6
          items, c_damage_01: 19 → 13; the staged hole kept on both
    - [ ] **Pauses for the video tier** (no poses, only pixels):
      - [ ] decode the whole clip at 160x120 (one ffmpeg pass, cheap); phase correlation
            between neighbouring frames → image shift in px/s; a pause = shift below a
            threshold for >= 1.2 s (the pixel version of the LiDAR gaze dwell)
      - [ ] guard against blank walls (little texture → low shift while walking): require
            enough image gradient in the frame, or treat those stretches as unknown
      - [ ] reconstruction sample = pause frames first, then evenly spaced frames, so every
            frame the detector sees has a Pi3X pose (new Kaggle run for the video numbers)
      - [ ] coverage selection on the Pi3X poses and walls (same `select`), two-view rule
            on the same cameras; sizes carry the video tier's scale interval
      - [ ] test on the Camera-app damage-room clips (they have the staged hole) and score
            with `scripts/damage_hole_check.py`
    - [x] Photo tier damage: every photo goes to the detector (staged hole from 8 photos:
          28.0 cm2 [15.4, 46.4] vs 31.7)
    - [x] Offline fallback: Florence-2-base proposes boxes, crop captions classify
          (`damage_local.py`; auto on Gemini failure after retries)
    - [ ] Optional: cheap low-res screening pass, full-res only on frames with a hit
  - [x] Damage on the video and photo tiers (`damage_images.py`: the reconstruction's own
        images; sizes from its per-pixel points projected onto the walls)
  - [ ] Fix map 04: wardrobe / fridge / bookshelf boxes removed from the wall mask
  - [ ] Stretch: furniture symbols on the plan (not required by the brief)
- [x] Concealed-damage rule table (e.g. ceiling stain → leak above; stain at skirting →
      rising damp); each flag names its rule (`damage_rules.py`: R1-R5, R7-R10; R6 not built)
- [x] Scope line items keyed to surface ids (repaint wall W3: 12.4 m², etc.)

Exit: the damaged room produces damage regions, a flag, and scope lines.
Cut line: openings as door/passage gaps only, no windows.

## Phase 6: Benchmark and fix loop (Sun 18:00–Mon 01:00, 7 h)

Why: fix loop is 25% and benchmark accuracy is 15%; both need everything above to exist.

- [x] `scripts/benchmark.py`: every gate at every tier vs ground truth; repeatability table;
      timing; one command regenerates all numbers
- [x] Pick the single worst failing gate; write `docs/fix_declaration.md` (failing number,
      root-cause hypothesis + evidence, fix, predicted number) **before** fixing
- [x] Ship the fix; rerun; record before vs after (both regenerable from tags
      `fixloop-before` / `fixloop-after`)
- [x] Head-to-head on our own data (Cozmo confirmed): our LiDAR vs Polycam on 4 rooms of
      dataset C vs the architect's drawing; beat or tie on 6 of 8 (75%)

Exit: fix-loop bundle complete with honest numbers.

## Phase 7: Reports and packaging (Mon 01:00–08:00, incl. ~3 h sleep)

- [x] Benchmark report (gates at all tiers, repeatability, head-to-head, timing)
- [x] Technical report ≤ 6 pages: architecture, tier design + device matrix, drift
      handling, error budget, calibration, fix-loop story, known failure modes (mirrors,
      glass, wet surfaces, low light)
- [x] Final compliance matrix with honest statuses
- [x] README: fresh clone → running on a new capture in < 15 min; model weights fetched by
      script
- [x] Reproduction bundle: raw captures + ground truth + cached model outputs (deterministic
      replay) packaged for upload
- [x] Fresh-clone test in a temp directory (install 33 s, first LiDAR capture 27 s)

## Buffer (Mon 08:00–10:00)

Final walk-in rehearsal: someone else follows our protocol on a room we haven't used, and
the pipeline runs cold. Submit by 09:30.

## Defense prep (after submission)

Every design decision is defended live with tools closed. Keep a running
`docs/decisions.md` log (one line per decision + why) as we go, and review it before the
defense.
