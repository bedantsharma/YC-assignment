# Next session

Done in the last session: fix map 01a, 01b, 01c (see `docs/fix_loop.md`). Open checks from
it: dataset A's room changes are unverified (compare with A's `rgb.mp4`); the plan does not
draw the low-confidence zone's outline, only its area on the room label.

Work in this order. Each step ends with a commit and the ROADMAP status updated.

1. **Model spike, 1 h (biggest risk).** Video and photo tiers are 2 of the 3 required tiers
   and Cozmo picks the walk-in tier on the day. Run a pretrained multi-view model (VGGT,
   MASt3R or MapAnything) on ~30 frames of a Stray `rgb.mp4` on this Mac. Compare its
   geometry with the LiDAR result of the same recording. Pick by result. If none runs,
   tell the user at once.
2. **Fix map 02: repeatability.** `c_damage_01` vs `c_damage_02` disagree by 3–15 cm on
   walls (worst: 3.23 vs 3.08 m) and 8.8 cm on ceiling (gate: 1 cm / 0.5%). Trace before
   fixing (systematic debugging), declare in `docs/fix_loop.md` before changing code. Also
   compare B's 3 captures and A's 3. Candidate for the brief's single fix-loop entry.
3. **Drift correction** with an on/off ablation on `c_home_01` and A (brief fails without
   it).
4. **Openings** (doors, windows): `lintel_mask` in `src/floorplan/plan2d.py` already finds
   door heads; the gap under a head gives the width. Fill `rooms[].openings` + adjacency.
5. **Video and photo tiers** (Phase 4) with the model from step 1.
6. **Phase 5:** one open-vocabulary detector for damage (the hole in C's damage room) and
   to remove wardrobes/fridges from walls (fix map 04). Plan in ROADMAP Phase 5.

Waiting on the user: architect's laser measurements for B (first real accuracy numbers).
