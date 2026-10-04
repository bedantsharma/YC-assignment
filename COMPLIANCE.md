# Compliance matrix

Every requirement in the brief (`Applied AI.pdf`) and in Cozmo's written answers (Oct 3),
mapped to the code that implements it, the artifact that proves it, and an honest status.

**Status values:** Not started · In progress · Done · Partial (works, misses part of the
spec or its gate; Notes say which) · Not done (deliberately cut; Notes say why).

Paths marked *(planned)* do not exist yet. Datasets A/B/C are defined in
[docs/data_plan.md](docs/data_plan.md). Last updated: Sat Oct 3, 2026.

## 1. Capture (brief Part 1)

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| C1 | Choose a capture route: own iOS app (Route 1) or stock app + protocol (Route 2) | `docs/capture_protocol.md` | The protocol page | In progress | Route 2 chosen: Stray Scanner (LiDAR), native Camera (video, photos) |
| C2 | One-page protocol a non-engineer follows: what to install, how to walk, how long, what to avoid, how to hand over files | `docs/capture_protocol.md` | The protocol | In progress | Draft covers all five points; runs ~2 pages by choice (clarity over cramming). Built from Polycam, magicplan and Apple RoomPlan guidance. To be tested on a non-engineer |
| C3 | Photo tier: 2–8 stills per room, any iPhone 15+, no depth or poses | `src/floorplan/photos.py`, `pipeline._run_photos` (`floorplan run <room folders>`) | `docs/photo_tier.md` §8: rooms from C video stills | Done (C stills only) | Rooms with ≥ 4 photos looking across the room: −7% to +1% area vs LiDAR; 2–3 photos: 25–45% small (warned). Not yet run on real photo folders. **Deliberate deviation:** protocol asks ~15 photos per room (minimum 4); pipeline accepts 2–8 with wider intervals |
| C4 | Photo tier: one folder per room → the same stitched whole-property plan | `src/floorplan/photos.py` | Per-room plan, rooms named after folders | **Partial** | Folder = room label works; **stitching fails**: joint reconstruction placed rooms 1–2 m wrong, so rooms are laid out side by side with a NOT-stitched warning (`docs/photo_tier.md` §5, §7) |
| C5 | Video tier: handheld walkthrough clip, any iPhone 15+ | `src/floorplan/video.py`, `mvs.py`, `chunks.py`, `intervals.py` (`floorplan run --tier video`) | `c_home_01` from its `rgb.mp4`: 4 of 4 rooms, 57.3 [52.2, 62.5] vs 59.8 m² LiDAR (`docs/video_scale.md`) | Done (C only) | Pi3X default (CC BY-NC, disclosed), MapAnything fallback (Apache). Camera-app clips (`docs/home_c_new_captures.md`): damage room, 60 frames, within 5 cm of LiDAR on both sides; **5-min whole-house clip fails** (windows fold rooms onto each other; broken chain links fixed, plan still wrong). Not yet run on B |
| C6 | LiDAR tier: depth, poses, intrinsics on Pro devices | `src/floorplan/capture.py`, `src/floorplan/tiers/lidar.py` *(planned)* | Plans from datasets A, B, C | In progress | Loader done for Stray Scanner and ARKitScenes (common z-up frame) |
| C7 | Same output contract from every tier | `src/floorplan/output.py` | One result type for all tiers | In progress | |
| C8 | Intervals widen honestly as sensor data thins | `src/floorplan/lidar.py` (provisional) | Calibration table per tier | In progress | LiDAR: ±1.645σ from measured surface spreads, unobserved walls 5 cm σ. Uncalibrated until Phase 6 |
| C9 | Device matrix: which tier runs on which hardware, and the accuracy each honestly delivers | `docs/device_matrix.md` | Table in technical report | In progress | Skeleton: hardware per tier done; accuracy cells TBD until the benchmark |

## 2. Output contract, per capture (brief Part 2)

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| O1 | Per-room plan with walls (dimensioned) | `src/floorplan/plan2d.py`, `rooms.py`, `lidar.py` | `rooms[].walls[]` in JSON + `plan.png` | In progress | LiDAR tier works on datasets A and B; not yet checked against ground truth |
| O2 | Ceiling height per room | `src/floorplan/levels.py`, `rooms.py` | `rooms[].ceiling_height` | In progress | Per-room floor and ceiling planes (LiDAR); `null` + warning when the ceiling was never scanned |
| O3 | Floor area per room | `src/floorplan/rooms.py`, `lidar.py` | `rooms[].floor_area` | In progress | LiDAR tier; polygon snapped to wall faces |
| O4 | Openings (doors, windows) per room | `src/floorplan/openings.py` | `rooms[].openings[]`, [docs/openings.md](docs/openings.md) | Partial | Doors and passages from gaps in wall elevations, confirmed by seeing through; windows not detected (window walls return points across the glass) |
| O5 | Stitched multi-room plan: every room placed, connected, dimensioned, correct adjacency | `src/floorplan/lidar.py` (one cloud per capture), `src/floorplan/openings.py` | `adjacency[]` + `plan.png` | In progress | LiDAR and video: rooms placed in one frame by construction; adjacency from detected doors (`c_home_01`: hall-drawing, hall-bedroom; kitchen link missed). Photo tier: not stitched (G7) |
| O6 | Stitched plan produced from **every** tier, including photos | `src/floorplan/pipeline.py` | LiDAR + video stitched (`c_home_01`); photo not | Partial | LiDAR and video: one stitched plan; photo: rooms measured but not placed |
| O7 | Per-surface damage regions with class and metric extent | `src/floorplan/damage.py` *(planned)* | `damage[]` | Not started | |
| O8 | Concealed-damage flags naming the rule that fired | `src/floorplan/damage.py` *(planned)* | `flags[].rule_id`, `flags[].rule` | Not started | |
| O9 | Scope line items keyed to surfaces | `src/floorplan/scope.py` *(planned)* | `scope[].surface_id` | Not started | |
| O10 | Confidence interval on every measurement | `src/floorplan/output.py` | Every number is `{value, lo, hi, unit}` | Done | Enforced by the output types; lo ≤ value ≤ hi checked |
| O11 | One command per capture | `src/floorplan/cli.py` | `uv run floorplan run <capture>` | Done | LiDAR (8–23 s), video (2 min per room, ~8 min for a 4-room home), photo (25–70 s) on the M4 |
| O12 | JSON output | `src/floorplan/output.py` | `outputs/<capture>/plan.json` | Done | Own format (no published schema, per Cozmo); fields in README |
| O13 | Rendered plan a homeowner would recognise (as from Polycam / magicplan) | `src/floorplan/render.py` | `outputs/<capture>/plan.png` | In progress | Dimensioned walls with intervals, room areas and ceilings; no doors or furniture symbols yet |

## 3. Benchmark composition (brief Part 2)

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| B1 | One multi-room capture: 3+ rooms plus a connector | `data/home_c/` | Dataset C whole-home capture | In progress | Friend capturing Sat; A also covers this at the LiDAR tier |
| B2 | One furnished room with staged damage spanning two classes | `data/home_c/` | Dataset C damaged room | In progress | Tape "crack" + tea-stain "water damage" |
| B3 | Same rooms at all three tiers, multi-room set included | `data/home_c/` | Dataset C | In progress | |
| B4 | At least one room captured twice at the same tier | `data/home_c/`, `data/arkitscenes/` | C damaged room ×2; B room ×3 | In progress | B downloaded |
| B5 | Laser or tape ground truth on everything | `data/gt/` | `home_c.yaml`, `arkitscenes_421337.yaml` *(planned)* | In progress | B: laser cloud prepared for an architect to measure blind in CAD (not yet sent) (`docs/laser_measurement_sheet.md`); C from friend's tape sketch |
| B6 | Raw sensor data and measurements submitted | `scripts/fetch_*`, upload bundle *(planned)* | Reproduction bundle | Not started | |

## 4. Gates (brief Part 2)

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| G1 | Opening widths ≤ 2 cm on ≥ 85% of openings; missed and phantom openings count as misses | `src/floorplan/openings.py` | [docs/openings.md](docs/openings.md) | **Not met** | Bedroom door found in both scans but 34 cm narrow (door leaf / frame in the gap); windows not detected |
| G2 | Ceiling height ≤ 1.5 cm per room | `scripts/benchmark.py` | `docs/benchmark_report.md` (ceiling table) | Partly met | LiDAR: 3 of 4 room measurements (−2.1 to +1.0 cm; the dining room misses by 0.6 cm); video 3–14 cm |
| G3 | Ceiling spread across repeat captures ≤ 1 cm; report says bias or noise | `scripts/benchmark.py` | `docs/benchmark_report.md` (repeatability table + bias/noise sentence) | Partly met | B: 0.3–0.6 cm across 3 scans (met); C bedroom 0.2 / 1.3 cm; report: LiDAR error is cm-level noise, image tiers a corrected model bias |
| G4 | Repeatability: two captures of a room agree within 1 cm or 0.5% per wall | `scripts/benchmark.py` | `docs/benchmark_report.md` (repeatability table) | **Not met** | C bedroom scans: short side 0.4 cm, long side 4.6 cm; B scans differ 3–110 cm (coverage, fix map 02b); video v1 vs v2 1.2 cm |
| G5 | Drift: report states the method used on the multi-room capture | `src/floorplan/drift.py` (`floorplan run --drift`) | [docs/drift_ablation.md](docs/drift_ablation.md) (method section) | In progress | "Poses used as-is" is an automatic fail. Built (chunked 2D ICP on walls), **off by default (user decision)**: made the `c_home_01` kitchen and A `c00a170fe1` worse; report must state method + ablation |
| G6 | Drift: ablation of stitched footprint with correction on and off | `scripts/drift_ablation.py` | [docs/drift_ablation.md](docs/drift_ablation.md) (table; no figure yet) | Partial | Mixed: damage-room repeat scans 21 → 1 cm on the short side; A `c00a170fe1` walls lose support |
| G7 | Photo tier: one stitched plan, correct adjacency, no overlaps, footprint ±8%, calibrated intervals | `scripts/score_photos.py` (vs LiDAR) | `docs/photo_tier.md` §8 | **Not met** | No stitch (rooms side by side, no adjacency); footprint 45.0 vs 59.8 m² on `c_home_01` protocol stills (hall and room2 had 2–3 photos) |
| G8 | Photo tier: wall lengths ±8% with calibrated intervals | `scripts/score_photos.py` (vs LiDAR); `scripts/benchmark.py` *(planned)* | `docs/photo_tier.md` §8 | Partly met | Area within ±8% for rooms with ≥ 4 good photos (5 of 6), not for 2–3 photos; wall lengths not compared yet; intervals contain LiDAR in 8 of 11 rooms, uncalibrated; vs LiDAR, not tape |
| G9 | Video tier: wall lengths ±3% | `scripts/video_scale.py` (vs LiDAR); `scripts/benchmark.py` *(planned)* | Held-out table in `docs/video_scale.md` | Not met | After scale correction, held-out rooms: ceilings within 3.3% (meets), √area +0.2 / +2.6 / −8.5%, longest wall up to −15.5% (outline differences); vs LiDAR, not tape |
| G10 | Calibration scored at every tier; no confident garbage on thin input | `scripts/calibration.py` | `docs/benchmark_report.md` (calibration table) | In progress | 90% coverage vs home C: LiDAR sides 10/11, ceilings 4/4; video and photo in the report; photo rooms with partial coverage are the risk |

## 5. Head-to-head (brief Part 3)

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| H1 | Our LiDAR-tier output vs a consumer app on 2 benchmark rooms | `scripts/gt_table.py` (head-to-head section) | `docs/gt_comparison.md` | Done | Polycam (RoomPlan) on dataset C, 4 rooms vs the architect's drawing |
| H2 | Name the app and version; submit its export | `data/home_c/polycam/` | Polycam 2D plan | In progress | Polycam (Apple RoomPlan) screenshots in `data/home_c/polycam/` (gitignored: address), numbers in `data/gt/home_c_polycam.json`; app version not recorded yet. Our LiDAR is 6-57 cm smaller on every dimension (`docs/home_c_new_captures.md`); tape decides |
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
| P1 | Incremental commit history | git history | `git log` | In progress | Committing at every working step |
| P2 | Every design decision defensible live, tools closed | `docs/decisions.md` *(planned)* | Decision log | Not started | |

## 8. Deliverables

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| D1 | Compliance matrix: requirement → file path → artifact → status | `COMPLIANCE.md` | This file | In progress | Updated as work lands |
| D2 | Capture route plus device matrix | see C1, C2, C9 | | Not started | |
| D3 | README: fresh clean machine → running on a new capture in < 15 min, one command per capture | `README.md` | Timed fresh-clone test | In progress | |
| D4 | Reproduction bundle regenerates every reported number from raw inputs | `scripts/reproduce.sh` | Bundle + script | Done | LiDAR live; video/photo replay the Kaggle model cache; then `gt_table.py`, `benchmark.py` |
| D5 | Cached model outputs replay deterministically **and** the live path also runs | `src/floorplan/mvs.py` (`FLOORPLAN_RECON_CACHE`, `_ONLY`) | `outputs/kaggle_*/recon_cache` + Kaggle logs | In progress | Replay verified (cache keyed by frame pixels); live path runs on Kaggle T4; on the 16 GB laptop live runs hit memory pressure |
| D6 | Benchmark report: gates at all three tiers, repeatability, head-to-head, timing | `scripts/benchmark.py` | [docs/benchmark_report.md](docs/benchmark_report.md) | Done | Generated, not hand-edited |
| D7 | Fix-loop bundle | see F1–F5 | [docs/fix_declaration.md](docs/fix_declaration.md), tags `fixloop-before` / `fixloop-after` | Done | |
| D8 | Technical report ≤ 6 pages: architecture, tiers + device matrix, drift handling, error budget, calibration, fix-loop story, known failure modes | `docs/technical_report.md` | [docs/technical_report.md](docs/technical_report.md) | Done | ~2,000 words |
| D9 | Raw benchmark data: sensor logs, ground truth, app exports | `data/` + upload | Bundle | Not started | |

## 9. Walk-in test

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| W1 | All three tiers ready to run cold on an unseen space, their iPhone 15+, tier chosen on the day | `src/floorplan/cli.py` *(planned)* | Held-out rehearsal on dataset C | Not started | |
| W2 | Runs on our laptop, in person (Cozmo answer) | | Rehearsal on this Mac | Not started | Apple Silicon; no GPU assumptions |

## 10. Constraints

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| K1 | Handheld consumer capture only | `docs/capture_protocol.md` | Protocol | In progress | iPhone only, no tripods or rigs |
| K2 | Pretrained models, datasets, APIs allowed with disclosure | `docs/technical_report.md` §9 | Disclosure section | Done | Pi3X (CC BY-NC), MapAnything (Apache 2.0), tested DA3 / SpatialLM, ARKitScenes, Kaggle compute; no hosted API |
| K3 | Runs without calling our own infrastructure | `src/floorplan/` | Code review | In progress | Hosted APIs allowed by Cozmo (Oct 3); disclose any use, keep a local fallback |
| K4 | Weights and large binaries fetched by script, not committed | `scripts/fetch_*` | Fetch scripts | In progress | `scripts/fetch_arkitscenes.sh` |
| K5 | Mirrors, glass, wet-look surfaces, low light covered | `docs/technical_report.md` §8 | Known-failure-modes section | Done | Described from the method; low light not measured |

## Coverage

| Status | Count |
|---|---|
| Done | 2 |
| In progress | 24 |
| Partial | 0 |
| Not started | 38 |
| Not done | 0 |
| **Total** | **64** |
