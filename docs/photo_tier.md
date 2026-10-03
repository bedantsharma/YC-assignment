# Photo tier: model research, bake-off and results

Sun Oct 4, night (user asleep; worked through unattended). Brief input contract: 2–8 stills
per room, one folder per room, no depth or poses; target ±8% on wall lengths.

## 1. Research (Firecrawl, Sun ~01:30)

Question: which model reconstructs a metric room from a **few, wide-baseline, unposed**
photos? The video bake-off ([model_research.md](model_research.md)) tested dense frames.

- **SpatialBench** ([arXiv 2605.27367](https://arxiv.org/html/2605.27367v1), NeurIPS 2026)
  evaluates 41 model variants under four view densities, including a *Sparse* regime
  (a few frames, large baselines). Sparse, depth AbsRel ↓ / pose AUC@30 ↑:

  | Model | AbsRel | AUC@30 | Weights |
  |---|---|---|---|
  | DA-Next | 0.050 | 0.727 | **not released** (repo TODO: "Release DA-Next Checkpoint"; HF repo empty) |
  | VGGT-Ω | 0.077 | 0.703 | gated on request; metric scale not stated |
  | **Pi3X** | 0.084 | 0.627 | CC BY-NC, metric (approx.) — already our video model |
  | AMB3R | 0.088 | 0.619 | – |
  | DA3-Giant | 0.095 | 0.699 | CC BY-NC (nested: metric) |
  | VGGT | 0.105 | 0.585 | up to scale |
  | MapAnything | 0.153 | 0.446 | Apache 2.0, metric |

  The paper's own reading: in the sparse regime, full-attention models (DA3-Giant, π³)
  set the accuracy upper bound.
- **PLANA3R** (NeurIPS 2025): metric planar indoor reconstruction, but from **two** views
  only: does not fit 2–8 photos per room.
- Conclusion: among models we can run, **Pi3X** is the strongest sparse-view model with
  metric output; DA3-nested is the other candidate; MapAnything stays as the Apache
  fallback. All three were compared on our data (below).

## 2. Test photos (simulated)

The friend sent no photo folders, so stills are taken from C's videos
(`uv run scripts/make_photo_sets.py c_home_01 c_damage_01 c_damage_02 --k 8`): per room,
the room's video time split into 8 slots and the sharpest frame of each slot kept (like a
person taking 8 photos while walking round). The room of each frame comes from the user's
hand-drawn room rectangles and the recording's camera position: this builds the test
input only; the photo tier sees images and folder names, nothing else. `--k 4` sets are
every other photo. Contact sheet: `outputs/photos_sim_c_home_01.png`.

Limits: video stills are sharper-than-average frames but still video (motion, 1920×1440,
same exposure), and a person would frame photos deliberately (corners, doorways).

Second selection, `--protocol` (folders `k8p`): like a person following
[capture_protocol.md](capture_protocol.md): sharp, level frames taken away from the room's
middle and facing into it, headings spread, no near-duplicates. The walk offers 2–7 such
views per room (hall 3, kitchen 7, room1 4, room2 2; damage room 7 and 5). Contact sheets:
`outputs/photos_sim_*_protocol.png`.

## 3. Bake-off round 2 (Kaggle T4, `kaggle/photo_bakeoff`)

Same photo folders through each model (8 or 4 per room, time-slot selection), scored with
`uv run scripts/score_photos.py --dir outputs/photo_bakeoff` (raw clouds, no correction).

| Recording | Model | Photos | Camera error | Rooms (LiDAR) | √area ratio | Ceiling ratio |
|---|---|---|---|---|---|---|
| c_damage_01 | **Pi3X** | 8 | 7 cm | 1 (1) | 0.902 | 0.945 |
| c_damage_01 | MapAnything | 8 | 22 cm | 1 (1) | 0.910 | 1.048 |
| c_damage_02 | **Pi3X** | 8 | 5 cm | 1 (1) | 0.894 | 0.928 |
| c_damage_02 | MapAnything | 8 | 22 cm | 1 (1) | 0.983 | 1.040 |
| c_home_01 | **Pi3X** | 32 | 2.0 m | **4 (4)** | 0.891 (total) | 0.926 |
| c_home_01 | MapAnything | 32 | 0.9 m | 3 (4) | 0.847 (total) | 1.056 |
| any | any | 4 per room | – | rooms found but 0.50–0.73 | | |
| any | DA3-nested | 8 | – | **out of memory** (T4, 16 GB); 4 photos ran at 10.5 GB | | |

- **Pi3X chosen** (same as video): best cameras on single rooms (5–7 cm), only model to
  find all four rooms of the home, ceilings closest. MapAnything stays the Apache fallback.
- **DA3-nested** now installs (the missing `addict` was the round-1 failure) but cannot
  hold 8 photos at 504 px on a 16 GB GPU, so it cannot run on the 16 GB M4 either.
- **4 photos per room** is too few for this backend: rooms are found but come out 27–50%
  small (√area), because much of each room is never seen.

## 4. Diagnosis: why 8 photos first gave no room

The first local run (8 photos of `c_damage_01`) gave "no rooms found: no enclosed free
space". Masks (`outputs/photo_eval/damage01_masks.png`): in-room enclosure 0.4–0.8 against
the LiDAR backend's 0.75, because photos see each wall only in parts. Closing wall gaps
along the plan axes (0.6–2.0 m) found nothing, since the gaps were not collinear (the
room's notch): prediction wrong, not shipped. Accepting rooms at **0.5** for the photo
tier (LiDAR and video keep 0.75) gave one room, unobserved walls dotted.

A scorer bug also hid rooms: it levelled clouds with a 3D camera fit to ARKit, which tilts
the floor when there are only a few cameras at one height (8 photos of `c_damage_02`: no
room after the 3D fit, one room when levelled from wall normals as the tier does). Both
scorers now level as the tier does and pair rooms in the floor plane only.

## 5. Whole home vs single rooms

Pi3X, local (M4) and Kaggle, `scripts/photo_eval.py` + `score_photos.py`:

| Case | Photos | Camera error | Result vs LiDAR |
|---|---|---|---|
| Damage room, protocol-style | 7 / 5 | 6 / 3 cm | √area **0.954 / 0.970**, ceiling 0.932 / 0.903 |
| Damage room, time-slot | 8 / 8 | 7 / 5 cm | √area 0.902–0.908 / 0.889–0.894, ceiling 0.924–0.948 |
| Home rooms one at a time, protocol | 2–7 | 17–35 cm | √area 0.66–0.90 (kitchen, 7 photos: 0.895) |
| Whole home jointly, 32 photos, one pass (M4) | 32 | 2.2 m | 4 rooms, 51 vs 59.8 m²; per room 0.84–1.30 |
| Whole home jointly, 32 photos, chained (M4) | 32 | 1.9 m | 4 rooms, 60.5 m²; scale vs ARKit 0.70 |
| Whole home jointly, 16 protocol photos | 16 | 1.2 m | 3 of 4 rooms, 42.2 m² |

1. **Single rooms with ≥ 5 good photos work**: within 3–5% on √area before correction.
2. **Few photos → rooms too small**: 2–4 photos leave parts of the room unseen.
3. **The whole-home stitch is the weak part**: camera errors of 1–2 m in every joint run;
   rooms are found but mis-sized and mis-placed relative to each other. Chaining windows
   made it worse (scale 0.70), so up to 32 photos now go through **one pass** (fits the
   M4: 109 s, 11.4 GB).

## 6. A backend instability, found and fixed for photos

Scoring the same 7-photo cloud gave 8.2 m² in the tier and 11.9 m² in the scorer. Turning
the cloud in the floor plane showed why: **7.3 or 11.1 m² depending on its yaw** (150–315°
vs 330–135°). The plan backend's *observed* mask fills unseen floor only when it is fully
surrounded by seen cells; with sparse photos the floor is mostly unseen, and one one-cell
gap in the ring decides whether 3 m² is filled. (LiDAR clouds are dense, so the 9 LiDAR
captures are not affected in practice; still worth noting.)

Fix (photo tier only): **line-of-sight carving** (`plan2d.carved_mask`, `Sightlines`): the
space between a camera and every point it saw is free and observed. Same cloud: 10.9 vs
11.1 m² at the two yaws. With carving, rooms measured from one folder each (raw, before
correction):

| Room (protocol photos) | Photos | √area vs LiDAR, before → after carving |
|---|---|---|
| Damage room scan 1 / 2 | 7 / 5 | 0.954 / 0.970 (unchanged) |
| Home room1 (= damage room) | 4 | 0.72 → **0.96** |
| Home kitchen | 7 | 0.90 → **0.94** |
| Home room2 | 2 | 0.68 → 0.84 |
| Home hall | 3 | 0.66 → 0.72 |

## 7. Design shipped

`floorplan run <folder of room folders>` (`src/floorplan/photos.py`, pipeline `_run_photos`):

1. Photos loaded upright (EXIF), HEIC supported, long side 960 px.
2. **Each folder reconstructed on its own** (Pi3X, one pass up to 32 photos; chained
   windows above), levelled from wall normals, scale corrected with the photo bias
   (horizontal ×1.037, vertical ×1.075), plan built with enclosure 0.5 and carving.
3. The room its photos were taken from (most cameras inside) is kept and named after the
   folder; floor seen through doorways is dropped, with a warning.
4. Rooms are **laid out side by side, not stitched**, with an explicit warning: joint
   reconstruction (all folders in one pass) placed rooms 1–2 m wrong in every run (§5).
   This is the roadmap's cut line ("document the photo stitch as failing").
5. Intervals: 10% horizontal, 3% vertical (1σ) + 5 cm, in quadrature with surface spread.
   Folders with fewer than 5 photos get a warning.

## 8. Results (full pipeline, `outputs/photo_runs/`)

LiDAR of the same recording as reference (not ground truth). Areas in m², ceilings in m.

| Input | Room | Photo tier [90% interval] | LiDAR | Area error |
|---|---|---|---|---|
| c_damage_01, protocol | room (7) | 12.2 [8.1, 16.3], ceiling 3.37 | 13.13, 3.36 | −7% |
| c_damage_02, protocol | room (5) | 12.6 [8.4, 16.8], ceiling 3.25 | 12.44, 3.35 | +1% |
| c_damage_01, time-slot | room (8) | 13.2 [8.8, 17.5], ceiling 3.43 | 13.13, 3.36 | 0% |
| c_damage_02, time-slot | room (8) | 11.2 [7.4, 15.0], ceiling 3.33 | 12.44, 3.35 | −10% |
| c_home_01, protocol | kitchen (7) | 7.5 [5.0, 10.0], ceiling 3.20 | 7.8, 3.36 | −4% |
| | room1 (4) | 13.1 [8.8, 17.5], ceiling 3.33 | 13.3, 3.36 | −1% |
| | room2 (2) | 11.2 [6.2, 14.9], ceiling 3.09 | 14.9, 3.17 | −25% |
| | hall (3) | 13.2 [6.7, 17.6], no ceiling | 23.8 | −45% |
| c_home_01, time-slot | kitchen (8) | **no room** | 7.8 | – |
| | room1 / room2 / hall | 5.5 / 13.9 / 9.5 | 13.3 / 14.9 / 23.8 | −59% / −7% / −60% |

Reading:
- **Rooms with ≥ 4 photos that look across the room: −7% to +1% on area, ceilings −5% to
  +2%** (within the brief's ±8%). One time-slot set (c_damage_02) is −10%.
- **2–3 photos, or photos that mostly look at close-ups**: rooms 25–60% small, or none
  (kitchen time-slot: 8 photos, mostly close-ups and a ceiling fan). The tier warns.
- **Intervals**: the LiDAR value falls inside the 90% interval in 8 of 11 rooms; misses
  are the hall (both sets) and the time-slot room1. They are not calibrated yet.
- **Stitching fails** (G7): no room positions, no adjacency. Total area is a sum of rooms.

Time on the M4: 25–30 s per single room (model ~10 s), 42–71 s for four folders; peak
memory 9.7–11.5 GB. One command, `floorplan run`, no extra flags.

## 9. Not done / next

- Stitching: place each room with the photos through doorways (fit a per-room cloud to a
  joint reconstruction on the shared photos, rotation and shift only). The joint runs'
  1–2 m camera errors suggest this needs better doorway photos, not just code.
- Real photo folders (the friend's, or the walk-in): everything here is video stills.
- Calibrate intervals against tape once C's measurement plan arrives.
- Try carving in the video tier (the kitchen did not pair after re-levelling).
