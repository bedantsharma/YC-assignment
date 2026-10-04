# Compliance matrix

Every requirement in the brief (`Applied AI.pdf`) and in Cozmo's written answers (Oct 3),
mapped to the code that implements it, the artifact that proves it, and an honest status.

**Status values:** Not started · In progress · Done · Partial (works, misses part of the
spec or its gate; Notes say which) · Not done (deliberately cut; Notes say why).

Paths marked *(planned)* do not exist yet. Datasets A/B/C are defined in
[docs/data_plan.md](docs/data_plan.md). Last updated: Sun Oct 4, 2026 (night).

## 1. Capture (brief Part 1)

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| C1 | Choose a capture route: own iOS app (Route 1) or stock app + protocol (Route 2) | `docs/capture_protocol.md` | The protocol page | Done | Route 2: Stray Scanner (LiDAR), native Camera (video, photos) |
| C2 | One-page protocol a non-engineer follows: what to install, how to walk, how long, what to avoid, how to hand over files | `docs/capture_protocol.md` | The protocol (+ PDF) | Partial | Covers all five points (incl. the 3 s hold at damage); ~2 pages by choice. The friend (non-engineer) captured home C from an earlier draft; the final version is not yet tested on a new person |
| C3 | Photo tier: 2–8 stills per room, any iPhone 15+, no depth or poses | `src/floorplan/photos.py`, `pipeline._run_photos` (`floorplan run <room folders>`) | `docs/gt_comparison.md` (real photos, all / 8 / 5 per room), `docs/photo_tier.md` | Done | Friend's real photos vs ground truth: with 8 per room the open space is +2 / +4 cm, the bedroom −15 / −11 cm, the drawing room +29 / +32 cm, the kitchen not found (warned); with every photo all four rooms are found. **Deliberate deviation:** protocol asks ~15 photos per room (minimum 4); pipeline accepts 2–8 with wider intervals |
| C4 | Photo tier: one folder per room → the same stitched whole-property plan | `src/floorplan/photos.py` | Per-room plan, rooms named after folders | **Partial** | Folder = room label works; **stitching fails**: joint reconstruction placed rooms 1–2 m wrong, so rooms are laid out side by side with a NOT-stitched warning (`docs/photo_tier.md` §5, §7) |
| C5 | Video tier: handheld walkthrough clip, any iPhone 15+ | `src/floorplan/video.py`, `mvs.py`, `chunks.py`, `intervals.py`, `remote.py` (`floorplan run --tier video`) | `c_home_01` from its `rgb.mp4`: 4 of 4 rooms; `docs/gt_comparison.md`, `docs/video_scale.md` | Done | Pi3X default (CC BY-NC, disclosed), MapAnything fallback (Apache). vs ground truth: 11 of 16 sides within 3%, median 8 cm. Damage-room Camera-app clips within 5 cm of LiDAR. Whole-house clips: the 5-min v1 clip fails (rooms fold onto each other); the eye-level v2 clip finds 4 of 4 rooms (footprint IoU 0.72-0.76 vs LiDAR) but every side 20-50 cm long (one scale error, not fixed). Not run on B |
| C6 | LiDAR tier: depth, poses, intrinsics on Pro devices | `src/floorplan/capture.py`, `cloud.py`, `levels.py`, `plan2d.py`, `rooms.py`, `lidar.py` | Plans from datasets A (3), B (3), C (3) | Done | Stray Scanner and ARKitScenes loaders (common z-up frame); 7-23 s per capture on the laptop |
| C7 | Same output contract from every tier | `src/floorplan/output.py` | One `Result` type, one `plan.json` format | Done | All three tiers write the same fields, damage included |
| C8 | Intervals widen honestly as sensor data thins | `src/floorplan/lidar.py`, `intervals.py`, `scripts/calibration.py` | `docs/benchmark_report.md` (calibration table) | Done | LiDAR from measured surface spreads; video / photo widened by the residual measured against ground truth; 90% coverage of sides 91% / 92% / 80% (photo short of 90%, see G10) |
| C9 | Device matrix: which tier runs on which hardware, and the accuracy each honestly delivers | `docs/device_matrix.md` | Table in technical report | Done | Accuracy per tier copied from the benchmark report |

## 2. Output contract, per capture (brief Part 2)

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| O1 | Per-room plan with walls (dimensioned) | `src/floorplan/plan2d.py`, `rooms.py`, `lidar.py` | `rooms[].walls[]` in JSON + `plan.png` | Done | Median 5 cm vs home C's ground truth (LiDAR) |
| O2 | Ceiling height per room | `src/floorplan/levels.py`, `rooms.py` | `rooms[].ceiling_height` | Done | Per-room floor and ceiling planes; `null` + warning when the ceiling was never captured; accuracy in G2 |
| O3 | Floor area per room | `src/floorplan/rooms.py`, `lidar.py` | `rooms[].floor_area` | Done | Polygon snapped to wall faces; unobserved parts flagged low confidence and widen the interval |
| O4 | Openings (doors, windows) per room | `src/floorplan/openings.py` | `rooms[].openings[]`, [docs/openings.md](docs/openings.md) | Partial | Doors and passages from gaps in wall elevations, confirmed by seeing through; windows not detected (window walls return points across the glass) |
| O5 | Stitched multi-room plan: every room placed, connected, dimensioned, correct adjacency | `src/floorplan/lidar.py`, `src/floorplan/openings.py` | `adjacency[]` + `plan.png` | Partial | LiDAR and video: rooms placed in one frame by construction; adjacency from detected doors (`c_home_01`: hall-drawing, hall-bedroom; kitchen link missed). Photo tier: not stitched (G7) |
| O6 | Stitched plan produced from **every** tier, including photos | `src/floorplan/pipeline.py` | LiDAR + video stitched (`c_home_01`); photo not | Partial | LiDAR and video: one stitched plan; photo: rooms measured but not placed |
| O7 | Per-surface damage regions with class and metric extent | `src/floorplan/damage.py`, `damage_geom.py`, `damage_frames.py`, `damage_lidar.py`, `damage_images.py`, `damage_local.py` (`floorplan run --damage`) | `damage[]`; [docs/damage_hole.md](docs/damage_hole.md), [docs/damage_models.md](docs/damage_models.md), report §8 | Done | All three tiers; staged hole inside the 90% area interval on 7 of 7 runs (LiDAR ×2, LiDAR offline ×2, video ×2, photo). Gemini 3.1 Pro online, Florence-2-base offline fallback. Known: touch grime read as water stain; crack width only from traced cracks |
| O8 | Concealed-damage flags naming the rule that fired | `src/floorplan/damage_rules.py` | `flags[].rule_id`, `flags[].rule` | Done | Rules R1–R5, R7–R10 (research doc §4) on real runs, e.g. R10 near-wiring on the staged hole; R6 (crack from a door corner) not built |
| O9 | Scope line items keyed to surfaces | `src/floorplan/damage_rules.py` | `scope[].surface_id` | Done | Xactimate-style items (trade code, surface id, quantity with interval, no pricing) on every damage run |
| O10 | Confidence interval on every measurement | `src/floorplan/output.py` | Every number is `{value, lo, hi, unit}` | Done | Enforced by the output types; lo ≤ value ≤ hi checked |
| O11 | One command per capture | `src/floorplan/cli.py`, `run.sh` | `uv run floorplan run <capture>` (or `./run.sh <capture>`) | Done | LiDAR 7-23 s on the M4. Video and photo: the model runs on Kaggle's GPUs by default (`--recon auto`), one job per run: 4.4 min end to end for 32 photos in 4 rooms, 0.66 GB on the laptop; replays of cached runs 10-70 s. Without Kaggle: low-memory local run (`--recon local`) |
| O12 | JSON output | `src/floorplan/output.py` | `outputs/<capture>/plan.json` | Done | Own format (no published schema, per Cozmo); fields in README |
| O13 | Rendered plan a homeowner would recognise (as from Polycam / magicplan) | `src/floorplan/render.py` | `outputs/<capture>/plan.png`; examples in `docs/img/deck/` | Partial | Dimensioned walls with intervals, room areas and ceilings, unobserved walls dotted; no door or furniture symbols, damage not drawn on the plan (listed in `plan.json`, outlined on the frames in `damage/`) |

## 3. Benchmark composition (brief Part 2)

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| B1 | One multi-room capture: 3+ rooms plus a connector | `data/home_c/` | `c_home_01` (LiDAR + video), `c_home_v2` (video) | Done | 4 rooms + hall in home C; A covers it too at the LiDAR tier |
| B2 | One furnished room with staged damage spanning two damage classes | `data/home_c/` | `c_damage_01/02` (LiDAR), `c_damage_v1/v2` (video), `photos/room1` | Done | Staged hole with exposed wiring in the furnished bedroom: two classes (no water stain is visible in the photos); labels in `data/gt/home_c_damage_labels.json` |
| B3 | Same rooms at all three tiers, multi-room set included | `data/home_c/` | LiDAR, video and real photos of the same rooms | Done | |
| B4 | At least one room captured twice at the same tier | `data/home_c/`, `data/arkitscenes/` | C bedroom ×2 (LiDAR) and ×2 (video); B room ×3 | Done | Results in G4 |
| B5 | Laser or tape ground truth on everything | `data/gt/` | `home_c.json` (architect's drawing + tape), `arkitscenes_421337.json` | Done | C: drawing for room sizes, tape for ceilings, doors, windows and the staged hole. B: architect's measurements from the laser scan (approximate; inner vs outer face unresolved) |
| B6 | Raw sensor data and measurements submitted | `data/` + upload bundle | Reproduction bundle | Not started | Friend agreed (Oct 4) to submitting home C's raw captures and ground truth; bundle next |

## 4. Gates (brief Part 2)

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| G1 | Opening widths ≤ 2 cm on ≥ 85% of openings; missed and phantom openings count as misses | `src/floorplan/openings.py` | [docs/openings.md](docs/openings.md) | **Not met** | Bedroom door found in both scans but 34 cm narrow (door leaf / frame in the gap); windows not detected |
| G2 | Ceiling height ≤ 1.5 cm per room | `scripts/benchmark.py` | `docs/benchmark_report.md` (ceiling table) | Partly met | LiDAR: 3 of 4 room measurements (−2.1 to +1.0 cm; the dining room misses by 0.6 cm); video 3–14 cm |
| G3 | Ceiling spread across repeat captures ≤ 1 cm; report says bias or noise | `scripts/benchmark.py` | `docs/benchmark_report.md` (repeatability table + bias/noise sentence) | Partly met | B: 0.3–0.6 cm across 3 scans (met); C bedroom 0.2 / 1.3 cm; report: LiDAR error is cm-level noise, image tiers a corrected model bias |
| G4 | Repeatability: two captures of a room agree within 1 cm or 0.5% per wall | `scripts/benchmark.py` | `docs/benchmark_report.md` (repeatability table) | **Not met** | C bedroom scans: short side 0.4 cm, long side 4.6 cm; B scans differ 3–110 cm (coverage, fix map 02b); video v1 vs v2 1.2 cm |
| G5 | Drift: report states the method used on the multi-room capture | `src/floorplan/drift.py` (`floorplan run --drift`) | [docs/drift_ablation.md](docs/drift_ablation.md), technical report §5 | Done | Method stated: chunked 2D ICP on the walls, off by default because the ablation shows it made two plans worse; the default relies on ARKit's own loop closure plus wall measurement at the centre of the drift band (fix loop) |
| G6 | Drift: ablation of stitched footprint with correction on and off | `scripts/drift_ablation.py` | [docs/drift_ablation.md](docs/drift_ablation.md) (table; no figure yet) | Partial | Mixed: damage-room repeat scans 21 → 1 cm on the short side; A `c00a170fe1` walls lose support |
| G7 | Photo tier: one stitched plan, correct adjacency, no overlaps, footprint ±8%, calibrated intervals | `scripts/score_photos.py` (vs LiDAR) | `docs/photo_tier.md` §8 | **Not met** | No stitch (rooms side by side, no adjacency); footprint 45.0 vs 59.8 m² on `c_home_01` protocol stills (hall and room2 had 2–3 photos) |
| G8 | Photo tier: wall lengths ±8% with calibrated intervals | `scripts/benchmark.py`, `scripts/calibration.py` | `docs/benchmark_report.md` | Partly met | vs home C's ground truth: 29 of 40 room sides within ±8%, median 19 cm (real photos and video stills); 90% coverage 80% of sides (calibration scored on the video stills) |
| G9 | Video tier: wall lengths ±3% | `scripts/benchmark.py` | `docs/benchmark_report.md` | Partly met | vs ground truth: 11 of 16 room sides within ±3%, median 8 cm; damage-room clips in-sample for the scale bias |
| G10 | Calibration scored at every tier; no confident garbage on thin input | `scripts/calibration.py` | `docs/benchmark_report.md` (calibration table) | Partly met | 90% coverage vs home C, sides / ceilings: LiDAR 91% / 100%, video 92% / 100%, photo 80% / 88% (photo widened to its measured error; scored on the video stills; rooms seen in part still miss). Area intervals: LiDAR 3 of 6, photo 8 of 11 |

## 5. Head-to-head (brief Part 3)

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| H1 | Our LiDAR-tier output vs a consumer app on 2 benchmark rooms | `scripts/gt_table.py` (head-to-head section) | `docs/gt_comparison.md` | Done | Polycam (RoomPlan) on dataset C, 4 rooms vs the architect's drawing |
| H2 | Name the app and version; submit its export | `data/home_c/polycam/`, `data/gt/home_c_polycam.json` | Polycam 2D plan | Done | **Polycam 7.0.4** (Apple RoomPlan) on the friend's iPhone 16 Pro; plan screenshots in `data/home_c/polycam/` (gitignored locally: they show the street address; go in the raw-data bundle with the address cropped), numbers transcribed in `data/gt/home_c_polycam.json` |
| H3 | One table, our error and theirs, dimension by dimension; beat or tie on ≥ 70% | `scripts/gt_table.py` | `docs/gt_comparison.md` (last section) | **Met** | Beat or tie 6 of 8 (75%) after fix 09 (0 of 8 before); ties judged at Polycam's 1 cm precision |

## 6. Fix loop (brief Part 4)

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| F1 | Fix declaration: single worst gate, with the failing number | `docs/fix_declaration.md` | Declaration page | Done | Walls 11-53 cm short vs home C's ground truth (median 29 cm), truth outside the area interval in 6 of 6; declared before fixing (commit `520904a`) |
| F2 | Root-cause hypothesis and the evidence for it | `docs/fix_declaration.md` §2, `scripts/diag_walls.py` | Declaration page | Done | Drift smears walls into 10-40 cm bands, snap takes the inner edge; furniture counts as wall; 4 candidate rules compared offline; `--drift` checked and ruled out |
| F3 | The fix and the predicted number after it | `docs/fix_declaration.md` §3-4, §6 | Declaration page | Done | Per-room predictions met within 3 cm on LiDAR; video prediction wrong (scale bias fitted to the short LiDAR), follow-up declared and met |
| F4 | Shipped fix with before and after runs, both regenerable, and a readable diff | git tags `fixloop-before` / `fixloop-after` | Before/after numbers + diff | Done | `git diff fixloop-before fixloop-after -- src`; `scripts/lidar_summary.py`, `scripts/compare_gt_c.py`, `scripts/gt_table.py` regenerate both |
| F5 | If it falls short of the gate, the report says why | `docs/fix_declaration.md` §7 | Post-mortem section | Done | Remaining: dining short side −23 cm (unscanned wall), area intervals miss 3 of 6 (uncalibrated), B grows unverified |

## 7. Process (brief Part 5)

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| P1 | Incremental commit history | git history | `git log` | Done | 130+ small commits, each a working step |
| P2 | Every design decision defensible live, tools closed | `docs/decisions.md` | Decision log | Not started | Next after this pass |

## 8. Deliverables

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| D1 | Compliance matrix: requirement → file path → artifact → status | `COMPLIANCE.md` | This file | Done | Statuses checked against the generated reports on Oct 4-5 |
| D2 | Capture route plus device matrix | see C1, C2, C9 | `docs/capture_protocol.md`, `docs/device_matrix.md` | Done | |
| D3 | README: fresh clean machine → running on a new capture in < 15 min, one command per capture | `README.md`, `setup.sh`, `run.sh`, `docs/plain_guide.md` | Timed fresh-clone test | In progress | Quick start for non-engineers (`./setup.sh`, `./run.sh <capture>`), no Homebrew needed (ffmpeg bundled). Fresh-clone timing still to do |
| D4 | Reproduction bundle regenerates every reported number from raw inputs | `scripts/reproduce.sh` | Bundle + script | Done | LiDAR live; video/photo replay the Kaggle model cache; then `gt_table.py`, `benchmark.py` |
| D5 | Cached model outputs replay deterministically **and** the live path also runs | `src/floorplan/mvs.py`, `remote.py`, `mvs_local.py` | `outputs/kaggle_*/recon_cache`, `outputs/recon_cache_photos` | Done | Replay: cache keyed by frame pixels (`FLOORPLAN_RECON_CACHE_ONLY=1` never runs a model). Live: `--recon auto` sends every model pass of a run to Kaggle and fills the cache (k8 photos end to end: rooms within 3% of the cached run); `--recon local` runs on the laptop in small windows, one child process each, retried smaller when killed for memory (tested with a fake model: Pi3X does not fit the 16 GB laptop) |
| D6 | Benchmark report: gates at all three tiers, repeatability, head-to-head, timing | `scripts/benchmark.py` | [docs/benchmark_report.md](docs/benchmark_report.md) | Done | Generated, not hand-edited |
| D7 | Fix-loop bundle | see F1–F5 | [docs/fix_declaration.md](docs/fix_declaration.md), tags `fixloop-before` / `fixloop-after` | Done | |
| D8 | Technical report ≤ 6 pages: architecture, tiers + device matrix, drift handling, error budget, calibration, fix-loop story, known failure modes | `docs/technical_report.md` | [docs/technical_report.md](docs/technical_report.md) (+ PDF via `scripts/md_to_pdf.py`) | Done | 6 pages incl. damage (§8) and disclosure (§10); a plain-language companion for non-engineers: `docs/plain_guide.md` |
| D9 | Raw benchmark data: sensor logs, ground truth, app exports | `data/` + upload | Bundle | Not started | Same bundle as B6 (home C captures, Polycam export with the address cropped, ground truth; A and B by their own sources) |

## 9. Walk-in test

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| W1 | All three tiers ready to run cold on an unseen space, their iPhone 15+, tier chosen on the day | `src/floorplan/cli.py`, `run.sh`, `docs/capture_protocol.md` | Walk-in runbook + rehearsal on the held-back room | In progress | All three tiers run from one command; video / photo through Kaggle (needs network, ~5 min), LiDAR fully on the laptop. Runbook and rehearsal still to do |
| W2 | Runs on our laptop, in person (Cozmo answer) | `setup.sh` | Rehearsal on this Mac | In progress | Apple Silicon M4, 16 GB: LiDAR, geometry and damage (Gemini or Florence-2) run here; the reconstruction model runs on Kaggle (it does not fit 16 GB) |

## 10. Constraints

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| K1 | Handheld consumer capture only | `docs/capture_protocol.md` | Protocol | Done | iPhone only, no tripods or rigs |
| K2 | Pretrained models, datasets, APIs allowed with disclosure | `docs/technical_report.md` §10 | Disclosure section | Done | Pi3X (CC BY-NC), MapAnything (Apache 2.0), Florence-2-base (MIT, offline damage), tested DA3 / SpatialLM, ARKitScenes; Kaggle GPUs (default for video / photo); **hosted: Gemini 3.1 Pro (Vertex AI) for damage detection**, answers cached in `data/damage_cache/` |
| K3 | Runs without calling our own infrastructure | `src/floorplan/` | Code review | Done | No own servers. Hosted calls are disclosed and optional: Gemini (damage; Florence-2 on the laptop without network) and Kaggle under the user's own account (video / photo model; low-memory local run without network) |
| K4 | Weights and large binaries fetched by script, not committed | `setup.sh`, `scripts/fetch_arkitscenes.sh`, `floorplan.damage_local --fetch`, `floorplan.mvs_local --fetch` | Fetch scripts | Done | Weights from Hugging Face into its cache; datasets by script |
| K5 | Mirrors, glass, wet-look surfaces, low light covered | `docs/technical_report.md` §9 | Known-failure-modes section | Done | Described from the method; low light not measured |

## Coverage

| Status | Count |
|---|---|
| Done / met | 43 |
| Partial / partly met | 12 |
| Not met | 3 |
| In progress | 3 |
| Not started | 3 |
| **Total** | **64** |
