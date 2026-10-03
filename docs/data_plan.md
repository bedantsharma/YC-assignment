# Data plan: which data feeds which experiment

Three data sources, each covering gaps the others leave. Scoring weights refer to
[requirements.md](../requirements.md).

## Datasets

| ID | Source | Device | What it contains | Ground truth | Limits |
|---|---|---|---|---|---|
| **A** | Cozmo's 3 Stray Scanner captures (`data/raw/`) | iPhone Pro (unknown model) | One multi-room apartment walked 3 times: LiDAR depth, confidence, poses, intrinsics, RGB video, IMU | None | No absolute accuracy; ceiling visible in only one capture |
| **B** | ARKitScenes venue 421337 (`data/arkitscenes/`) | 2020 iPad Pro | One room captured 3 times: LiDAR depth, confidence, poses, intrinsics, RGB video | Faro laser scan (mm-accurate point cloud) | Single room; iPad, not iPhone; ground truth is a point cloud, not measured dimensions |
| **C** | Friend's home ([checklist](friend_capture_checklist.md)) | iPhone 16 Pro | Multi-room home at all three tiers, staged damage, repeat captures, Polycam export | Tape measurements | Tape precision ~0.5 cm; depends on the friend's time |

### How B's ground truth is used

The laser point cloud is not a list of wall lengths, and measuring it with our own wall
detector would grade our code with itself. Instead we measure B's walls, ceiling height, and
openings **once, by hand**, from the laser cloud (picking corner points in a viewer), and
store them in `data/gt/arkitscenes_421337.yaml`. That file is then ground truth like any tape
sheet.

In practice the measuring is done by an architect in her own CAD software (ReCap / Revit,
CloudCompare), working **blind** (she does not see our output first).
`scripts/prepare_laser_gt.py` crops the 1.9 GB station scan to the room and thins it to
one real point per 5 mm (43 M → 2.7 M points; E57, LAS, PLY);
[laser_measurement_sheet.md](laser_measurement_sheet.md) says what to measure and how
(inside faces at 1.1 m, ceiling at four points, clear opening widths).

### Dataset C layout and what has arrived

```
data/home_c/
  lidar/c_home_NN/   one Stray Scanner recording per folder (same files as dataset A)
  video/             native Camera-app videos, original files
  photos/<room>/     one folder per room, original photos (+ doorway shots)
  polycam/           Polycam export + floor-plan screenshots (head-to-head)
  notes/             photo of the tape-measured sketch
data/gt/home_c.yaml  tape measurements, transcribed from the sketch (committed)
```

| Item from the checklist | Status (Sat Oct 3, ~17:45 IST) |
|---|---|
| LiDAR whole-home walk | **Received:** `lidar/c_home_01` (167 s, 9,995 frames, 1920x1440 RGB, 256x192 depth). Runs: 4 rooms, ~56 m², ceilings ~3.3–3.5 m (unverified) |
| LiDAR damaged room x2 | **Received:** `lidar/c_damage_01` (62 s, 3,701 frames) and `lidar/c_damage_02` (56 s, 3,380 frames), same L-shaped room. Staged damage: one hole in one wall, about 3 in (~7.6 cm) wide per the friend (not tape-measured; which wall not yet known) |
| Camera-app video (whole home, damaged room x2) | Not in hand, not currently expected → fallback: C's `rgb.mp4` |
| Photo folders per room + doorway shots | Not in hand, not currently expected → fallback: stills sampled from video |
| Polycam export (2 rooms) | Not in hand, not currently expected → head-to-head at risk |
| Tape sketch (walls, ceilings, openings, damage, adjacency) | Not in hand, not currently expected: **no ground truth for C**; B's laser is the only absolute reference |

Folder names are descriptive; the original Stray Scanner ids (all recorded Oct 3, one
session) are `c_home_01` = `bb6820aff7` (14:48), `c_damage_01` = `2a45337da0` (14:50),
`c_damage_02` = `82720d462e` (14:52). The held-out room is chosen when the sketch arrives; nothing has been
tuned on C so far.

## Experiments

| # | Experiment | Data | Measures / gate | Score it feeds |
|---|---|---|---|---|
| E1 | Build the LiDAR geometry backend (floor, ceiling, walls, rooms) | **A** (develop), B | Plans look right; code runs on every capture | Walk-in 30% |
| E2 | LiDAR absolute accuracy | **B** (laser), **C** (tape) | Wall length, ceiling height ≤ 1.5 cm, floor area error | Benchmark 15% |
| E3 | Repeatability | **B** (3 captures of one room), **A** (3 of one apartment), **C** (damaged room ×2 per tier) | Same wall within 1 cm or 0.5%; ceiling spread ≤ 1 cm; bias vs noise | Benchmark 15% |
| E4 | Drift correction + on/off ablation | **A** (100 m multi-room walk), **C** whole-home scan | Stitched footprint with correction on vs off | Benchmark 15% (auto-fail without it) |
| E5 | Multi-room stitching and adjacency | **A** (LiDAR), **C** (all tiers) | Correct adjacency, no overlapping rooms | Walk-in, Benchmark |
| E6 | Video tier | **Development / ablation:** A and C Stray `rgb.mp4` vs the LiDAR result from the same recording; B `.mov` vs laser. **Benchmark:** C native Camera video vs tape | Wall lengths ±3%, calibrated intervals; depth-removal ablation | Benchmark, Walk-in |
| E7 | Photo tier | Stills from A and B videos (development); **C** real per-room photo folders (evaluation) | Wall lengths ±8%; stitched footprint ±8%, no overlaps | Benchmark, Walk-in |
| E8 | Interval calibration | Every capture with ground truth: **B**, **C** | Share of true values inside our 90% intervals, per tier | Avoids the "confident garbage" score cap |
| E9 | Openings | **C** (tape widths for every door and window), **B** (laser) | ≤ 2 cm on ≥ 85%, missed/phantom counted | Benchmark, Walk-in |
| E10 | Damage, concealed-damage flags, scope | **C** staged-damage room | Both damage classes found, metric extent vs tape, flags name their rule | Compliance, Walk-in |
| E11 | Head-to-head vs Polycam | **C** (our LiDAR result vs Polycam on the same 2 rooms, both vs tape) | Beat or tie on ≥ 70% of dimensions | Head-to-head 10% |
| E12 | Fix loop | Whichever dataset shows our worst gate (likely B or C) | Before → after on that gate | Fix loop 25% |
| E13 | Walk-in rehearsal | **One room of C held out** from all tuning | Cold run, scored against its tape numbers | Rehearsal for the 30% |

## Why this combination works

- **A** is the cleanest multi-room LiDAR data, so the geometry code is built and debugged on
  it. Its `rgb.mp4` is recorded alongside the depth, so running the video tier on it (with
  depth ignored) and comparing to the LiDAR result from the same capture isolates exactly
  what is lost when depth is removed.
- **B** is the only source of mm-accurate ground truth and gives three captures of one room,
  covering the strict LiDAR gates (ceiling height, repeatability) and the error budget. It is
  available now, before the friend's data arrives.
- **C** is what Cozmo asked for ("your own captures with real truth measurements"). It is
  the only source covering photo-folder stitching, damage, openings with measured widths,
  and the Polycam comparison, and it uses the same phone class as the walk-in test.

## Video from LiDAR recordings: development only

Stray Scanner (and ARKitScenes) record a video alongside the depth. It is useful, but it is
an easier input than the walk-in video tier, which is a Camera-app clip from any iPhone 15:

| | Stray / ARKitScenes video | Camera-app video (walk-in) |
|---|---|---|
| Lens intrinsics | Known exactly, per frame | Unknown, must be estimated |
| Stabilisation | None, raw frames | On by default: frames cropped and warped |
| Format | Fixed resolution, plain H.264 | 4K/1080p, often HDR, rotation flags, variable frame rate |
| Exposure | Steady | Auto-exposure and focus changes |

**Rules:**

1. **Isolation.** When the video or photo tier runs on a LiDAR recording, it uses **only the
   RGB video**. It never reads depth, confidence, poses, stored intrinsics or IMU from that
   recording. This is enforced in code (the tier loaders only receive the video path), not by
   convention.
2. **Benchmark numbers come from Camera-app video only.** Video-tier gate results in the
   benchmark report use dataset C's native Camera video. Stray/ARKitScenes video is used for
   development and for the depth-removal ablation (same frames with and without depth),
   and is labelled as such wherever it appears.
3. **Ground-truth poses are for diagnosis only.** The recorded poses may be used offline to
   check our estimated camera trajectory, never as input to the video or photo tier.

## Avoiding overfitting

Develop and tune on A and B. Evaluate on C. Keep one room of C completely untouched until
the walk-in rehearsal, so at least one result shows how the pipeline does on a space it has
never seen, which is exactly what the walk-in test measures.

## If the friend's data is late or incomplete

| Missing from C | Fallback | Cost |
|---|---|---|
| Tape measurements | Use B (laser) as the only absolute ground truth | Photo/video gates measured on one room only |
| Photo folders | Stills sampled from C's or A's videos | Not a real "2–8 photos" test; stated in report |
| Camera-app video | C's Stray `rgb.mp4` as the video-tier stand-in | Easier input than the walk-in; labelled as an approximation in the report |
| Polycam export | Head-to-head marked as not done | 10% at risk |
| Staged damage | Damage pipeline demonstrated on A's frames without metrics | Damage gate unscored |
