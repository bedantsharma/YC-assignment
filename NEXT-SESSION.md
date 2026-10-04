# Next session

State and findings: [HANDOVER.md](HANDOVER.md). Each step ends with a commit and the
ROADMAP status updated. **No big model runs on the laptop: Kaggle only** (CLAUDE.md).
Exception agreed Oct 4: the small damage models below (Florence-2-base, SAM 2.1 tiny) may run
locally on CPU/MPS as the offline fallback.

Deadline Mon Oct 5, 10:00 IST.

## 0. First, collect what was left running (Oct 4 evening)

1. **House video rerun** (`kaggle/house_v2`, kernel `floorplan-house-v2-runs`). The upload
   of the laptop-decoded frames was **stopped by a 30-min time limit** on Oct 4, so the
   dataset `floorplan-house-v2` probably lacks `frames/`. Restage (`videos/c_home_v2.mp4`,
   `code/floorplan` from `src/`, `frames/` = `data/home_c/frames/`, the dataset-metadata.json
   with id `bedantsharma/floorplan-house-v2`), run `uvx kaggle datasets version -p <dir>
   --dir-mode zip -m "frames"` in the background with a long timeout, wait for `ready`,
   then `uvx kaggle kernels push -p kaggle/house_v2 --accelerator NvidiaTeslaT4`.
   Then: the log's `frames sha1 (90 frames)` must be `f2c905478fab…` (the laptop's); download
   to `outputs/kaggle_house_v2/` (delete the old, unusable `recon_cache` there first), and
   replay locally:
   `FLOORPLAN_FRAMES_CACHE=data/home_c/frames FLOORPLAN_RECON_CACHE=outputs/kaggle_house_v2/recon_cache FLOORPLAN_RECON_CACHE_ONLY=1 uv run floorplan run data/home_c/video/c_home_v2.mp4 --tier video --frames 300 --up top --out outputs/house_v2/f300`
   (90/150/240/300). Score with `uv run scripts/score_video_c.py <plan.json>`; add the rows
   to `scripts/gt_table.py`.
2. **Photo replay**: real photos ran on Kaggle (`outputs/kaggle_photos_c2/`, strip version);
   replay locally with `FLOORPLAN_RECON_CACHE=outputs/kaggle_photos_c2/recon_cache
   FLOORPLAN_RECON_CACHE_ONLY=1 uv run floorplan run data/home_c/photo_sets/<all|k8|k5>`
   and add the rows to `scripts/gt_table.py`.
3. **ARK ground truth**: ask the architect whether her dimensions are outer or inner wall
   faces (`data/gt/arkitscenes_421337.json`, "UNRESOLVED"). Then add B to `gt_table.py`.

## 1. Damage (Phase 5): the plan agreed with the user

Research: [docs/damage_research.md](docs/damage_research.md). Test case: the bedroom hole
(2.5 in, centre 4.66 ft up, 7.5 ft from the right wall; photo IMG_1371 in
`data/home_c/photos/room1/`) and the wall cracks around the wiring.

1. **Detect (primary, hosted):** per keyframe/photo, Gemini returns JSON boxes for crack,
   water stain, mould, hole, peeling paint. The user creates the API key and sets it as an
   environment variable themselves (never typed by Claude). Optional: Claude checks each crop to
   cut false positives. Disclose the hosted model in the report.
2. **Detect (offline fallback, local, allowed):** Florence-2-base (0.23B, MIT)
   open-vocabulary boxes. Holes are also confirmed model-free by a depth dip behind the
   wall plane (LiDAR tier).
3. **Outline:** SAM 2.1 tiny (111 MB, Apache-2.0, CPU) turns each box into a mask.
4. **Measure:** cast a ray through each mask-outline pixel onto the wall plane (we know
   every wall's plane and every frame's pose); area in wall (u, v) coordinates. 90% interval
   by Monte Carlo over mask edge (±2 px), plane offset and pose / tier scale bias, widened
   by the spread across views. Check: the staged hole ≈ 32 cm², centre 1.42 m up.
5. **Flags:** rule table in the research doc (BRE Digest 251 crack widths, EPA 10 sq ft
   mould, rising-damp tide mark ≤ 1 m, ceiling stain → leak above, ...). Each flag names
   its rule id. Output fields already exist (`damage[]`, `flags[]`, `scope[]` in
   `output.py`).
6. **Scope:** line items per surface (item, surface id, quantity, unit; no pricing),
   Xactimate-style wording from the research doc.

## 2. Then, in order

1. **Video scale on the new house clip**: every side 20-50 cm long and ceilings ~30 cm high
   at 240/300 frames (one common factor). Hypothesis: the Pi3X scale bias (1/0.890) was
   measured on chat-compressed 464×832 clips and overshoots on the cleaner 540×960 clip.
   Test it without overfitting the benchmark: raw scale of the damage room in the old vs
   new clips (no ground truth needed), or leave-one-room-out. Label any fitted number as
   fitted.
2. **Photo tier**: kitchen found no room at 8 and 5 photos; room1 none at 5. Intervals are
   very wide (kitchen area 5.5-15.1 m²) and coverage was 80%. Strip splitting of portrait
   photos: mixed on room1 (all: −17/−10 → −26/−18 cm; k8: −17/−12 → −15/−11 cm): keep,
   but it is not shown to help.
3. **Presentation** (format not decided): the user will present LiDAR intervals (91%
   coverage) and defend photo (80%) with capture guidance, the scale correction, more data.
4. Walk-in plan for the image tiers (model on Kaggle, laptop replays; decide with the user),
   fresh-clone test (README, < 15 min).

## Waiting on

- User: Gemini API key (set by the user in the environment).
- Architect: outer vs inner faces on the ARK plan.
- Friend: original-quality files and the Polycam app version (low priority now).

## Open, lower priority

- Dining & living short side −23 cm: unscanned wall; accepted as a capture limit (user).
- B's three LiDAR scans disagree (fix map 02b): `42444946` adds an area beyond the room
  (extent 4.21 × 5.34 m).
- No video or photo runs exist on ARKitScenes (B); its `.mov` videos could go through
  `kaggle/` like home C's (public dataset, private Kaggle copy).
- Drift correction that does no harm (brief G5).
