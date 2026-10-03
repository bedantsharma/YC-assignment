# Next session

Done Sat 20:40–22:20 IST (see each doc for numbers):
- **Model spike** ([docs/model_spike.md](docs/model_spike.md)): MapAnything runs on the M4
  (52 s / 30 frames, 12.8 GB peak). Upright frames: scale 1.03 vs ARKit, cloud 5.8 cm
  from LiDAR, room 11.1 vs 13.1 m². Sideways frames (as Stray stores them) collapse it.
- **Fix 02** (`fix02-after`): ceiling tail ripples fixed; the damage room's three scans
  agree on the ceiling to 1 cm. Wall half parked on branch `fix02-wall-occluder`.
- **Drift correction** (`--drift`, [docs/drift_ablation.md](docs/drift_ablation.md)):
  built and ablated on all 9 captures. Mixed: damage-room repeat scans 21 → 1 cm on the
  short side, but A `c00a170fe1` loses wall support. **Off by default.**

**Decided (user):** drift correction stays **off by default**; with `--drift` the
`c_home_01` kitchen outline got much worse. Not tracing the A regression now.

Work in this order. Each step ends with a commit and the ROADMAP status updated.

1. **Video tier** (Phase 4) with MapAnything: upright frames (rotation from video
   metadata; an RGB-only rule for Stray recordings, which have none), keyframes by view
   change within the 16 GB budget, then `build_plan`. Install as an optional dependency
   group, not a core one. Reference: the LiDAR result of the same recording.
2. **Openings** (doors, windows): `lintel_mask` in `src/floorplan/plan2d.py` finds door
   heads; the gap under a head gives the width. Fill `rooms[].openings` + adjacency.
3. **Photo tier** with the same model.
4. **Phase 5:** one open-vocabulary detector for damage and for furniture on walls
   (fix map 04).

Open from fix 02: notch long axis still 9–12 cm apart between scans; B's extents differ by
up to 0.9 m (fix map 02b, segmentation, untraced).

Waiting on the user: architect's laser measurements for B (first real accuracy numbers).

Later, if time: a drift correction that does no harm (brief G5 wants a stated method).
