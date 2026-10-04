# Video tier: whole home and scale correction

Sun Oct 4, ~00:30 IST. Model: Pi3X (user's choice after bake-off round 1,
[model_research.md](model_research.md)); MapAnything kept behind `--model mapanything`.
LiDAR of the same recording is the reference (evaluation only); C has no ground truth yet.

## Pi3X on the M4

The first local run failed: Pi3X turns autocast off for its output heads only on CUDA, so on
MPS the camera head's SVD ran in bf16, which MPS does not support. The heads now run in
float32 (`src/floorplan/mvs.py`). Same 30 frames of `c_damage_01`:

| | M4 (MPS) | Kaggle T4 (fp16) | LiDAR |
|---|---|---|---|
| Camera error (median, vs ARKit after similarity fit) | 5.2 cm | 5.7 cm | – |
| Scale vs ARKit | 1.001 | 1.007 | – |
| Area | 11.85 m² | 11.70 m² | 13.13 m² |
| Long wall | 4.12 m | 4.10 m | 4.24 m |
| Ceiling | 3.06 m | 3.04 m | 3.36 m |
| Model time / peak memory | 119 s / 10.9 GB | – / 12.6 GB | |

## Whole home: chained windows

One pass of 30 frames over the 166 s walk of `c_home_01` found 1 room of 4 (both models).
`src/floorplan/chunks.py`: 90 frames in 4 windows of 30, 10 shared; each window is
reconstructed alone and mapped onto the previous one by a trimmed similarity fit on the
shared frames' dense point maps (pixel-for-pixel correspondences, RGB only).

`uv run scripts/video_eval.py data/home_c/lidar/c_home_01 --frames 90` then
`uv run scripts/score_bakeoff.py --dir outputs/video_eval`:

| c_home_01, Pi3X | one pass, 30 frames (T4) | chained, 90 frames (M4) | LiDAR |
|---|---|---|---|
| Rooms | 1 | **4** | 4 |
| Total area | 10.8 m² | **53.7 m²** (−10%) | 59.8 m² |
| Camera error (median) | 0.40 m | **0.16 m** | – |
| Time / peak memory | – | 463 s / 10.4 GB | |

Fit residuals between windows: 4.0, 16.8 and 9.8 cm (window 2 is the weakest link).

## Scale bias

`uv run scripts/video_scale.py outputs/bakeoff/c_damage_0*__*.npz outputs/video_eval/*.npz`.
Video / LiDAR per room. Rooms are paired by floor overlap after moving the video cloud
into the LiDAR frame with the rotation of a camera fit to ARKit (no scale; evaluation only).

| Recording | Model | LiDAR room | Longest wall | √area | Ceiling |
|---|---|---|---|---|---|
| c_damage_01 | MapAnything (T4) | r1 | 0.907 | 0.911 | 1.023 |
| c_damage_02 | MapAnything (T4) | r1 | 0.943 | 0.981 | 1.048 |
| c_damage_01 | Pi3X (T4) | r1 | 0.966 | 0.944 | 0.904 |
| c_damage_02 | Pi3X (T4) | r1 | 0.971 | 0.979 | 0.929 |
| c_damage_01 | Pi3X (M4) | r1 | 0.972 | 0.950 | 0.909 |
| c_home_01 | Pi3X chained | r1 living | 0.814 | 0.966 | 0.916 |
| c_home_01 | Pi3X chained | r2 kitchen | 0.883 | 0.882 | 0.909 |
| c_home_01 | Pi3X chained | r3 bedroom | 0.976 | 0.989 | 0.944 |
| c_home_01 | Pi3X chained | r4 (damage room) | 0.928 | 0.944 | 0.909 |

Findings:
1. **Not a global scale error.** Pi3X's camera path is metric (1.00 vs ARKit on the damage
   room), yet its surfaces come out short: the model places walls and ceiling too close to
   the cameras. The bias differs by axis: Pi3X ~0.96 horizontal, ~0.91 vertical;
   MapAnything ~0.94 horizontal, ~1.04 vertical.
2. **The vertical bias is stable**: Pi3X ceilings 0.904–0.944 over 7 rooms, 3 recordings.
3. **Horizontal is noisier**, and the longest wall is dominated by outline differences
   (living room: √area −3%, longest wall −19%, because the LiDAR outline includes a 2.9 m²
   low-confidence strip). The kitchen is short by ~12% in both measures.

## Correction (shipped, provisional)

> **Re-measured on Oct 4** ([fix_declaration.md](fix_declaration.md) §6): the values below
> were fitted to LiDAR walls that were 7-8% short. Against the corrected LiDAR the
> horizontal bias is Pi3X **0.890**, MapAnything **0.877** (vertical unchanged). The tables
> below are the original fit, kept as the record.

`src/floorplan/intervals.py`: the z-up cloud is divided by the model's bias (horizontal,
vertical), fitted on the **damage room only** (c_damage_01 and c_damage_02): Pi3X 0.964 /
0.914, MapAnything 0.935 / 1.035. Checked for Pi3X on the home's three other rooms, not
used in the fit (r4 is the damage room again, so excluded):

| Held-out room | Ceiling before → after | √area before → after | Longest wall before → after |
|---|---|---|---|
| r1 living | −8.4% → +0.2% | −3.4% → +0.2% | −18.6% → −15.5% |
| r2 kitchen | −9.1% → −0.5% | −11.8% → −8.5% | −11.7% → −8.4% |
| r3 bedroom | −5.6% → +3.3% | −1.1% → +2.6% | −2.4% → +1.3% |

Intervals then add the remaining relative error in quadrature (1σ): Pi3X 5% horizontal,
2% vertical (from the held-out rooms); MapAnything 6% / 4% (no held-out check), plus 5 cm
surface error.

Limits, stated plainly: the fit and the check are the same home, phone and person; the
damage room is 3 recordings of one room; LiDAR is the reference, not a tape. The brief's
±3% video target is met for ceilings on the held-out rooms, not for walls. Next checks:
the friend's measured plan (C), and B's video against the laser scan (an independent home).

## Result: `floorplan run data/home_c/lidar/c_home_01 --tier video --frames 90`

Pi3X, 4 chained windows, scale corrected; 434 s of model time on the M4. Values with 90%
intervals; LiDAR of the same walk for comparison (rooms paired by hand from the plans).

| Room | Video area (m²) | LiDAR area (m²) | Video ceiling (m) | LiDAR ceiling (m) |
|---|---|---|---|---|
| Living | 21.6 [18.0, 25.2] | 23.8 (incl. 2.9 low confidence) | 3.33 [3.19, 3.47] | 3.33 |
| Bedroom | 15.8 [13.1, 18.4] | 14.9 | 3.30 [3.16, 3.44] | 3.17 |
| Damage room | 12.7 [10.5, 14.8] | 13.3 | 3.37 [3.23, 3.51] | 3.36 |
| Kitchen | 7.3 [6.0, 8.6] | 7.8 | 3.30 [3.16, 3.43] | 3.36 |
| **Footprint** | **57.3 [52.2, 62.5]** | **59.8** | | |

Every LiDAR area and ceiling falls inside the video interval. The intervals are wide
(±16% on area) because the horizontal residual is 5%; they narrow only with better
geometry or ground truth to calibrate against.
