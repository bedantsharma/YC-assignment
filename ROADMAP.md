# Roadmap

Deadline: **Mon Oct 5, 10:00 IST**. Start: Sat Oct 3, ~12:30 IST. About 45 working hours
including sleep. Scope and scoring are in [requirements.md](requirements.md).

## Status (Sun Oct 4, ~01:15 IST)

Read this first when resuming (after [HANDOVER.md](HANDOVER.md) and
[NEXT-SESSION.md](NEXT-SESSION.md)). Details are in the phase sections below.

### Progress at a glance (~33 h to the deadline)

| Phase | Planned for | State |
|---|---|---|
| 0 Scaffolding | Sat 12:30 | **Done**, except device-matrix numbers (need the benchmark) |
| 1 Data | Sat 12:30 | **Mostly done**: A, B, C's LiDAR + video in; ground truth (architect, friend's plan) not in |
| 2 LiDAR backend | Sat 17:00 | **Done**: 9 captures run end to end |
| 3 Repeatability, drift | Sat 23:00 | **Half**: drift built + ablated (off); repeatability table and `fixloop-before` tag not done |
| 4 Video, photo | Sun 08:00 | **Video done early** (whole home, scale corrected); **photo not started** |
| 5 Openings, damage, scope | Sun 14:00 | Not started |
| 6 Benchmark, fix loop | Sun 18:00 | Not started (needs ground truth); three practice fixes done in `docs/fix_loop.md` |
| 7 Reports, packaging | Mon 01:00 | Not started |

By score weight: walk-in (30%) can run LiDAR and video but not photo yet; fix loop (25%)
has the method rehearsed but the graded fix needs the benchmark; benchmark (15%) and
head-to-head (10%) wait on ground truth and a Polycam export; compliance (10%), capture
route (5%) and commit history (5%) are on track.

- **Done**
  - Phase 0 scaffolding (output format, compliance matrix, capture protocol, CLI, loaders),
    except the device matrix numbers (see warning in Phase 0)
  - Phase 1: datasets A and B on disk; friend's checklist sent; B's laser station checked
    (covers all four walls); **dataset C LiDAR in**: whole-home walk
    `data/home_c/lidar/c_home_01` (4 rooms, ~56 m², 22 s; unverified) and the staged-damage
    room twice, `c_damage_01` / `c_damage_02` (one ~3 in hole in a wall; ~10 s each)
  - **Phase 2: LiDAR tier runs end to end.** `uv run floorplan run <capture>` writes
    `outputs/<id>_lidar/plan.json` + `plan.png` with an interval on every number. 61 tests
  - Laser ground-truth package built: `uv run scripts/prepare_laser_gt.py` →
    `outputs/laser_gt/` and `outputs/laser_scan_for_measuring.zip` (120 MB: E57, LAS, PLY,
    overview, [measurement sheet](docs/laser_measurement_sheet.md) PDF)
  - Phase 4: model spike + Firecrawl survey + Kaggle bake-off round 1
    ([docs/model_research.md](docs/model_research.md)): Pi3X wins on geometry (cameras 5×
    more accurate), MapAnything on license. **User chose Pi3X (Sun 00:00)**, MapAnything
    kept behind `--model mapanything`
  - **Video tier works on the whole home** ([docs/video_scale.md](docs/video_scale.md)):
    Pi3X on the M4 (119 s / 10.9 GB per 30 frames), 90 frames in 4 chained windows, scale
    bias divided out (fitted on the damage room, checked on 3 other rooms). `c_home_01`:
    4 rooms, 57.3 [52.2, 62.5] m² vs 59.8 m² LiDAR; every room's LiDAR area and ceiling
    inside the video interval
  - Drift correction built and ablated, **off by default (user decision)**
    ([docs/drift_ablation.md](docs/drift_ablation.md))
- **Datasets: B stays (decided Sat 23:00).** B's laser scan is the only absolute ground
  truth until C's measurements arrive, so B is kept as the benchmark dataset (not used in
  the walk-in path). Revisit once C has tape numbers
- **Waiting on**
  - **Friend: house measurement plan (tape dimensions of C's rooms), user asks him Sun
    Oct 4.** When it arrives: transcribe → `data/gt/home_c.yaml` (by hand, never from our
    output), then C becomes a second ground-truth dataset (all three tiers on one home)
  - Friend, otherwise: not in hand: Camera-app videos, photo folders, Polycam export,
    so the fallbacks in
    `docs/data_plan.md` apply (B's laser is the only absolute ground truth; C's `rgb.mp4`
    stands in for Camera-app video; stills sampled from video stand in for photo folders;
    head-to-head at risk without a Polycam export)
  - User to send the laser zip to the architect (girlfriend), then her measurements →
    `data/gt/arkitscenes_421337.yaml`. She must measure blind: do not show her our plans
  - ~~Cozmo: hosted APIs allowed? how is the head-to-head run?~~ **Answered (Siva):** hosted
    APIs yes (disclose, keep a local fallback); head-to-head on our own data, i.e. dataset
    C: our LiDAR vs Polycam on 2 rooms, both vs tape. So C's Polycam export is now needed
    for the head-to-head too
- **Fix loop:** [docs/fix_loop.md](docs/fix_loop.md) holds the fix map (work top to bottom)
  and each entry. Fix 01 shipped (`fix01-before` → `fix01-after`): `c_home_01` rooms found
  2/4 → 4/4 (door lintels split rooms; counter fronts no longer walls). Fix 01c
  shipped (`fix01c-after`): the hall's unscanned strip is kept as a flagged low-confidence
  zone (2.9 m²), hall IoU 0.79. Fix 02 (`fix02-after`): ceiling tail ripples no longer
  picked; the damage room's three scans agree on the ceiling within 1 cm (3.35–3.36 m).
  Its wall part failed its prediction twice and was not shipped (PR #1 closed unmerged;
  most likely drift, see the entry)
- **Not yet validated:** no LiDAR number has been compared with ground truth yet; intervals
  are provisional (±1.645σ from surface spreads) until Phase 6 calibrates them
- **Repeatability (C damage room, two scans):** ceiling **passes** after fix 02 (3.36 vs
  3.35 m). Walls **fail**: short side 3.30 vs 3.08 m (window wall, three candidate
  surfaces), notch 15 / 9 cm. B's three scans: ceilings 3.046–3.052 m (pass), extents
  differ up to 0.9 m (fix map 02b, outline/segmentation, untraced). Intervals (±3 cm) are
  overconfident (fix map 03)
- **Next, in order** (details: [NEXT-SESSION.md](NEXT-SESSION.md))
  1. Photo tier (Pi3X on stills; folder = room label)
  2. Openings in the LiDAR backend; Phase 5 damage
  3. Video tier on B's `.mov` vs the laser scan (an independent home for the scale check)
  4. When ground truth arrives (B laser; C measurement plan): accuracy numbers,
     `scripts/benchmark.py`, `fixloop-before` tag

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
- [ ] Device matrix accuracy numbers: filled from the benchmark in Phase 6
- [x] CLI skeleton: `floorplan run <capture_dir> --tier {lidar,video,photo} --out outputs/`
- [x] Loaders for Stray Scanner and ARKitScenes (common z-up frame, verified on real data),
      video and photo folders (paths only: isolation rule enforced)

> **Warning: Phase 0 is not complete.** `docs/device_matrix.md` is scaffolding only, not the
> deliverable. Every accuracy cell is `TBD`, and nothing in it has been measured yet. It
> becomes the real device matrix only once the Phase 6 benchmark fills those cells from
> ground truth. Do not cite it as done in the compliance matrix or the report until then.

Exit: `uv run floorplan run data/raw/c7d28f72c6` writes a valid (mostly empty) JSON.

## Phase 1: Data acquisition (Sat 12:30–16:00)

Why now: everything from Phase 4 on needs ground truth, and daylight matters for photos.
Sources and how each is used: [docs/data_plan.md](docs/data_plan.md).

- [x] Dataset A: Cozmo's 3 Stray Scanner captures in `data/raw/` (verified, fuses cleanly)
- [x] Dataset B: ARKitScenes venue 421337, 3 captures + 1 laser station (4.6 GB,
      `scripts/fetch_arkitscenes.sh`)
- [x] Capture checklist written and sent to the friend
      ([md](docs/friend_capture_checklist.md), PDF)
- [ ] **In progress:** Dataset C, friend's home on an iPhone 16 Pro (all three tiers, staged
      damage, Polycam). LiDAR whole-home walk received (`data/home_c/lidar/c_home_01`);
      staged-damage room twice (`c_damage_01`, `c_damage_02`); tape, videos, photos,
      Polycam not expected
- [x] Check B's laser station covers every wall: yes, all four walls are visible (some
      parts in furniture shadow at 1.1 m, visible at other heights); no second station needed
- [x] Laser cloud prepared for hand measurement (`scripts/prepare_laser_gt.py`: cropped,
      thinned to 5 mm, E57 / LAS / PLY) with
      [the measurement sheet](docs/laser_measurement_sheet.md);
      zip in `outputs/laser_scan_for_measuring.zip`
- [ ] Send the zip to the architect; she measures blind (without seeing our output)
- [ ] Her measurements → `data/gt/arkitscenes_421337.yaml`
- [ ] Friend's house measurement plan (requested Sun Oct 4) → transcribe by hand into
      `data/gt/home_c.yaml`; pick the held-out room

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
- [ ] Repeatability table: same wall across captures, spread in cm and %
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
- [ ] **Tag `fixloop-before`** once the first full benchmark numbers exist

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
- [ ] Photo tier: all folders reconstructed jointly (doorway photos link rooms); folder =
      room label → stitched plan
- [~] Tier-specific interval widening: video done per axis from the held-out rooms (Pi3X 5%
      horizontal, 2% vertical, 1σ); calibration against tape still to do
- [ ] Run on the provided captures (LiDAR as reference) and on our own captures (tape as
      reference)

Exit: one command per tier works on our own captures.
Cut line: if joint photo reconstruction fails, reconstruct per room and place rooms using
the doorway photos; if that fails too, document the photo stitch as failing.

## Phase 5: Openings, damage, scope (Sun 14:00–18:00, 4 h)

- [ ] Openings: gaps in each wall line in the 2D map + depth discontinuities → widths
- [ ] One shared detector (agreed Sat): open-vocabulary (YOLO-World / Grounding DINO;
      hosted vision model as fallback) on RGB keyframes, with a text list of classes. Box →
      depth pixels in the box → 3D with the frame's pose (same frame index as the depth; no
      IMU work needed) → footprint on the plan. Built once, used for:
  - [ ] Damage: hole, crack, water stain → class + metric extent on the wall plane
  - [ ] Fix map 04: wardrobe / fridge / bookshelf boxes removed from the wall mask
  - [ ] Stretch: furniture symbols on the plan (not required by the brief)
- [ ] Concealed-damage rule table (e.g. ceiling stain → leak above; stain at skirting →
      rising damp); each flag names its rule
- [ ] Scope line items keyed to surface ids (repaint wall W3: 12.4 m², etc.)

Exit: the damaged room produces damage regions, a flag, and scope lines.
Cut line: openings as door/passage gaps only, no windows.

## Phase 6: Benchmark and fix loop (Sun 18:00–Mon 01:00, 7 h)

Why: fix loop is 25% and benchmark accuracy is 15%; both need everything above to exist.

- [ ] `scripts/benchmark.py`: every gate at every tier vs ground truth; repeatability table;
      timing; one command regenerates all numbers
- [ ] Pick the single worst failing gate; write `docs/fix_declaration.md` (failing number,
      root-cause hypothesis + evidence, fix, predicted number) **before** fixing
- [ ] Ship the fix; rerun; record before vs after (both regenerable from tags
      `fixloop-before` / `fixloop-after`)
- [ ] Head-to-head on our own data (Cozmo confirmed): our LiDAR vs Polycam on 2 rooms of
      dataset C, both vs tape; beat or tie on ≥ 70% of dimensions

Exit: fix-loop bundle complete with honest numbers.

## Phase 7: Reports and packaging (Mon 01:00–08:00, incl. ~3 h sleep)

- [ ] Benchmark report (gates at all tiers, repeatability, head-to-head, timing)
- [ ] Technical report ≤ 6 pages: architecture, tier design + device matrix, drift
      handling, error budget, calibration, fix-loop story, known failure modes (mirrors,
      glass, wet surfaces, low light)
- [ ] Final compliance matrix with honest statuses
- [ ] README: fresh clone → running on a new capture in < 15 min; model weights fetched by
      script
- [ ] Reproduction bundle: raw captures + ground truth + cached model outputs (deterministic
      replay) packaged for upload
- [ ] Fresh-clone test in a temp directory

## Buffer (Mon 08:00–10:00)

Final walk-in rehearsal: someone else follows our protocol on a room we haven't used, and
the pipeline runs cold. Submit by 09:30.

## Defense prep (after submission)

Every design decision is defended live with tools closed. Keep a running
`docs/decisions.md` log (one line per decision + why) as we go, and review it before the
defense.
