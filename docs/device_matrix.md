# Device matrix

Which capture tier runs on which hardware, and the accuracy each tier honestly delivers.
Required by the brief (Part 1 and deliverables 2 and 7). How to capture each tier:
[capture_protocol.md](capture_protocol.md).

Accuracy numbers are copied from the benchmark report, never estimated by hand.

## Tiers by hardware

| Tier | Runs on | Capture app | Input the pipeline reads | Tested on |
|---|---|---|---|---|
| LiDAR | iPhone 12 Pro / Pro Max or newer Pro model; iPad Pro (2020 or newer) | Stray Scanner | depth, confidence, poses, intrinsics (+ RGB video) | Cozmo captures (dataset A, device not stated); iPhone 16 Pro (dataset C); ARKitScenes iPad Pro (dataset B) |
| Video | Any iPhone 15 or newer, Pro or not | Native Camera app, 1x lens | RGB video only | iPhone 16 Pro (dataset C) |
| Photos | Any iPhone 15 or newer, Pro or not | Native Camera app, 1x lens | RGB stills only, one folder per room | iPhone 16 Pro (dataset C) |

A non-Pro iPhone has no LiDAR sensor, so it gets the video or photo tier. A Pro device can
run all three. The video and photo tiers ignore depth and poses even when a LiDAR recording
provides them (isolation rule, [data_plan.md](data_plan.md)), so their numbers reflect what a
non-Pro phone would get.

## Accuracy by tier

Home C against its ground truth (architect's drawing, tape), copied from
[benchmark_report.md](benchmark_report.md) (`uv run scripts/benchmark.py`). Gates are from
the brief.

| Measurement | Gate | LiDAR | Video | Photos |
|---|---|---|---|---|
| Room side, median abs. error | LiDAR: repeatability; video ±3%; photos ±8% | 5 cm | 8 cm (11 of 16 within ±3%) | 19 cm (29 of 40 within ±8%) |
| Ceiling height | ≤ 1.5 cm per room | −2.1 to +1.0 cm (3 of 4 met) | 0.3–14 cm | 1–48 cm |
| Opening width | ≤ 2 cm on ≥ 85% of openings | door 34 cm narrow; windows missed | not scored | not scored |
| Footprint (stitched) | photos ±8% | one cloud, stitched by construction | stitched on room clips; the 5-min house clip folds | not stitched |
| Repeatability, per wall | 1 cm or 0.5% | 0.4 / 4.6 cm (bedroom, 2 scans) | 1.2 cm (2 clips) | – |
| 90% interval coverage, sides / ceilings | ~90% | 91% / 100% | 92% / 100% | 80% / 88% |
| Run time per capture | (none stated) | 7–22 s on the M4 laptop | model + geometry 62–203 s on a T4; laptop replay 12–20 s | model 27–75 s on a T4 + ~1 s geometry |

Photo numbers combine the friend's real photos (all, 8 and 5 per room) and stills cut from
home C's videos.

## Where the numbers come from

| Tier | Ground truth | Captures |
|---|---|---|
| LiDAR | Architect's drawing and tape (home C); B's laser-scan measurements for repeatability only (approximate) | B: 3 scans of one room; C: whole home + 2 scans of the damage room |
| Video | Architect's drawing and tape (home C) | C: Camera-app clips of the damage room and the LiDAR recording's own RGB video |
| Photos | Architect's drawing and tape (home C) | C: the friend's per-room photo folders and stills cut from the videos |

Dataset A has no ground truth, so it is used only for development, the drift ablation and as
a check that results are "consistent with LiDAR". Every room of C is in the benchmark; the
walk-in rehearsal is on a room none of our data has seen ([walkin_runbook.md](walkin_runbook.md)).

## Known limits (to confirm in the benchmark)

- Only one phone model (iPhone 16 Pro) is tested at the video and photo tiers; other iPhone
  15+ models should behave alike, since they use the same main camera class, but this is not
  measured.
- LiDAR range is about 5 m; larger rooms rely more on poses and drift correction.
- Mirrors, glass, dark and wet-look surfaces degrade every tier (see the technical report's
  failure modes).
