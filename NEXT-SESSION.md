# Next session

State and findings: [HANDOVER.md](HANDOVER.md). Each step ends with a commit and the
ROADMAP status updated. **One model job at a time on the laptop.**

## Done this session (Sun ~01:00)

User chose Pi3X; it runs on the M4; whole-home video works by chained windows; scale bias
corrected and checked on held-out rooms ([docs/video_scale.md](docs/video_scale.md)).

## Next, in order

1. **Photo tier** (`src/floorplan/pipeline.py` photo branch is a stub). Stills sampled
   from C's videos stand in for photo folders (one folder per room). Reconstruct all
   folders jointly with Pi3X (doorway photos link rooms; chained windows if > 30 photos),
   then the same `correct_scale` → `build_plan` → `widen_room` path as video. Folder name
   = room label. Cut line: per-room reconstruction if the joint one fails.
2. **Openings** (doors, windows) in the LiDAR backend: `lintel_mask` in
   `src/floorplan/plan2d.py` finds door heads; the gap under a head gives the width. Fill
   `rooms[].openings` + adjacency.
3. **Phase 5:** one open-vocabulary detector for damage (the hole in C's damage room) and
   to remove wardrobes/fridges from walls (fix map 04).
4. **Video on B** (`data/arkitscenes/.../<id>.mov`, an independent home): checks the scale
   correction outside C, and against the laser scan once the architect's numbers land.
5. Bake-off round 2 (DA3) only if time is left: unlikely to be used (1.4B, CC BY-NC).

## Waiting on

- Friend: house measurement plan (user asks Sun Oct 4) → `data/gt/home_c.yaml` by hand.
  Then recompute the video scale bias against tape instead of LiDAR.
- Architect: blind laser measurements for B → `data/gt/arkitscenes_421337.yaml`.
- With either: the first accuracy numbers, then `scripts/benchmark.py` and the
  `fixloop-before` tag.

## Open, lower priority

- Video: the kitchen comes out 8.5% short after correction; window 2 of `c_home_01`
  chains with a 17 cm residual. Both untraced.
- Drift correction that does no harm (brief G5); report must cover the current ablation.
- Fix 02 notch long axis still 9–12 cm between scans; B's extents differ by up to 0.9 m
  (fix map 02b, segmentation, untraced).
