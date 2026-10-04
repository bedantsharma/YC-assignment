# Next session

State and findings: [HANDOVER.md](HANDOVER.md). Each step ends with a commit and the
ROADMAP status updated. **No model runs on the laptop: Kaggle only** (CLAUDE.md).

## 1. The graded fix: our walls stop at the innermost surface (do this first)

Ground truth for home C arrived (`data/gt/home_c.json`: architect's drawing, 4 rooms,
ceilings 11 ft). `uv run scripts/gt_table.py` (→ [docs/gt_comparison.md](docs/gt_comparison.md))
compares every method we have tried:

| Method | Median wall error | Worst | Mean area error | Ceiling |
|---|---|---|---|---|
| Polycam (competitor) | 6 cm | −12 cm | −2% | – |
| **Our LiDAR tier** | **29 cm, every side short** | −53 cm | −19% | 1 cm |
| Our video tier (working clips) | 30 cm | −71 cm | −21% | 6 cm |
| Our photo tier (video stills) | 41 cm | −252 cm | −33% | 10 cm |
| Raw Pi3X / MapAnything / DA3 through our plan builder | 31-67 cm, short | | −21 to −47% | |
| SpatialLM Qwen-0.5B on our LiDAR cloud (own wall finder) | 9 cm | +15 cm | +4% | 20 cm |

**The failing gate:** LiDAR rooms are 11-53 cm short on every side and 11-30% small in
area; the true area is outside our interval in **all 6** room measurements. This is the
worst failing number and the head-to-head (beat Polycam on ≥ 70% of dimensions) is lost
on it.

**Finding:** every method that goes through our plan builder (`plan2d.py` wall test +
`rooms.py` snapping) comes out short, on all three tiers and with every reconstruction
model; the only method with its own wall finder (SpatialLM) is the only one that is not
short. So the shared backend is the cause, not the sensors. Two mechanisms, both seen in
the data:

1. **Doubled walls, inner copy chosen.** In the damage room's LiDAR cloud each wall shows
   up 2-3 times, 15-50 cm apart (pose drift; slice 2.2-3.0 m above the floor, see
   `docs/home_c_new_captures.md`). Our outline snaps to the innermost copy. SpatialLM puts
   walls at the outer copies and lands within 0-15 cm of the truth.
2. **Furniture as wall** (fix map 04). Kitchen 45 / 33 cm short: upper cabinets are 1 ft
   (30 cm) deep and fill the wall band above the counters (friend's tape, in the GT file);
   wardrobes / the closet in the bedroom likewise.

**Procedure (fix-loop rules, `docs/fix_loop.md`):**
1. Tag `fixloop-before` on the current HEAD before touching code.
2. Diagnose per wall on the clouds (`outputs/cache/c_damage_0{1,2}.npy`; `c_home_01`
   needs `cloud.fuse`): for each GT wall, where are the candidate surfaces, which one do we
   snap to, which one matches the GT? Separate the two mechanisms per room.
3. Write `docs/fix_declaration.md` **before fixing**: failing number (above), root-cause
   hypothesis + evidence, the fix, the **predicted** numbers per room.
4. Candidate fixes to test against the GT: snap to the outer face of a wall band (or the
   band's densest / outermost surface seen at all heights), and drop surfaces that end
   below the ceiling with open space behind them (cabinets, wardrobes).
5. Ship; rerun `uv run scripts/gt_table.py`, `uv run scripts/compare_gt_c.py`, and
   `uv run scripts/lidar_summary.py` (all 9 captures, compare with `docs/fix_loop.md`);
   record before vs after; tag `fixloop-after`.
6. The video tier benefits from the same fix: replay it from the Kaggle cache, no model
   needed (`FLOORPLAN_RECON_CACHE=outputs/kaggle_video_runs/recon_cache
   FLOORPLAN_RECON_CACHE_ONLY=1 uv run --extra video floorplan run <video> --tier video
   --frames 60`). The photo runs have no cache yet: rerun them on Kaggle.

## 2. After the fix, in order

1. **Real photo folders** from the friend (user is sorting them by room): run the photo
   tier on Kaggle (cache for replay), add rows to `scripts/gt_table.py`.
2. **Head-to-head** (H1): our LiDAR vs Polycam vs GT on the 4 rooms, from `gt_table.py`.
3. **Openings** (doors, windows): GT has the bedroom door 3.4 ft and window 7 ft, living
   room openings; `lintel_mask` in `plan2d.py` finds door heads. SpatialLM (seed-voted)
   is a candidate for windows.
4. **Phase 5 damage**: the bedroom hole (2.5 in, centre 4.66 ft up, 7.5 ft from the right
   wall) is the test case.
5. Phase 7: benchmark report, technical report, compliance, fresh-clone test.

## Waiting on

- User: sorted photo folders (one folder per room).
- Friend (one message, see HANDOVER): original-quality videos/photos via Drive/iCloud,
  Polycam app version + any export; optionally a 1-2 min eye-level house video.
- Architect: blind laser measurements for B → `data/gt/arkitscenes_421337.yaml`.

## Open, lower priority

- Whole-house Camera-app video fails: windows fold rooms onto each other
  (`docs/home_c_new_captures.md`). Try shorter windows, skip ceiling frames, or a new clip.
- Drift correction that does no harm (brief G5); the doubled walls above are drift too.
- B's three scans differ by up to 0.9 m in extent (fix map 02b).
