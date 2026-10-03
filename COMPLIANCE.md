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
| C3 | Photo tier: 2–8 stills per room, any iPhone 15+, no depth or poses | `src/floorplan/tiers/photo.py` *(planned)* | Plan from dataset C photo folders | Not started | **Deliberate deviation:** protocol asks ~15 photos per room (minimum 4) for a reliable first result; pipeline must still accept 2–8, with wider intervals. Accuracy vs photo count to be reported |
| C4 | Photo tier: one folder per room → the same stitched whole-property plan | `src/floorplan/tiers/photo.py` *(planned)* | Stitched plan from C photo folders | Not started | Protocol requires one photo through each doorway to link rooms |
| C5 | Video tier: handheld walkthrough clip, any iPhone 15+ | `src/floorplan/tiers/video.py` *(planned)* | Plan from C native video | Not started | |
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
| O4 | Openings (doors, windows) per room | `src/floorplan/geometry/openings.py` *(planned)* | `rooms[].openings[]` | Not started | |
| O5 | Stitched multi-room plan: every room placed, connected, dimensioned, correct adjacency | `src/floorplan/geometry/stitch.py` *(planned)* | `property.adjacency` + stitched plan image | Not started | |
| O6 | Stitched plan produced from **every** tier, including photos | `src/floorplan/tiers/` *(planned)* | Stitched plans for A/C at each tier | Not started | |
| O7 | Per-surface damage regions with class and metric extent | `src/floorplan/damage.py` *(planned)* | `damage[]` | Not started | |
| O8 | Concealed-damage flags naming the rule that fired | `src/floorplan/damage.py` *(planned)* | `flags[].rule_id`, `flags[].rule` | Not started | |
| O9 | Scope line items keyed to surfaces | `src/floorplan/scope.py` *(planned)* | `scope[].surface_id` | Not started | |
| O10 | Confidence interval on every measurement | `src/floorplan/output.py` | Every number is `{value, lo, hi, unit}` | Done | Enforced by the output types; lo ≤ value ≤ hi checked |
| O11 | One command per capture | `src/floorplan/cli.py` | `uv run floorplan run <capture>` | In progress | LiDAR tier runs end to end (plan.json + plan.png, 8–23 s); video and photo tiers still stubs |
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
| G1 | Opening widths ≤ 2 cm on ≥ 85% of openings; missed and phantom openings count as misses | `scripts/benchmark.py` *(planned)* | Openings table in benchmark report | Not started | |
| G2 | Ceiling height ≤ 1.5 cm per room | `scripts/benchmark.py` *(planned)* | Ceiling table | Not started | |
| G3 | Ceiling spread across repeat captures ≤ 1 cm; report says bias or noise | `scripts/benchmark.py` *(planned)* | Ceiling table + report sentence | Not started | |
| G4 | Repeatability: two captures of a room agree within 1 cm or 0.5% per wall | `scripts/benchmark.py` *(planned)* | Repeatability table | Not started | Datasets A (×3), B (×3), C (×2) |
| G5 | Drift: report states the method used on the multi-room capture | `src/floorplan/drift.py` (`floorplan run --drift`) | [docs/drift_ablation.md](docs/drift_ablation.md) (method section) | In progress | "Poses used as-is" is an automatic fail. Built (chunked 2D ICP on walls), **off by default (user decision)**: made the `c_home_01` kitchen and A `c00a170fe1` worse; report must state method + ablation |
| G6 | Drift: ablation of stitched footprint with correction on and off | `scripts/drift_ablation.py` | [docs/drift_ablation.md](docs/drift_ablation.md) (table; no figure yet) | Partial | Mixed: damage-room repeat scans 21 → 1 cm on the short side; A `c00a170fe1` walls lose support |
| G7 | Photo tier: one stitched plan, correct adjacency, no overlaps, footprint ±8%, calibrated intervals | `scripts/benchmark.py` *(planned)* | Photo-stitch row | Not started | |
| G8 | Photo tier: wall lengths ±8% with calibrated intervals | `scripts/benchmark.py` *(planned)* | Photo-tier table | Not started | |
| G9 | Video tier: wall lengths ±3% | `scripts/benchmark.py` *(planned)* | Video-tier table | Not started | |
| G10 | Calibration scored at every tier; no confident garbage on thin input | `scripts/calibration.py` *(planned)* | Coverage table per tier | Not started | Caps total score if violated |

## 5. Head-to-head (brief Part 3)

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| H1 | Our LiDAR-tier output vs a consumer app on 2 benchmark rooms | `scripts/head_to_head.py` *(planned)* | Comparison table | Not started | Polycam free tier, on dataset C (Cozmo confirmed: compare on our own data) |
| H2 | Name the app and version; submit its export | `data/home_c/polycam/` | Polycam export | In progress | Friend exporting Sat |
| H3 | One table, our error and theirs, dimension by dimension; beat or tie on ≥ 70% | `scripts/head_to_head.py` *(planned)* | Table in benchmark report | Not started | |

## 6. Fix loop (brief Part 4)

| ID | Requirement | File path | Artifact | Status | Notes |
|---|---|---|---|---|---|
| F1 | Fix declaration: single worst gate, with the failing number | `docs/fix_loop.md` | Declaration page | In progress | Fix 01 (room segmentation, 2/4 rooms found) declared before fixing; the submitted entry is picked in Phase 6 (worst brief gate) |
| F2 | Root-cause hypothesis and the evidence for it | `docs/fix_loop.md` | Declaration page | In progress | Fix 01: three causes traced stage by stage; first hypothesis recorded as wrong |
| F3 | The fix and the predicted number after it | `docs/fix_loop.md` | Declaration page | In progress | Fix 01: 4/4 and hall IoU predicted and met; kitchen area predicted wrong, explained |
| F4 | Shipped fix with before and after runs, both regenerable, and a readable diff | git tags `fix01-before` / `fix01-after` | Before/after numbers + diff | In progress | Fix 01 shipped: `git diff fix01-before fix01-after`; `scripts/lidar_summary.py` + `scripts/score_rooms.py` regenerate both |
| F5 | If it falls short of the gate, the report says why | `docs/fix_declaration.md` *(planned)* | Post-mortem section | Not started | |

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
| D4 | Reproduction bundle regenerates every reported number from raw inputs | `scripts/reproduce.sh` *(planned)* | Bundle + script | Not started | |
| D5 | Cached model outputs replay deterministically **and** the live path also runs | `src/floorplan/cache.py` *(planned)* | Cache + live run log | Not started | The walk-in test runs live |
| D6 | Benchmark report: gates at all three tiers, repeatability, head-to-head, timing | `docs/benchmark_report.md` *(planned)* | Report | Not started | |
| D7 | Fix-loop bundle | see F1–F5 | | Not started | |
| D8 | Technical report ≤ 6 pages: architecture, tiers + device matrix, drift handling, error budget, calibration, fix-loop story, known failure modes | `docs/technical_report.md` *(planned)* | Report (PDF) | Not started | |
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
| K2 | Pretrained models, datasets, APIs allowed with disclosure | `docs/technical_report.md` *(planned)* | Disclosure section | In progress | ARKitScenes disclosed in data plan |
| K3 | Runs without calling our own infrastructure | `src/floorplan/` | Code review | In progress | Hosted APIs allowed by Cozmo (Oct 3); disclose any use, keep a local fallback |
| K4 | Weights and large binaries fetched by script, not committed | `scripts/fetch_*` | Fetch scripts | In progress | `scripts/fetch_arkitscenes.sh` |
| K5 | Mirrors, glass, wet-look surfaces, low light covered | `docs/technical_report.md` *(planned)* | Known-failure-modes section | Not started | |

## Coverage

| Status | Count |
|---|---|
| Done | 2 |
| In progress | 24 |
| Partial | 0 |
| Not started | 38 |
| Not done | 0 |
| **Total** | **64** |
