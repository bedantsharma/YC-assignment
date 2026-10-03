# Roadmap

Deadline: **Mon Oct 5, 10:00 IST**. Start: Sat Oct 3, ~12:30 IST. About 45 working hours
including sleep. Scope and scoring are in [requirements.md](requirements.md).

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

Why first: cheap, guaranteed marks (compliance 10%, capture route 5%), and the schema fixes
the interface every later phase writes to.

- [ ] Output JSON schema (`schema/floorplan.schema.json`): rooms, walls, openings, surfaces,
      damage, flags, scope items; every number as `{value, lo, hi, unit}`
- [ ] Compliance matrix skeleton (`COMPLIANCE.md`), every row "not started"
- [ ] Capture protocol draft (`docs/capture_protocol.md`) for all three tiers, including
      the doorway-overlap photo rule, plus the device matrix
- [ ] CLI skeleton: `floorplan run <capture_dir> --tier {lidar,video,photo} --out outputs/`

Exit: `uv run floorplan run data/raw/c7d28f72c6` writes a valid (mostly empty) JSON.

## Phase 1: Capture our own benchmark (Sat 14:00–17:00, 3 h, physical)

Why now: everything from Phase 4 on needs it, and daylight matters for photos.

Follow our own protocol literally (it is graded on how a non-engineer would experience it):

- [ ] Choose 3+ rooms plus a hallway in one home
- [ ] Stage damage in one furnished room, two classes (e.g. tape "crack" + tea-stain "water
      damage" on paper taped to a wall)
- [ ] Video walkthrough of all rooms (native Camera, 1080p or 4K, steady walk)
- [ ] Photo folders: 2–8 stills per room, plus one photo through each doorway
- [ ] Repeat one room at the video tier and at the photo tier (repeatability)
- [ ] Tape-measure ground truth into `data/gt/<home>.yaml`: every wall length, ceiling
      height per room (2 spots), every door and window width, room-to-room adjacency
- [ ] Photograph the tape readings as evidence

Exit: raw captures in `data/raw/`, ground truth file complete.

## Phase 2: LiDAR geometry backend (Sat 17:00–23:00, 6 h)

Why: the core of every tier and the walk-in test. LiDAR first because its data is cleanest,
so bugs are in our code, not the input.

- [ ] Loader → fused, voxel-downsampled, confidence-filtered point cloud (from
      `scripts/fuse_topdown.py`)
- [ ] Floor and ceiling planes (RANSAC on horizontal points) → ceiling height per room
- [ ] Wall-height slice → 2D occupancy image → line segments (RANSAC / Hough) → Manhattan
      snapping to the dominant orientation
- [ ] Room segmentation of the 2D free-space map (watershed / connected components)
- [ ] Per room: polygon, wall lengths, floor area, ceiling height
- [ ] Intervals from plane-fit residuals and per-frame spread
- [ ] Render the plan (matplotlib, dimensions on every wall) + write JSON

Exit: all three provided captures produce a plan with recognisable rooms.
Cut line: if room segmentation fights back, output a single whole-floor polygon plus walls.

## Phase 3: Repeatability and drift (Sat 23:00–Sun 01:00, 2 h)

Why: two benchmark gates that need no ground truth, using the three provided captures.

- [ ] Align the three captures (ICP on the 2D wall map) and match rooms and walls
- [ ] Repeatability table: same wall across captures, spread in cm and %
- [ ] Drift handling: plane-anchored correction (snap walls to the dominant axes, re-solve
      poses) with an on/off flag; ablation figure of the stitched footprint
- [ ] **Tag `fixloop-before`** once the first full benchmark numbers exist

Exit: `scripts/benchmark_lidar.py` prints the repeatability table and drift ablation.

Sleep: Sun 01:00–08:00.

## Phase 4: Video and photo tiers (Sun 08:00–14:00, 6 h)

Why: Cozmo expects all three tiers working, and the walk-in tier is chosen on the day.

- [ ] **1 h spike:** run a pretrained multi-view reconstruction model (candidates: VGGT,
      MASt3R, MapAnything) on 30 frames from a provided `rgb.mp4`; check it runs on this Mac
      and compare its geometry to LiDAR. Pick the model by result, not reputation
- [ ] Metric scale: model's metric output, or a monocular metric-depth model, cross-checked
      against ceiling height priors
- [ ] Video tier: sample frames → reconstruction → same backend as Phase 2
- [ ] Photo tier: all folders reconstructed jointly (doorway photos link rooms); folder =
      room label → stitched plan
- [ ] Tier-specific interval widening, calibrated against our tape ground truth
- [ ] Run on the provided captures (LiDAR as reference) and on our own captures (tape as
      reference)

Exit: one command per tier works on our own captures.
Cut line: if joint photo reconstruction fails, reconstruct per room and place rooms using
the doorway photos; if that fails too, document the photo stitch as failing.

## Phase 5: Openings, damage, scope (Sun 14:00–18:00, 4 h)

- [ ] Openings: gaps in each wall line in the 2D map + depth discontinuities → widths
- [ ] Damage: vision model on keyframes → class + bounding box → project onto the wall plane
      for metric extent (hosted API if Cozmo allows, local fallback otherwise)
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
- [ ] Head-to-head, if Cozmo answers with a usable option

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
