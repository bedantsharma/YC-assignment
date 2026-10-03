# Requirements: Cozmo AI "Applied AI" case study (Round 2)

Source: `Applied AI.pdf` (Aug 2026). This file restates what we are building, how each part
is scored, the order we will tackle it in, and the open questions for Cozmo.

## 1. What we are building

A pipeline that takes iPhone captures of a home and produces, with **one command per
capture**:

- a dimensioned plan per room: walls, wall lengths, ceiling height, floor area, openings
  (doors and windows)
- a stitched whole-property plan with every room placed, connected, and dimensioned
- damage regions per surface, with damage class and real-world size
- concealed-damage flags, each naming the rule that fired
- repair scope line items tied to surfaces
- a confidence interval on **every** measurement
- JSON in Cozmo's published schema, plus a rendered plan image

It must work at three input tiers, each producing the same output with honestly wider
intervals as data gets thinner:

| Tier | Input | Wall-length gate |
|---|---|---|
| LiDAR | depth + poses + intrinsics (Pro iPhones) | strict gates below |
| Video | handheld walkthrough clip, any iPhone 15+ | ±3% |
| Photos | 2–8 stills per room, one folder per room, no depth or poses | ±8% |

### Accuracy gates (Round 2 additions)

| Gate | Pass condition |
|---|---|
| Opening widths | ≤ 2 cm on ≥ 85% of openings; a missed or phantom opening counts as a miss |
| Ceiling height | ≤ 1.5 cm per room; repeat captures within 1 cm of each other; report says whether error is bias or noise |
| Repeatability | two captures of the same room agree within 1 cm or 0.5% per wall |
| Drift | drift correction on the multi-room capture, with an on/off ablation; using poses as-is fails |
| Photo-tier stitch | per-room photo folders → one stitched plan, correct adjacency, no overlaps, footprint ±8% |

Confident but wrong output on thin input **caps the total score**.

## 2. Scoring

| Weight | Component | What it takes |
|---|---|---|
| **30%** | Walk-in test | They capture an unseen space with their own iPhone at a tier chosen on the day; our pipeline runs cold in front of them and is scored against their laser measurements |
| **25%** | Fix loop | Name our worst gate and its number, give root cause and evidence, predict the fixed number, ship the fix with regenerable before/after runs and a diff |
| **15%** | Benchmark accuracy | Gates at all three tiers on our own benchmark, reproducible by them |
| **10%** | Compliance matrix | Requirement → file → artifact → status, covering the whole spec |
| **10%** | Head-to-head | Our LiDAR output vs a consumer app (Polycam, magicplan) on 2 rooms; beat or tie on ≥ 70% of dimensions |
| **5%** | Capture route | Install time, protocol clarity, non-engineer experience |
| **5%** | Process evidence | Commit history that shows the work being built incrementally |

Fix-loop scoring detail: root cause + shipped fix + gate passes = full marks; meaningful
movement short of the gate = majority marks if the report explains why; badly wrong
prediction = marks for an honest post-mortem only; analysis without a shipped fix = 0; fix
without regenerable before/after = 0.

## 3. Plan: easiest marks first

Our constraints: no iPhone Pro, a short deadline, and three Stray Scanner LiDAR captures of
one multi-room apartment (no ground-truth measurements). Order is by marks per hour of work
given those constraints. "Feeds" shows which scoring rows a step contributes to.

| # | Step | Feeds | Difficulty | Needs |
|---|---|---|---|---|
| 1 | Commit small and often from now on | Process 5% | Easy, ongoing | nothing |
| 2 | Compliance matrix skeleton, updated as we go | Compliance 10% | Easy | nothing |
| 3 | Capture protocol (Route 2: Stray Scanner, the app the provided data came from) + device matrix | Capture route 5% | Easy | nothing |
| 4 | LiDAR single-room plan: floor/ceiling planes, walls, wall lengths, floor area, JSON + rendered plan, one command | Walk-in 30%, Benchmark 15% | Medium | provided data |
| 5 | Confidence intervals on every number (spread across frames / plane-fit residuals) | Walk-in, Benchmark, avoids score cap | Medium | step 4 |
| 6 | Repeatability: same walls measured across the three captures | Benchmark 15% | Easy once 4 works | step 4 |
| 7 | Fix loop on our worst measured gate (likely repeatability or ceiling height) | Fix loop 25% | Medium | steps 4–6 |
| 8 | Drift correction (plane-anchored / Manhattan snapping) + on/off ablation | Benchmark 15% | Medium | multi-room capture |
| 9 | Stitched multi-room plan with adjacency | Walk-in, Benchmark | Hard | step 8 |
| 10 | Openings (door and window widths) | Benchmark gate, Walk-in | Hard | step 4 |
| 11 | Video tier: frames from `rgb.mp4`, no depth, multi-view reconstruction model | Benchmark, Walk-in | Hard | step 4 as reference |
| 12 | Photo tier: 2–8 stills per room, stitched | Benchmark, Walk-in | Hardest | step 11 |
| 13 | Damage regions, concealed-damage rules, scope line items | Compliance, Walk-in | Medium (vision model) | staged-damage capture |
| 14 | Head-to-head vs Polycam | Head-to-head 10% | Blocked | iPhone Pro + same rooms |
| 15 | Technical report (≤ 6 pages), benchmark report, reproduction bundle | All | Medium | everything above |

Steps 1–7 are the core target. Everything after is attempted only if time allows, and
anything missing is marked honestly in the compliance matrix.

## 4. Gaps and questions for Cozmo

Ranked by how much the answer changes what we build. The first block is ready to paste.

### Must ask

1. **Deadline:** what is the exact submission deadline (date, time, timezone)?
2. **Provided data:** the brief says "we provide no captures", but we received three
   Stray Scanner captures of one apartment. Are these for development only, or part of the
   evaluation? Do you have tape or laser measurements for them?
3. **Hardware:** I don't have an iPhone Pro. Can the provided captures stand in for my own
   LiDAR benchmark, and how should I handle the head-to-head (which needs the same rooms
   scanned in Polycam or magicplan)?
4. **Output schema:** the brief says "JSON to the published schema" but no schema is
   attached. Can you share it?
5. **Round 1 gates:** the brief says Round 1 gates apply plus five additions, but the Round 1
   gates aren't in the document. Which metrics and thresholds are they (wall length, floor
   area, ...)?
6. **Walk-in test logistics:** in person or remote? Does the pipeline run on my laptop or
   yours? Is internet access allowed during the run, and is there a time limit?
7. **Third-party APIs:** "everything runs without calling your infrastructure". Does that
   allow hosted model APIs (e.g. a vision-language model for damage) with disclosure, or must
   everything run locally?
8. **Scope expectations:** given the timeline, is a strong LiDAR tier with honest gaps
   elsewhere acceptable, or are all three tiers expected to be functional?

### Good to clarify

9. **Damage classes:** which taxonomy (crack, water stain, mold, hole, ...)? Is there a
   reference list?
10. **Concealed-damage rules:** do you have expected rules, or do we define our own?
11. **Scope line items:** what fields (item, quantity, unit)? Any pricing catalog or codes
    (e.g. Xactimate), or quantities only?
12. **Confidence intervals:** what coverage level (e.g. 90% or 95%)? How is calibration
    scored?
13. **Measurement definitions:** wall length corner-to-corner on the interior face? Floor
    area net or gross (under cabinets)? Ceiling height for sloped ceilings or soffits?
    Opening width measured inside the frame? Do open passages without doors count as
    openings?
14. **Photo tier:** may our capture protocol dictate how photos are taken (e.g. one photo
    through each doorway to help stitching), or must any 2–8 photos work?
15. **Walk-in space:** single room or multi-room? Furnished? Will it include mirrors, glass
    or low light?
16. **"Cover them" for mirrors, glass, wet surfaces, low light:** handle them, or document
    them as known failure modes?
17. **Submission format:** repo visibility (public or private, who to invite)? Report as PDF?
18. **Defense:** date, length, format.
19. **Compliance matrix:** is partial status given partial credit?
