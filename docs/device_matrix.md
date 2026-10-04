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
| Room side, median abs. error | LiDAR: repeatability; video ±3%; photos ±8% | 5 cm | 8 cm (11 of 16 within ±3%) | 25 cm (13 of 22 within ±8%) |
| Ceiling height | ≤ 1.5 cm per room | −2.1 to +1.0 cm (3 of 4 met) | 0.3–14 cm | 1–48 cm |
| Opening width | ≤ 2 cm on ≥ 85% of openings | door 34 cm narrow; windows missed | not scored | not scored |
| Footprint (stitched) | photos ±8% | one cloud, stitched by construction | stitched on room clips; the 5-min house clip folds | not stitched |
| Repeatability, per wall | 1 cm or 0.5% | 0.4 / 4.6 cm (bedroom, 2 scans) | 1.2 cm (2 clips) | – |
| 90% interval coverage, sides / ceilings | ~90% | 91% / 100% | 92% / 100% | 80% / 88% |
| Run time per capture | (none stated) | 9–20 s on the M4 laptop | model 60–260 s on a T4 + 10–20 s geometry | model 27–75 s on a T4 + ~1 s geometry |

Photo numbers come from stills cut from home C's videos, not from the friend's own photos.

## Where the numbers come from

| Tier | Ground truth | Captures |
|---|---|---|
| LiDAR | Laser scan (ARKitScenes 421337) and tape (home C) | B: 3 videos of one room; C: whole home |
| Video | Tape (home C) | C: Camera-app walkthrough |
| Photos | Tape (home C) | C: per-room photo folders |

Dataset A has no ground truth, so it is used only for repeatability and as a check that
results are "consistent with LiDAR". One room of C is held out for the walk-in rehearsal and
is reported separately.

## Known limits (to confirm in the benchmark)

- Only one phone model (iPhone 16 Pro) is tested at the video and photo tiers; other iPhone
  15+ models should behave alike, since they use the same main camera class, but this is not
  measured.
- LiDAR range is about 5 m; larger rooms rely more on poses and drift correction.
- Mirrors, glass, dark and wet-look surfaces degrade every tier (see the technical report's
  failure modes).
