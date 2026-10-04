# Home C: Camera-app videos and Polycam (Oct 4)

New from the friend: three Camera-app videos (damage room twice, whole house once) and
three Polycam screenshots (2D plan, isometric). Tape measurements and photos are still to
come, so **our LiDAR plan is the provisional reference** (user's call) and Polycam is the
competitor, not ground truth.

All model runs on Kaggle (`kaggle/video_runs`, T4, fp16); the laptop replays the cached
reconstructions (`FLOORPLAN_RECON_CACHE`, `mvs.py`).

## Inputs

| File | What | Note |
|---|---|---|
| `data/home_c/video/c_damage_v1.mp4`, `c_damage_v2.mp4` | damage room, 116 s / 119 s | 464 × 832 portrait, 60 fps: compressed in transit (a chat app), not the 4K original |
| `data/home_c/video/c_home_v1.mp4` | whole house, 295 s | same; long stretches pointed at the ceiling (fans, cornices) and close-ups |
| `data/home_c/polycam/*.jpeg` | Polycam 2D plan + isometric | screenshots, not an export; they show the street address, so they stay gitignored. Numbers transcribed by hand into `data/gt/home_c_polycam.json` |

## Polycam vs our LiDAR (same home, different scans)

Room matching: Polycam's plan rotated 180° onto ours (`data/gt/home_c_polycam.json`).
Polycam's numbers are interior wall-to-wall lengths.

| Room (Polycam) | Polycam (m) | Our LiDAR (m) | Difference | Area: Polycam vs ours (m²) |
|---|---|---|---|---|
| Kitchen | 3.57 × 3.04 | 3.20 × 2.72 | −37 / −32 cm | 11 vs 7.8 |
| Bedroom 1 (`room2`) | 4.53 × 3.73 | 4.24 × 3.53 | −29 / −20 cm | 17 vs 14.9 |
| Bedroom 2 = damage room (`room1`) | 4.53 × 3.27 | 4.46 × 3.21 | −7 / −6 cm | 14 vs 13.3 |
| Dining + Bedroom 3 (`hall`, one open space) | 5.52 × 5.59 | 4.95 × 5.52 | −57 / −7 cm | 31 vs 23.8 |
| Damage room, own scans | 4.53 × 3.27 | 4.24 × 3.30 / 4.26 × 3.08 | −29 / +3, −27 / −19 cm | 14 vs 13.1 / 12.4 |

Ours is smaller on every dimension. In the damage room's cloud each wall appears 2-3
times, 15-50 cm apart (pose drift: the same evidence behind fix map 02's open wall half),
and our outline snaps to the innermost copy; in the kitchen, cabinets also count as wall
(fix map 04). Which is right needs the tape.

## Video tier on the Camera-app videos

### Damage room: works

Scored with `uv run scripts/score_video_c.py <plan.json> --lidar outputs/c_damage_02_lidar/plan.json`.

| Video | Frames | Room (m) | Area [90%] (m²) | Ceiling [90%] (m) |
|---|---|---|---|---|
| v1 | 30 | 4.39 × 3.21 | 13.4 [11.1, 15.7] | 3.50 [3.35, 3.64] |
| v2 | 30 | 4.17 × 2.76 | 11.2 [9.0, 13.1] | 3.30 [3.16, 3.44] |
| v1 | 60 | **4.21 × 3.11** | 12.3 [10.2, 14.4] | 3.48 [3.34, 3.62] |
| v2 | 60 | **4.24 × 3.08** | 12.0 [10.0, 14.0] | 3.32 [3.18, 3.46] |
| LiDAR `c_damage_01` / `_02` | | 4.24 × 3.30 / 4.26 × 3.08 | 13.1 / 12.4 | 3.36 / 3.35 |
| Polycam | | 4.53 × 3.27 | 14 | |

With 60 frames both videos agree with the LiDAR within 5 cm on both sides (v2 is within
2 cm of `c_damage_02`), and every LiDAR area and ceiling is inside the video interval.
30 frames is too few for a 2-minute clip (v2's short side −32 cm). Kaggle T4 run time
60-110 s per video.

### Whole house: fails

| Frames | Before the chain fix | After |
|---|---|---|
| 90 | 1 room (21.6 m², footprint IoU 0.34) | 4 rooms, 39.0 m², IoU 0.42, but dimensions wrong (room1 5.6 × 3.5 vs 4.46 × 3.21) |
| 150 | 1 room (7.3 m²) | 2 rooms, 11.0 m², IoU 0.18 |
| LiDAR / Polycam | 4 rooms, 59.8 m² / 6 rooms, 79 m² gross | |

**Diagnosis (link level, replayed locally from the cache):** the chained windows broke at
room transitions. Each shared frame, fitted on its own, matches the earlier window to 1-2
cm; fitted together they give scale 0.54 and a 153 cm residual, because the two windows
place the shared frames (7.3 m of walking through a doorway) differently. One similarity
cannot serve both placements. A first guess, low-texture frames (ceiling shots), was
wrong: the worst link's shared frames are well textured.

**Fix (`chunks.fit_shared`):** when the fit over all shared frames is broken (residual >
10 cm), each shared frame's own fit is a candidate and the link is fitted on the frames
that agree with the best one. Prediction: link 5 near 0.95 with ≤ 3 cm; damage room
unchanged. Result: link 5 0.538/153 cm → 0.946/0.8 cm; every link now 0.94-1.07; damage
room plans identical. A first version applied the candidate fit to every link and moved
the damage room's short side by 18-28 cm (fewer frames, looser rotation), so it now runs
only on broken links.

**What is still wrong:** the windows themselves fold. Top-down, the chained cloud shows
the same rooms overlaid at different rotations: within one 30-frame window spanning two
rooms, the model misplaces one room against the other. The link fix cannot repair that.
The LiDAR recording's own video of the same house (22 s steady walk) gives 4 of 4 rooms
(`docs/video_scale.md`); this 5-minute clip with ceiling sweeps does not. Next things to
try, in order: shorter windows per room (more frames, fewer rooms per window); skip frames
pointed at the ceiling; detect a folded window (its cameras jump) and drop it.
