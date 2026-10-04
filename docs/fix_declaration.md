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

## 5. Result (commit `c69216d`)

### LiDAR tier: as predicted

`uv run scripts/compare_gt_c.py`:

| Room (scan) | Before (m) | After (m) | Error after, long / short (cm) | Predicted | Area after [GT inside?] |
|---|---|---|---|---|---|
| Kitchen | 3.20 × 2.72 | 3.58 × 3.05 | −8 / 0 | −5 / 0 | 10.3 (−8%), out |
| Dining & living | 5.52 × 4.95 | 5.64 × 5.26 | −7 / −22 | −7 / −22 | 25.1 (−20%), out |
| Drawing | 4.24 × 3.53 | 4.51 × 3.65 | −6 / −1 | −6 / 0 | 16.5 (−1%), **in** |
| Bedroom (`c_home_01`) | 4.46 × 3.21 | 4.53 × 3.30 | −4 / −5 | −4 / −5 | 13.9 (−9%), out |
| Bedroom (`c_damage_01`) | 4.24 × 3.30 | 4.62 × 3.39 | +5 / +3 | +5 / +3 | 14.9 (−2%), **in** |
| Bedroom (`c_damage_02`) | 4.26 × 3.08 | 4.67 × 3.38 | +9 / +3 | +9 / +3 | 15.0 (−2%), **in** |

- **Median absolute wall error 29 → 5 cm** (Polycam: 6 cm); worst −53 → −22 cm (the dining
  & living room's unscanned west wall). Truth inside the area interval: 0 → 3 of 6.
- Repeat scans of the bedroom: short side 21 → 1 cm apart, long side 2 → 5 cm apart.
- Ceilings unchanged (1 cm).
- All 9 captures (`uv run scripts/lidar_summary.py`): A `1a8384c3f6` and `c00a170fe1`
  unchanged; A `c7d28f72c6` 11.2 7.0 13.5 10.9 10.6 → 10.9 7.0 13.9 11.7 11.1 m² (each
  < 1 m², unverified); B 15.0 / 15.0 / 14.8 → 17.2 / 16.4 / 16.0 m², exactly as predicted,
  including the predicted loss of agreement between B's scans (unverified until B's laser
  measurements arrive).

### Video tier: prediction wrong

Replayed from the Kaggle cache: the damage-room plans barely moved (60 frames: 4.21 × 3.11
→ 4.27 × 3.14 and 4.24 × 3.08 → 4.26 × 3.12; still ≈ −30 / −22 cm). Predicted: within
±15 cm. Why: Pi3X's clouds are not smeared like the LiDAR's (one reconstruction, no drift),
so the geometry fix has little to move. The video tier is short for another reason: its
**horizontal scale correction was measured against our LiDAR** (`intervals.SCALE_BIAS`,
video / LiDAR on the damage room, `docs/video_scale.md`), and that LiDAR was 7–8% short.
The correction copied the LiDAR's error into the video tier.

## 6. Follow-up (declared before applying): re-measure the video scale bias

**Fix.** Re-derive `SCALE_BIAS` horizontal with the same documented procedure (Pi3X and
MapAnything Kaggle runs on the damage room, `uv run scripts/video_scale.py
outputs/bakeoff/c_damage_0*__*.npz outputs/video_eval/*.npz`, mean of longest wall and
√area), now against the corrected LiDAR:

| Model | Horizontal before | Horizontal now | Vertical (unchanged) |
|---|---|---|---|
| Pi3X (video and photo) | 0.964 | **0.890** | 0.914 (video), 0.930 (photo) |
| MapAnything (video and photo) | 0.935 | **0.877** | 1.035 |

**Predicted** (Camera-app damage-room clips; every horizontal length × 0.964 / 0.890 =
1.083):

| Clip | Now (m) | Predicted (m) | Predicted error long / short (cm) |
|---|---|---|---|
| v1, 60 frames | 4.27 × 3.14 | 4.62 × 3.40 | +5 / +5 |
| v2, 60 frames | 4.26 × 3.12 | 4.61 × 3.38 | +4 / +3 |
| v1, 30 frames | 4.41 × 3.24 | 4.78 × 3.51 | +21 / +16 |
| v2, 30 frames | 4.20 × 3.01 | 4.55 × 3.26 | −2 / −9 |

Video-tier median absolute wall error on these clips ≈ 30 → ≈ 5 cm; ceilings unchanged.
**This is in-sample:** the bias is fitted on the damage room, where the LiDAR now matches the
truth, so the damage-room clips agree by construction. The held-out evidence is weaker:
across the home's other rooms (Pi3X, chained 90-frame run) the horizontal ratio ranges
0.80–0.99, so a single bias leaves up to ±10% per room (drawing room ≈ +10% after
correction). Those rooms need the `c_home_01` video rerun on Kaggle (no replay cache).

### Follow-up result (commit `d5b2de1`): as predicted

| Clip | Predicted error (cm) | Measured error long / short (cm) | Area | Ceiling (unchanged) |
|---|---|---|---|---|
| v1, 60 frames | +5 / +5 | **+6 / +6** | 14.4 m² (−6%) | 3.48 m (+13 cm) |
| v2, 60 frames | +4 / +3 | **+5 / +4** | 14.9 m² (−3%) | 3.32 m (−3 cm) |
| v1, 30 frames | +21 / +16 | +20 / +16 | 16.0 m² (+4%) | 3.50 m (+14 cm) |
| v2, 30 frames | −2 / −9 | −2 / −9 | 14.2 m² (−8%) | 3.30 m (−5 cm) |

Camera-app damage-room clips: median absolute wall error 30 → 6 cm (in-sample, see above).
The video tier's summary row in `docs/gt_comparison.md` (median 13 cm) still includes the
`c_home_01` video plan from before the fix: it has no replay cache and needs a Kaggle rerun
(as do the photo-tier rows, marked "pre-fix geometry"). A photo-tier test fixture fed the
tier an unbiased cloud and broke once the correction grew (a 0.9 m door became 1.01 m and
the rooms merged); it now feeds a biased cloud, as a model would.

## 7. Where this leaves the gate

- **LiDAR vs ground truth: median 5 cm, mean 6 cm, Polycam 6 / 6 cm.**
- **Head-to-head (H1/H3), our `c_home_01` scan vs Polycam, 8 room dimensions, beat or tie
  at Polycam's 1 cm precision: 6 of 8 (75%), target ≥ 70%: met** (`uv run
  scripts/gt_table.py`, last section). Won: kitchen both (8 vs 9, 0 vs 1 cm), dining long
  (8 vs 12), drawing short (1 vs 7), bedroom short (5 vs 8); tied: bedroom long (4 vs 4).
  Lost: dining short (23 vs 3 cm, the unscanned west wall), drawing long (6 vs 4). Before
  the fix: 0 of 8. Caveat: which of the dining room's 18'9" / 18' labels is which side is
  read from the sort order (long / short), as for every room.
- Still failing: the dining & living room's short side (−22 cm, a wall never scanned) and
  area intervals that miss the truth in 3 of 6 rooms (the truth's areas are nominal
  rectangles; the intervals are not calibrated yet, fix map 03).
- Unverified side effects: B's room grows 1.2–2.2 m² and its scans agree less (fix map 02b).

Regenerate: `git checkout fixloop-before` / `fixloop-after`, then `uv run
scripts/lidar_summary.py && uv run scripts/compare_gt_c.py && uv run scripts/gt_table.py`
(video rows: replay the Kaggle cache, NEXT-SESSION §1.6).
