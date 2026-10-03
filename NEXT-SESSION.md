# Next session

State and findings: [HANDOVER.md](HANDOVER.md). Each step ends with a commit and the
ROADMAP status updated. **One model job at a time on the laptop.**

## Done overnight (Sun ~01:30–04:00, user asleep)

Photo tier built and measured ([docs/photo_tier.md](docs/photo_tier.md)): Firecrawl survey,
Kaggle bake-off round 2 (Pi3X again), per-room reconstruction with line-of-sight carving.
Rooms with ≥ 4 good photos: −7% to +1% area vs LiDAR. **Stitching rooms together fails**
(joint reconstruction 1–2 m off), so rooms are laid out side by side with a warning.
Nothing pushed yet: commits are local.

## For the user when back

- Push when happy (`git push`); review `docs/photo_tier.md` §8 (results) and §5 (stitch).
- Friend: real photo folders would replace the video stills (2–8 per room, protocol).
- Friend's measurement plan → `data/gt/home_c.yaml` (first tape check of all tiers).

## Next, in order

1. **Openings** (doors, windows) in the LiDAR backend: `lintel_mask` in
   `src/floorplan/plan2d.py` finds door heads; the gap under a head gives the width. Fill
   `rooms[].openings` + adjacency.
2. **Phase 5:** one open-vocabulary detector for damage (the hole in C's damage room) and
   to remove wardrobes/fridges from walls (fix map 04).
3. **Video and photo tiers on B** (`data/arkitscenes/.../<id>.mov`, an independent home):
   checks both scale corrections outside C, and against the laser scan once it lands.
4. **Photo stitching**, only if time is left: place each per-room cloud with the doorway
   photos (fit to a joint reconstruction on shared photos, rotation + shift only).
5. Phase 6 benchmark + graded fix loop once ground truth is in; Phase 7 reports.

## Waiting on

- Friend: house measurement plan (user asks Sun Oct 4) → `data/gt/home_c.yaml` by hand.
- Architect: blind laser measurements for B → `data/gt/arkitscenes_421337.yaml`.
- With either: first accuracy numbers, `scripts/benchmark.py`, the `fixloop-before` tag.

## Open, lower priority

- Video: kitchen 8.5% short after correction; window 2 of `c_home_01` chains with 17 cm
  residual; try carving in the video tier.
- Drift correction that does no harm (brief G5); report must cover the current ablation.
- Fix 02 notch long axis 9–12 cm between scans; B's extents differ by up to 0.9 m (02b).
