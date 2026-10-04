# Decision log

Every design decision, why it was made, the evidence, and what was rejected. Meant to be
defended live with tools closed, so each line carries its number. Sources in brackets.

## Scope and output

| # | Decision | Why | Evidence | Rejected |
|---|---|---|---|---|
| S1 | **One geometry backend for all three tiers**: every input becomes a metric z-up point cloud with camera positions, then the same floor / wall / room code measures it | Three tiers in two days; one fix improves every tier; tiers differ only in where the points come from | The fix loop (fix 09) moved LiDAR 29 → 5 cm and the same code serves video and photos [technical_report §2, §6] | A separate method per tier (e.g. a learned layout model for photos): three code bases to debug |
| S2 | **Own JSON format, no JSON Schema file** | No schema was published; Cozmo said to ignore that reference | Cozmo's answer, Oct 3 [requirements §1]; format documented in README, enforced by `output.py` types | Inventing a schema nobody scores |
| S3 | **A 90% interval on every number**, as `{value, lo, hi, unit}`, checked lo ≤ value ≤ hi when written | The brief caps the score for confident but wrong output on thin input | Coverage: LiDAR 91%, video 92%, photo 80% of sides [benchmark_report] | – |
| S4 | **Wall length = corner to corner on the interior face; floor area = net visible floor** | What a tape measures and what a homeowner means by room size | Matches the architect's drawing convention we score against [data/gt/home_c.json] | – |
| S5 | **Capture route 2: stock apps + a protocol** (Stray Scanner for LiDAR, Camera app for video and photos) | No custom iOS app in two days; Stray Scanner matches the provided data format | Brief allows route 2; Cozmo's own captures are Stray Scanner [requirements §4] | Own iOS app (route 1) |
| S6 | **Protocol asks ~15 photos per room (minimum 4), one through each doorway**, though the brief says 2-8 | 2-3 photos gave rooms 25-45% too small; the pipeline still accepts 2-8 with wider intervals and a warning | Photo tier tests [photo_tier.md]; brief: "we follow your page literally" | Holding to 8: the kitchen fails at 8 photos and works with all 33 [gt_comparison] |

## Geometry

| # | Decision | Why | Evidence | Rejected |
|---|---|---|---|---|
| G1 | **Floor and ceiling from height histograms**; a ceiling peak must stand apart from stronger peaks below it | Robust and needs no model; the "stand apart" test is fix 02 [technical_report §2] | LiDAR ceilings within −2.1 to +1.0 cm; 3 scans of one room agree within 1.3 cm [benchmark_report] | – |
| G2 | **A cell is wall if its points span ≥ 0.8 m of height** | Separates walls from counters and tables | `plan2d.WALL_MIN_EXTENT_M`; counter fronts capped by a hollow-under top are excluded [technical_report §2] | – |
| G3 | **Each wall placed at the median of its points 2.3 m to 0.3 m under the ceiling, own side of interior walls** (fix 09) | Drift smears a wall into a 10-40 cm band and furniture sits below 2.3 m; the old rule took the band's inner edge | Median side error 29 → 5 cm; damage-room scans 21 → 0.4 cm apart; rules compared offline on every room before choosing [fix_declaration §2] | Median of the 0.1-2.3 m band (kitchen −32 cm, dining −29 cm); median above 2.3 m without the own-side rule (dining −12 cm). Own side chosen for the physical reason (an interior wall's far face belongs to the neighbour), not the score |
| G4 | **Drift correction built but off by default** | It helped one capture and hurt two | Damage room 21 → 1 cm, but A's `c00a170fe1` and C's kitchen worse [drift_ablation] | On by default; "poses as-is" with no method (brief: automatic fail; we state method + ablation) |
| G5 | **Unscanned floor kept as a flagged low-confidence zone, area interval widened** | Honest about a wall with no points instead of guessing it | Dining room short side −23 cm, its west wall has no points at any height [technical_report §9] | Extrapolating the wall: invents geometry |
| G6 | **Openings from gaps at body height confirmed by seeing through; door if a lintel is above** | Only geometry available; no model | Door found in both scans but 34 cm narrow; windows not found (gate G1 not met, stated) [openings.md] | – |

## Video and photo tiers

| # | Decision | Why | Evidence | Rejected |
|---|---|---|---|---|
| V1 | **Pi3X as the reconstruction model**, MapAnything as the Apache-2.0 option (`--model mapanything`) | Cameras ~5× more accurate and walls closer in a bake-off on our own home | Camera error 6-7 cm vs 30 cm; long wall −3.5% vs −7% [model_research] | MapAnything default (commercial licence, less accurate); DA3 and SpatialLM tested, not adopted [lidar_model_research] |
| V2 | **Divide out a measured scale bias per model and tier** (Pi3X 0.89 horizontal, 0.91 vertical), and widen intervals by the residual | Each model places surfaces too close by a stable factor | Re-measured after the fix loop (0.964 → 0.890); damage-room clips then landed +5 / +6 cm [video_scale, fix_declaration §6] | Trusting the model's metric scale: 9% low ceilings |
| V3 | **Long videos in overlapping windows of 30 frames (10 shared), chained by similarity fits on the shared frames' point maps** | One pass of 30 frames over a whole home finds 1 room of 4; more frames in one pass run out of memory | Windows: 4 of 4 rooms on `c_home_01`; a broken link is refitted on the frames that agree (scale 0.54 / 153 cm residual → 0.95 / 0.8 cm) [home_c_new_captures.md] | One big pass (out of memory on a T4 at 90 frames) |
| V4 | **Video and photo tiers read only the RGB, never the LiDAR recording's depth, poses or IMU** | Their numbers must be what a non-Pro iPhone gets | Enforced in the loaders [data_plan.md] | Using ARKit poses to help the video tier |
| V5 | **Photo folders reconstructed one room at a time, laid side by side, not stitched** | Joint reconstruction placed rooms 1-2 m wrong; a wrong stitch is worse than an honest "not stitched" | [photo_tier.md]; gate G7 stated as not met | Shipping the wrong joint stitch |
| V6 | **Frames decoded once on the laptop and shipped to Kaggle as PNG** (`FLOORPLAN_FRAMES_CACHE`) | ffmpeg on Kaggle (x86) and the Mac (ARM) decode the same video to different pixels, so pixel-keyed caches missed | Tested: not the ffmpeg version, not B-frames [HANDOVER, video.py] | Decoding on both sides |

## Compute and reproducibility

| # | Decision | Why | Evidence | Rejected |
|---|---|---|---|---|
| R1 | **The reconstruction model runs on Kaggle's GPUs by default; one job per run** (`--recon auto`) | Pi3X does not fit the 16 GB laptop (one run pushed memory into the red); the walk-in runs on our laptop | k8 photos (4 rooms) end to end in 4.4 min, 0.66 GB on the laptop, rooms within 3% of the cached run [mvs.py, remote.py] | Running Pi3X on the laptop; one Kaggle job per window (5-10 min each) |
| R2 | **Local fallback in small windows, one child process each, retried smaller when killed**; kept for machines with more memory | The run must not crash a machine without network; a killed child returns all its memory | Window 10 frames on 16 GB; kill-and-retry tested with a fake model that lives only in `tests/` [mvs_local.py] | One local pass of 30 frames (12.8 GB peak) |
| R3 | **Every model output cached by its input pixels**; the laptop replays it (`FLOORPLAN_RECON_CACHE_ONLY=1`) | Every reported number regenerates from raw data without a GPU | `scripts/reproduce.sh` regenerates all reports [D4, D5 in COMPLIANCE] | Re-running models for every report |
| R4 | **No MAGMA linear algebra on the GPU** | Added to dodge an out-of-memory error; it silently moved Pi3X's points by 1.4 m | Same 8 photos: MAGMA vs not 144 cm apart, without it 0.7 cm from the cached run; the 24-photo hall then found its room [mvs.py] | Keeping it for the memory saving |
| R5 | **ffmpeg from the system, else the copy bundled with `imageio-ffmpeg`**; length and rotation read without ffprobe | A Mac without Homebrew must still run the video tier | Same length to the microsecond and same rotation on all 10 iPhone videos; pixel-identical frames [ffmpeg.py] | Requiring Homebrew |
| R6 | **fp16 on the Kaggle T4, not bf16** | With bf16 the T4's attention falls back to the full matrix (86 GB for 30 views) | Kaggle runs [CLAUDE.md] | bf16 |

## Ground truth and evaluation

| # | Decision | Why | Evidence | Rejected |
|---|---|---|---|---|
| E1 | **Ground truth only from the architect's drawing and the friend's tape, never from our code** | Scoring ourselves against our own output proves nothing | [data/gt/home_c.json] | LiDAR as truth for the image tiers' headline numbers |
| E2 | **Head-to-head on our own home (C), Polycam 7.0.4 vs our LiDAR, both against the drawing** | Cozmo said to compare on our own data; no export of the provided apartment exists | Beat or tie 6 of 8 (75%, target 70%); ties at Polycam's 1 cm precision [gt_comparison] | Comparing against Polycam as if it were truth |
| E3 | **Fix-loop target: short walls on the LiDAR tier**, declared before fixing | The worst gate by size and it touched every tier through the shared backend | Median 29 cm, truth outside the area interval in 6 of 6; declared in commit `520904a` [fix_declaration] | – |
| E4 | **Keep one room of home C untouched for the walk-in rehearsal** | A rehearsal on tuned data proves nothing | [CLAUDE.md] | Tuning on everything |
| E5 | **Calibration reported as empirical coverage of the 90% intervals** | The brief's "calibrated intervals" means the stated level holds | 91% / 92% / 80% sides [calibration.py] | – |

## Damage

| # | Decision | Why | Evidence | Rejected |
|---|---|---|---|---|
| D1 | **A hosted vision model finds and labels damage; our geometry measures it** | Models are good at "what"; sizes need the wall plane and the pose, which only we have | Staged hole (31.7 cm²) inside the 90% area interval on 7 of 7 runs on all tiers [damage_hole.md] | Asking the model for sizes |
| D2 | **Gemini 3.1 Pro as the detector** | Best on every row of a 3-model comparison, and the fastest; a false alarm costs a homeowner a check | Holes 10 / 10, 0 false holes, 16 / 16 clean photos left clean, 8 s per photo vs Flash 3.8 / 3.6: 9 / 10, 12-11 / 16, 14-24 s [damage_models.md] | Gemini 3.8 Flash, 3.6 Flash; Gemini 2.5 (older) |
| D3 | **Offline fallback: Florence-2-base on the laptop**, automatic when Gemini fails after retries | Cozmo asked for a local fallback in case the walk-in has no network | Finds 4 of 10 hole photos (misses far ones), 3 s per photo; sized the hole as well as Gemini on the scans [damage_models.md, damage_hole.md] | – |
| D4 | **Damage outlines without a model**: contrast against the surrounding wall, ellipse fallback | Simple, fast, no weights; good enough for the area interval | 7 of 7 intervals hold the tape [damage_hole.md] | A segmentation model per box |
| D5 | **LiDAR keyframes: pauses first, then coverage** (each wall patch seen twice, within 3 m and 60°, not hidden by depth), 60 frames | Sending every frame is slow and costly; pauses are where the user looked at damage | [damage_frames.py]; protocol asks for a 3 s hold at 1 m from each damage | Even time slots (the first version) |
| D6 | **Two-view rule judged against what the keyframes could see**: an item is dropped only if ≥ 2 keyframes looked at the spot and it was seen in fewer than 2; seen by one frame only = kept, unconfirmed | Sampling can leave damage in one frame; dropping it then would be wrong | [damage_frames.confirm] | A plain "seen twice" rule |
| D7 | **Crack width only from traced cracks; crack pass off by default** | Box outlines gave widths that fired the structural rule wrongly; the crack pass once looped 54 segments | [technical_report §8] | Width from any outline |
| D8 | **Hand grime read as water stain left as a known limit** | A prompt fix would be tuned on the same 26 test photos; humans confuse them too and there is no grime class | User's decision, Oct 4 [technical_report §8] | Prompt tuning on the test set |
| D9 | **Flags name the rule that fired (R1-R5, R7-R10); scope items Xactimate-style, no prices** | The brief asks for the rule; prices vary by region | [damage_rules.py]; R6 (crack from a door corner) not built | – |

## Process

| # | Decision | Why | Evidence | Rejected |
|---|---|---|---|---|
| P1 | **No model ever runs on the laptop during development**; Kaggle runs, the laptop replays | One Pi3X run pushed the 16 GB M4 into red memory pressure | User's rule, Oct 4 [CLAUDE.md] | Local runs |
| P2 | **Stand-in models only in tests, never in `src/`** | Nothing fake may reach the real pipeline | `tests/fake_mvs_worker.py` [test_recon_backend.py] | An env-var dry-run mode in the pipeline |
| P3 | **Small commits at every working step** | Commit history is graded; a repo in one or two commits scores zero on process | 140 commits by Oct 5 [git log] | Squashed history |
