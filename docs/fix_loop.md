# Fix loop log

Each entry follows the brief's fix-loop discipline: the failing number, the root cause with
evidence, the fix, and a **predicted** number, all written and committed **before** the fix.
The before and after runs are regenerable from git tags. The entry submitted as the brief's
single fix-loop declaration is chosen in Phase 6 (worst gate); entries here are the full
record.

## Fix map

Work top to bottom. Every fix must leave all 9 LiDAR captures no worse
(`uv run scripts/lidar_summary.py`), not just the capture it targets.

| # | Problem | Seen on | Cause | Fix | Status |
|---|---|---|---|---|---|
| 01a | Hall and room 2 merged through a 1.2 m doorway | C `c_home_01` | Rooms split only at openings < 0.9 m | Door lintels split rooms (kept out of the enclosure test) | **Done** (`fix01-after`) |
| 01b | Kitchen cut off at the counter front | C `c_home_01` | Counter front (0.1–1.1 m) passes the wall test | First try, "walls reach 1.5 m", **broke A** (low scans); replaced by the counter's shape (face capped by a hollow-under top at 0.82–1.05 m) | **Done** (`fix01-after`) |
| 01c | Hall's north-west corner cut off as its own room | C `c_home_01` | 2.7 m of the hall's west wall has **zero points at any height**; rays leak west, the strip fails enclosure (0.62 < 0.75) and the hall splits in two | Seen floor that fails enclosure is attached (≤ 1 m deep) to the room it borders as a **low-confidence zone**; rooms touching along > 2 m with no wall or lintel merge | **Done** (`fix01c-after`) |
| 02 | Two scans of the damaged room disagree: walls by 3–15 cm, ceiling by 8.8 cm | C `c_damage_01/02` | Not traced yet | Trace first (Phase 3) | Open (repeatability gate) |
| 03 | Intervals overconfident: ±3 cm ranges that don't overlap between repeat scans | C damage room | Intervals from surface spread only, no capture-to-capture error | Calibrate against repeats and ground truth (Phase 6) | Open |
| 04 | Wardrobes, fridges, bookshelves count as walls; rooms shrink | A, C | Tall furniture passes the wall test | Detector boxes (Phase 5 shared detector) remove them from walls | Open |
| 05 | Spurious 0.3–0.5 m steps in walls | A | Clutter touching a wall bends the outline | Trace first | Open |
| 06 | Open-plan spaces split arbitrarily | A | Watershed meets wherever the seeds touch | Trace first; lintels (01a) may cover part | Open |
| 07 | Floor-to-ceiling opening into unscanned space notches a room | synthetic | Outline follows the observed edge | Trace first | Open |
| 08 | Ceilings of 2.3–2.4 m in two A rooms | A `c7d28f72c6` | Real lowered ceiling, or a cabinet top? | Check against the video | Open |

## Fix 01c: hall cut off at an unscanned wall (declared before fixing)

Before: `fix01-after` (= tag `fix01c-before`). `c_home_01`: 5 rooms; hall r3 16.7 m²,
IoU 0.59; fragment r1 4.2 m² unmatched. Evidence and fix: fix map row 01c.

Predicted after: `c_home_01` **4 rooms**, no fragment; hall ≈ 21–25 m², IoU ≥ 0.7, with a
low-confidence zone of ≈ 2–4 m² named in the warnings and the hall's area interval
widened by it. Other 8 captures: B and C damage unchanged; A may merge rooms that touch
along > 1.2 m with no wall (open plan), each to be checked by eye.

Result (after: tag `fix01c-after`): **as predicted.** `c_home_01` 4 rooms, no fragment;
hall r1 23.8 m² (interval 20.5–24.1), IoU 0.79, of which 2.9 m² low confidence (in
`rooms[].low_confidence_area`, the warnings and the plan label). B, C damage and
`c7d28f72c6` unchanged; `1a8384c3f6` unchanged; `c00a170fe1` r1 10.0 → 12.8 m², the extra
2.5 m² flagged low confidence (floor seen, walls never seen; capped at 1 m).

Found while fixing, before claiming the result (each caught by the 9-capture check):

1. First version attached any unenclosed observed cell: B gained 2.1 m² outside the room
   (through a door, only 10% of it real floor) and `c00a170fe1` a 3 m wedge. Added: floor
   must have been seen, and a zone reaches at most 1 m past its room.
2. A 1.2 m merge threshold merged two A rooms joined by a ~1.5 m open passage. Raised to
   2.0 m (wider than any doorway or open passage), not fitted to these captures.
3. Merging before attaching left the fragment: it only touches the hall along a long
   boundary once the strip between them is attached. Now attach, then merge.
4. Renumbering labels with `np.unique` mapped room 1 to 0 when no cell was outside every
   room; caught by a unit test.

## Fix 01: room segmentation on the friend's whole-home scan (C, `c_home_01`)

Status: **shipped.** Before: tag `fix01-before`. After: tag `fix01-after`.
Regenerate either: `git checkout <tag> && uv run scripts/lidar_summary.py && uv run scripts/score_rooms.py`.

### Failing number

Rooms found on `c_home_01`, scored against the user's hand labels of the home
(`data/gt/home_c_rooms.json`: hall, kitchen, room 1, room 2; identity and rough extent only):

```
uv run floorplan run data/home_c/lidar/c_home_01 && uv run scripts/score_rooms.py
```

| Labelled room | Detected | IoU | Result |
|---|---|---|---|
| room1 | r4, 13.6 m² | 0.77 | found |
| kitchen | r2, 8.5 m² | 0.60 | found, but cut off at the counter front |
| room2 | r3, 30.1 m² | 0.47 | missed: **r3 is the hall and room 2 merged** |
| hall | r1, 4.2 m² | 0.11 | missed: r1 is a fragment of the hall |

**ROOMS FOUND: 2/4.** A room is found at IoU ≥ 0.5 (one-to-one matching). Target: 4/4,
no merged rooms. This is not one of the brief's numbered gates, but it decides every
per-room number (walls, area, ceiling, adjacency) on a multi-room walk-in capture.

### Root cause and evidence

Three causes, found by tracing each stage's mask (floor hits, wall cells, observed,
enclosure, distance-transform seeds, labels) and the raw point heights, then checking the
video frames. The first hypothesis (counter tops raise the floor estimate) was **wrong**:
the floor is fitted once for the whole home, so counters cannot move it.

1. **Hall and room 2 merge through a 1.2 m doorway (code).** The partition at u ≈ 3.9 m
   has a gap from v ≈ -2.8 to -1.6 m: zero points between 1.0 and 1.9 m height in every
   10 cm of it, a lintel from ~1.9–2.0 m up, wall above to the ceiling. Room seeds are
   free space more than `DOOR_HALF_WIDTH_M` = 0.45 m from any wall, i.e. the code assumes
   doors are at most 0.9 m wide. A 1.2 m opening leaves a seed corridor through the door,
   so both rooms grow from one seed.
2. **Kitchen counter front classified as wall (code).** A cell is a wall if its points
   span ≥ 0.8 m of height in 0.1–2.3 m. Across the kitchen (v ≈ -5.1) the base-cabinet
   front at u ≈ 1.3–1.4 m has points in 0.1–1.1 m (10 slices): it passes. The tiled wall
   behind the counter (seen in the video) is at u ≈ 2.0 m, with points from 0.8 to 2.3 m.
   The kitchen's east wall is drawn at the counter front, ~0.7 m inside the real wall.
3. **Hall west strip not captured (capture).** From u ≈ -1.2 to -0.6 m there are 20–180
   floor points per column (vs ~1,800 mid-hall) and nothing at 0.3–2.0 m, only ceiling.
   *Corrected after a closer trace (fix map 01c):* the west wall itself has no points at
   any height for 2.7 m, so the strip fails the enclosure test, not the observed test, and
   the hall's north-west corner is cut off as `r1`. The
   friend's walk did not sweep that side down to the floor, which the capture checklist
   asks for ("sweep each wall top to bottom"). Causes 1 and 2 are independent of this:
   no capture would fix them.

### Fix (causes 1 and 2; cause 3 is out of scope for this entry)

1. **Door lintels split rooms.** Cells with points just below door-top height
   (2.0–2.3 m) and none at 0.5–1.8 m are a lintel over an opening. Treat them as a barrier
   when seeding and growing rooms (not when measuring walls). Open-plan junctions without
   a lintel still merge, which is correct.
2. **A wall must reach above counter height.** Wall cells also need points above ~1.5 m.
   Counters, sofa backs and table edges drop out. Window walls still pass (wall above the
   window head); wardrobes and fridges still count as walls (known limitation).

Each gets a failing synthetic test first (two rooms joined by a 1.2 m doorway with a
lintel; a room with a base cabinet along one wall).

### Predicted numbers

- `c_home_01`: **ROOMS FOUND 4/4**, no merged rooms. Hall IoU ≈ 0.55–0.65 (its west strip
  is still missing, cause 3); `r1` stays as one unmatched fragment.
- Kitchen east wall moves from u ≈ 1.3 to ≈ 2.0 m; kitchen area from 8.5 to ≈ 10.5 m².
  Its IoU against the hand box may drop slightly, since the hand box stops at u = 1.65.
- Other captures (regression check, `uv run scripts/lidar_summary.py`): B unchanged (one
  room); A's room counts may change only where a doorway wider than 0.9 m has a lintel.

### Baseline on every LiDAR capture (before)

`uv run scripts/lidar_summary.py` at `fix01-before`:

| Capture | Rooms | Areas (m²) | Ceilings (m) |
|---|---|---|---|
| 1a8384c3f6 | 5 | 11.9 8.3 3.4 16.3 13.3 | - - - - - |
| c00a170fe1 | 3 | 8.1 2.9 3.9 | - - - |
| c7d28f72c6 | 6 | 14.0 4.6 2.8 12.0 13.4 10.5 | 2.98 2.38 2.28 3.08 3.08 3.07 |
| 42444946 | 1 | 15.0 | 3.05 |
| 42444949 | 1 | 15.0 | 3.05 |
| 42444950 | 1 | 14.8 | 3.05 |
| c_damage_01 | 1 | 12.9 | 3.36 |
| c_damage_02 | 1 | 12.4 | 3.45 |
| c_home_01 | 4 | 4.2 8.5 30.1 13.6 | 3.28 3.37 3.38 3.47 |

### Result

**ROOMS FOUND: 2/4 → 4/4, no merged rooms** (target met).

| Labelled room | Before | After |
|---|---|---|
| hall | r1, 4.2 m², IoU 0.11, missed | r3, 16.7 m², IoU 0.59, found |
| room2 | r3 (merged with hall), 30.1 m², IoU 0.47, missed | r4, 14.9 m², IoU 0.85, found |
| room1 | r4, 13.6 m², IoU 0.77 | r5, 13.3 m², IoU 0.76 |
| kitchen | r2, 8.5 m², IoU 0.60 | r2, 7.8 m², IoU 0.60 |
| fragments | none | r1, 4.2 m² (hall's unscanned north-west corner, cause 3) |

Against the predictions:

- **4/4, no merges: as predicted.** Hall IoU 0.59, inside the predicted 0.55–0.65; the
  `r1` fragment remains, as predicted (cause 3 is a capture gap, fix map 01c).
- **Kitchen area: prediction wrong.** Predicted ≈ 10.5 m², got 7.8 m². The east wall did
  move from the counter front to the tiled wall (u ≈ 1.7–2.0 m), but the "before" 8.5 m²
  also contained a strip of the hall (v ≈ -3.7 to -2.6 m) that the hall now owns. The
  prediction added the counter strip without subtracting that.

What went wrong on the way (both caught by the 9-capture check, before committing a
result):

1. **"Walls must reach 1.5 m" broke dataset A.** In `c00a170fe1` 99% of points are below
   1.69 m (the phone never pointed up), so real walls failed it: 3 rooms → 0, and
   `1a8384c3f6` 5 → 3. Replaced by the counter's shape, with a test that a wall scanned
   only to 1.3 m survives.
2. **Lintels inside the enclosure test made a phantom room** in B (`42444946`, +3.4 m²)
   and merged rooms in `c7d28f72c6`: rays stopped at lintels, so floor seen through doors
   looked enclosed. That side effect had also inflated the hall to 24 m² (IoU 0.78), which
   would have overstated this fix. Lintels now only split rooms.

### After on every LiDAR capture

| Capture | Rooms before → after | Verdict |
|---|---|---|
| B `42444946`, `42444949`, `42444950` | 1 → 1, areas within 0.4 m² | unchanged |
| C `c_damage_01`, `c_damage_02` | 1 → 1, 12.9 → 13.1, 12.4 → 12.4 m² | unchanged |
| C `c_home_01` | 4 (2 right) → 5 (4 right + 1 fragment) | improved |
| A `c00a170fe1` | 3 → 2: a 2.9 m² sliver in a notch of r1 joins r1 | plausible, unverified |
| A `c7d28f72c6` | 6 → 5: the 2.8 m² "room" with a 2.28 m ceiling is gone; two boundaries move ~1 m | plausible, unverified |
| A `1a8384c3f6` | 5 → 6: a 13.3 m² room splits 7.0 + 5.8 at a lintel | plausible, unverified |

A has no ground truth or labels, so its changes are judged by eye from the plans, not
scored. They should be checked against A's video before the benchmark.
