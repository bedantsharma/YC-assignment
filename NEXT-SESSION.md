# Next session

State and findings: [HANDOVER.md](HANDOVER.md). Each step ends with a commit and the
ROADMAP status updated.

## First: decide the video model (user)

Recommendation from the bake-off: **Pi3X** for video/photo geometry (cameras 5× more
accurate, walls closer), **MapAnything** kept as the Apache-licensed fallback behind a
flag. Ask the user to confirm, and whether ~4 GB of Pi3X weights may replace MapAnything's
4.9 GB on the laptop (net disk change ≈ 0). If not, the walk-in stays on MapAnything.

## Then, in order

1. **Pi3X on the M4** (only if the user agrees): 30 frames of `c_damage_01` locally; check
   memory (< 16 GB) and time. If it fits, add it to `src/floorplan/mvs.py` behind
   `--model {pi3x,mapanything}` and rerun the video tier on the damage room.
2. **Whole-home video** (both models found 1 room of 4 at 30 frames): chunked
   reconstruction. Overlapping windows of ~30 frames (e.g. 10 shared), each reconstructed
   on its own, chained by a similarity fit on the shared frames' camera centres, fused,
   then `build_plan`. Target: `c_home_01` 4 rooms, total area near the LiDAR 59.8 m².
   Develop on Kaggle if it needs many windows; keep the final path runnable on the M4.
3. **Scale correction** for the video tier: both models are 1–9% off and biased
   differently up and down. Measure the bias per model on `c_damage_01/02` (LiDAR as
   reference), then decide between a calibrated factor and a geometric prior; widen
   intervals by what remains.
4. **Bake-off round 2** (optional, cheap): fix DA3 (add `addict`; dry-run the install
   locally first, no model construction), rerun on Kaggle. Skip if it doesn't install
   cleanly: at 1.4B and CC BY-NC it is unlikely to be used.
5. **Openings** (doors, windows) in the LiDAR backend: `lintel_mask` in
   `src/floorplan/plan2d.py` finds door heads; the gap under a head gives the width. Fill
   `rooms[].openings` + adjacency.
6. **Photo tier** with the chosen model (stills sampled from C's videos stand in for photo
   folders).
7. **Phase 5:** one open-vocabulary detector for damage (the hole in C's damage room) and
   to remove wardrobes/fridges from walls (fix map 04).

## Waiting on

- Friend: house measurement plan (user asks Sun Oct 4) → `data/gt/home_c.yaml` by hand.
- Architect: blind laser measurements for B → `data/gt/arkitscenes_421337.yaml`.
- With either, the first accuracy numbers, then `scripts/benchmark.py` and the
  `fixloop-before` tag.

## Open, lower priority

- Drift correction that does no harm (brief G5); report must cover the current ablation.
- Fix 02 notch long axis still 9–12 cm between scans; B's extents differ by up to 0.9 m
  (fix map 02b, segmentation, untraced).
