# Requirements: Cozmo AI "Applied AI" case study

Source: `Applied AI.pdf` (Aug 2026) plus Cozmo's written answers (Oct 3, 2026). This file
restates what we are building, how it is scored, and what is still unresolved. The
time-boxed plan lives in [ROADMAP.md](ROADMAP.md).

**Deadline: Monday Oct 5, 2026, 10:00 IST.**

## 1. Confirmed by Cozmo (Oct 3)

| Question | Answer | What it means for us |
|---|---|---|
| Deadline | Oct 5, 10:00 AM IST | ~46 hours from Sat 12:00 IST |
| Provided captures | Build our own pipeline with **real ground-truth measurements**; send our captures and sample results | We must capture and tape-measure real rooms ourselves |
| No iPhone Pro | Provided data may be used for the LiDAR tier | LiDAR tier uses the three Stray Scanner captures |
| JSON schema / Round 1 gates | Ignore the Round 1 references | No published schema exists: we output JSON in our own format, documented in the README; only the gates in the brief apply |
| Walk-in test | In person, on **our laptop**, no limits | Pipeline must run cold on this Mac (Apple Silicon); no time limit |
| Scope | **All three tiers working** is expected | Video and photo tiers are core, not optional |

## 2. What we are building

A pipeline that takes iPhone captures of a home and produces, with **one command per
capture**:

- a dimensioned plan per room: walls, wall lengths, ceiling height, floor area, openings
  (doors and windows)
- a stitched whole-property plan with every room placed, connected, and dimensioned
- damage regions per surface, with damage class and real-world size
- concealed-damage flags, each naming the rule that fired
- repair scope line items tied to surfaces
- a confidence interval on **every** measurement
- JSON in **our own format** (fields documented in the README), plus a rendered plan image

Three input tiers, all required, each producing the same output with honestly wider
intervals as data gets thinner:

| Tier | Input | Wall-length gate | Our data source |
|---|---|---|---|
| LiDAR | depth + poses + intrinsics | strict gates below | provided Stray Scanner captures |
| Video | handheld walkthrough clip, any iPhone 15+ | ±3% | our own capture + tape ground truth |
| Photos | 2–8 stills per room, one folder per room, no depth or poses | ±8% | our own capture + tape ground truth |

### Accuracy gates

| Gate | Pass condition |
|---|---|
| Opening widths | ≤ 2 cm on ≥ 85% of openings; a missed or phantom opening counts as a miss |
| Ceiling height | ≤ 1.5 cm per room; repeat captures within 1 cm of each other; report says whether error is bias or noise |
| Repeatability | two captures of the same room agree within 1 cm or 0.5% per wall |
| Drift | drift correction on the multi-room capture, with an on/off ablation; using poses as-is fails |
| Photo-tier stitch | per-room photo folders → one stitched plan, correct adjacency, no overlaps, footprint ±8% |

Confident but wrong output on thin input **caps the total score**, so intervals must widen
honestly at the video and photo tiers.

### Benchmark we must build (own captures)

- one multi-room capture: 3+ rooms plus a connector (hallway)
- one furnished room with staged damage spanning two damage classes
- the same rooms at the video and photo tiers (LiDAR comes from the provided data)
- at least one room captured twice at the same tier (repeatability)
- tape or laser ground truth on everything, submitted with the raw captures

## 3. Scoring

| Weight | Component | What it takes |
|---|---|---|
| **30%** | Walk-in test | They capture an unseen space with their iPhone at a tier chosen on the day; our pipeline runs cold on our laptop; scored against their laser measurements |
| **25%** | Fix loop | Name our worst gate and its number, give root cause and evidence, predict the fixed number, ship the fix with regenerable before/after runs and a diff |
| **15%** | Benchmark accuracy | Gates at all three tiers on our benchmark, reproducible by them |
| **10%** | Compliance matrix | Requirement → file → artifact → status, covering the whole spec |
| **10%** | Head-to-head | Our LiDAR output vs a consumer app on 2 rooms; beat or tie on ≥ 70% of dimensions |
| **5%** | Capture route | Install time, protocol clarity, non-engineer experience |
| **5%** | Process evidence | Commit history that shows the work being built incrementally |

Fix-loop scoring: root cause + shipped fix + gate passes = full marks; meaningful movement
short of the gate = majority marks if the report explains why; badly wrong prediction =
marks for an honest post-mortem only; analysis without a shipped fix = 0; fix without
regenerable before/after = 0.

## 4. Key design decisions

1. **One geometry backend for all tiers.** Every tier is converted to the same thing, a
   metric point cloud with camera poses, and the same floor / ceiling / wall / room code
   runs on it. LiDAR gets this from depth + odometry; video and photos get it from a
   pretrained multi-view reconstruction model. This is what makes three tiers feasible in
   two days.
2. **Capture route 2 (stock apps + one-page protocol).** LiDAR: Stray Scanner (matches the
   provided data). Video: native Camera app. Photos: native Camera app. No custom iOS app.
3. **The photo protocol requires one photo through each doorway** into the next room. The
   brief lets the protocol dictate capture ("we follow your page literally"), and the overlap
   is what lets per-room folders stitch into one plan.
4. **Intervals come from measured spread**, not guesses: plane-fit residuals and spread across
   frames for LiDAR, widened by tier-specific error measured against our tape ground truth.
5. **Own JSON output format**, documented as a field list in the README. No formal JSON
   Schema file: Cozmo said to ignore the published-schema reference, so it earns no marks.

## 5. Still open

### Ask Cozmo (follow-up)

1. **Hosted model APIs:** not answered. May the pipeline call a hosted vision model (e.g.
   for damage classification), with disclosure? Walk-in runs on our laptop with no limits,
   so we assume internet is available; we will keep a local fallback either way.
2. **Head-to-head:** not answered. It needs the same rooms scanned by our LiDAR pipeline and
   by Polycam/magicplan, but our LiDAR data is the provided apartment, which we can't
   re-scan. Options: (a) they share a Polycam/magicplan export of that apartment, (b) we
   compare at the video tier against an app on our own rooms, (c) mark as not possible.
3. **Ground truth for the provided captures:** do they have measurements for that
   apartment? Without them, the LiDAR tier can be scored for repeatability (three captures)
   but not absolute accuracy.
4. **Walk-in at the LiDAR tier:** which capture app will their Pro iPhone use? We assume they
   install Stray Scanner per our protocol.

### Decide ourselves (good-to-have answers, defaulted for now)

| Topic | Our default |
|---|---|
| Damage classes | crack, water stain, mould, hole, peeling paint |
| Concealed-damage rules | own rule table (e.g. ceiling stain → possible leak above) |
| Scope line items | item, surface id, quantity, unit; no pricing |
| Interval coverage | 90% intervals, calibration reported as empirical coverage |
| Wall length | corner to corner on the interior face |
| Floor area | net visible floor polygon (gross under fixed cabinets) |
| Opening width | inside the frame; open passages count as openings |
| Mirrors, glass, wet surfaces, low light | handle where possible, otherwise documented as known failure modes |
