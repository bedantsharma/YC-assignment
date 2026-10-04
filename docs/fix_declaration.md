# Fix declaration: our walls stop at the innermost surface

The brief's single fix-loop declaration (F1–F5). Written and committed **before** the fix;
the result section is added after. Before: tag `fixloop-before` (= `19059e0`). After: tag
`fixloop-after`. Full fix-loop record: [fix_loop.md](fix_loop.md).

## 1. Failing number

Home C against the ground truth (`data/gt/home_c.json`: architect's drawing, interior clear
dimensions; ceilings 11 ft). `uv run scripts/compare_gt_c.py` at `fixloop-before`:

| Room | Ground truth (m) | Our LiDAR (m) | Error long / short (cm) | Area vs GT | GT inside our area interval? |
|---|---|---|---|---|---|
| Kitchen | 3.66 × 3.05 | 3.20 × 2.72 (`c_home_01`) | −45 / −33 | −30% | no |
| Dining & living | 5.71 × 5.49 | 5.52 × 4.95 (`c_home_01`) | −20 / −53 | −24% | no |
| Drawing | 4.57 × 3.66 | 4.24 × 3.53 (`c_home_01`) | −33 / −13 | −11% | no |
| Bedroom (damage room) | 4.57 × 3.35 | 4.46 × 3.21 (`c_home_01`) | −11 / −14 | −13% | no |
| | | 4.24 × 3.30 (`c_damage_01`) | −33 / −6 | −14% | no |
| | | 4.26 × 3.08 (`c_damage_02`) | −31 / −27 | −19% | no |

**Every side is short (median 29 cm, worst −53 cm) and the truth is outside our interval
in all 6 room measurements.** Polycam, on the same home, is 6 cm off (median). Ceilings
are already within 1 cm. This is the worst failing number we have: it decides every wall
length and area on all three tiers and loses the head-to-head (H1) against Polycam.

## 2. Root cause and evidence

`gt_table.py` shows every method that goes through our plan builder is short, on all
three tiers and with every reconstruction model; only SpatialLM (its own wall finder) is
not. So the cause is in the shared backend, not the sensor. Traced per wall with
`uv run scripts/diag_walls.py` (every surface behind each output edge, with its height
range and coverage):

1. **A wall is a thick smear, and we snap to its inner edge.** In `c_damage_01` the two
   long walls are a dense band of points 40 cm thick, full height (0.3–3.1 m), along
   100% of the wall: pose drift, the same wall seen at different offsets on different
   passes. `rooms._snap_to_surface` moves each edge to the *first* histogram bin with
   ≥ 30% of the peak, i.e. the band's inner edge. The ground truth needs +0.33 m on that
   axis, which is where the **middle** of both bands lies (+0.16 / +0.17 m from our edges).
   Drift correction (`--drift`) does not remove the bias: rooms are still 10–55 cm short
   with it on (checked on all three home-C scans).
2. **Furniture counts as wall.** The free-space outline stops at the first obstacle. In
   the kitchen the upper cabinets (1 ft deep, tape) are a surface from 0.9 to 2.3 m, the
   wall behind them at +0.37 m goes to the ceiling, and the snap takes the cabinet. In B
   (`42444946`) a 1.8 m-tall piece of furniture stands 0.6 m in front of a wall. Wardrobes
   and cabinets end at or below ~2.3 m; walls continue to the ceiling.

The two have one remedy: measure the wall where only the wall is, **above 2.3 m** (above
door heads at 1.98 m and the tallest furniture), and take the **centre** of the smear
there, not its inner edge.

Rules tested offline on the home-C clouds before choosing (errors vs ground truth,
long / short, cm):

| Room (scan) | Current | Median of the 0.1–2.3 m wall band | Median above 2.3 m | Above 2.3 m, own side only (chosen) |
|---|---|---|---|---|
| Bedroom (`c_damage_01`) | −33 / −6 | +9 / −4 | +5 / +3 | +5 / +3 |
| Bedroom (`c_damage_02`) | −31 / −27 | +8 / −1 | +9 / +3 | +9 / +3 |
| Dining & living | −20 / −53 | +0 / −29 | −7 / −12 | −7 / −22 |
| Kitchen | −45 / −33 | −32 / +18 | −4 / +13 | −5 / 0 |
| Drawing | −33 / −13 | −1 / +5 | +3 / +4 | −6 / 0 |
| Bedroom (`c_home_01`) | −11 / −14 | +7 / −3 | −4 / +9 | −4 / −5 |

"Own side only" drops points nearer to another room's floor than to this room's: on an
interior wall the far face belongs to the neighbour (seen at +0.25 m behind the bedroom /
drawing wall). It is chosen for that physical reason, not for the score: overall it ties
with "above 2.3 m" (median 5 cm either way); it is better on the kitchen and bedroom, and
worse on the dining & living room, whose west wall was never scanned (fix map 01c).

## 3. The fix

In `rooms.measure_room`, for each outline edge, when the room's ceiling was measured:

- take the points within the edge's span (corners trimmed, as now), from 0.15 m inside to
  0.5 m outside the free-space edge, **between 2.3 m above the floor and 0.3 m under the
  ceiling** (clear of cornices and of the ceiling itself), and **nearer to this room's free
  space than to any other room's**;
- if there are at least 100, the wall goes to their **median** offset, and its sigma is
  their spread (1.4826 × MAD), so a smeared wall gets a wide interval;
- otherwise (no ceiling, as in A's `1a8384c3f6` and `c00a170fe1`, or too few points high
  up) the current nearest-face snap is kept unchanged.

## 4. Predicted numbers (from the offline run of exactly this rule; ±3 cm for implementation details)

| Room (scan) | Predicted (m) | Error long / short (cm) | Area (m²) [90%] | GT 15.3 / 31.4 / 11.1 / 16.7 inside? |
|---|---|---|---|---|
| Bedroom (`c_damage_01`) | 4.62 × 3.39 | +5 / +3 | 14.9 [13.8, 16.1] | in |
| Bedroom (`c_damage_02`) | 4.67 × 3.38 | +9 / +3 | 15.0 [13.8, 16.2] | in |
| Dining & living | 5.64 × 5.26 | −7 / −22 | 25.1 [23.8, 26.3] | **out** (unscanned west wall, notches) |
| Kitchen | 3.61 × 3.04 | −5 / 0 | 10.2 [9.8, 10.7] | **out** |
| Drawing | 4.51 × 3.66 | −6 / 0 | 16.5 [15.4, 17.5] | in |
| Bedroom (`c_home_01`) | 4.53 × 3.30 | −4 / −5 | 13.9 [13.4, 14.4] | **out** |

- LiDAR median absolute wall error **29 cm → ≈ 5 cm**; worst −53 → −22 cm (dining, an
  unscanned wall). Truth inside the area interval: **0 of 6 → 3 of 6**. The ground-truth
  areas are nominal rectangles; the bedroom's closet and the drawing room's pooja niche
  make the real floor smaller, so the area check is harsher than the extent check.
- Ceilings unchanged (the levels code is untouched).
- Repeat scans of the bedroom: long sides 4.24 / 4.26 → 4.62 / 4.67 (5 cm apart),
  short 3.30 / 3.08 → 3.39 / 3.38 (21 → 1 cm apart).
- **Other captures** (`uv run scripts/lidar_summary.py`):
  - A `1a8384c3f6`, `c00a170fe1`: no ceiling captured → **unchanged**.
  - A `c7d28f72c6`: room areas move by < 1 m² each, room count unchanged. Unverified (no
    ground truth for A).
  - B (one room, 3 scans): **grows 1.2–2.2 m²** (15.0 / 15.0 / 14.8 → ≈ 17.2 / 16.4 /
    16.0), mostly where furniture stood in front of a wall. The three scans will agree
    *less* on area (spread 0.2 → ≈ 1.2 m²) because their free-space outlines already
    differ (fix map 02b). Unverified until B's laser measurements arrive. This is the
    known risk of the fix.
- Video tier (replayed from the Kaggle cache, no model run): the 60-frame damage-room
  plans move from ≈ −30 cm toward the truth, within ±15 cm. Photo tier: no cache; not
  rerun here.

## 5. Result

*(after the fix: filled in from `uv run scripts/gt_table.py`, `scripts/compare_gt_c.py`,
`scripts/lidar_summary.py`; wrong predictions reported as such)*
