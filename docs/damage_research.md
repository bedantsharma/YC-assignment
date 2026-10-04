# Damage detection: research notes

Research for the damage part of the brief (Oct 4, about 15 h before the deadline). No code
was changed and no model was run on the laptop. Every claim has a source link. Lines marked
**(own)** are our own engineering judgement, not a sourced fact.

## Summary

1. No off-the-shelf model covers all five classes zero-shot with a published accuracy on
   interior walls. The best zero-shot evidence is a 2026 building-defect benchmark. Gemini-3
   classifies defects well (recall 0.97) but localises them poorly (detection F1 0.42).
2. Recommended: a hosted VLM (Gemini) finds and labels damage per keyframe as boxes. A small
   local segmenter (SAM 2.1 tiny, 111 MB) turns each box into a mask. Our own geometry
   projects the mask onto the wall plane.
3. Offline fallback: Florence-2-base (0.23B, MIT) open-vocabulary boxes plus SAM 2.1 tiny,
   both on CPU. A depth-recess check finds holes with no model at all. Flag both models as
   "small model on laptop".
4. Size comes from ray to wall-plane intersection, not raw depth. A Monte Carlo over mask
   boundary (±2 px), plane offset and pose gives the 90% interval. Multi-view spread is added.
5. Rules and scope come from BRE Digest 251 (crack widths), EPA (mould > 10 sq ft),
   damp-survey guidance (tide mark ≤ 1 m) and Xactimate line-item conventions (SF / LF / EA).

## Recommended pipeline for the 15-hour budget

| Stage | Primary (network) | Local fallback (no network) | Why |
|---|---|---|---|
| Find + classify | Gemini API, one call per keyframe. Prompt lists the 5 classes and asks for JSON `{label, box_2d, confidence, note}` | Florence-2-base `<OPEN_VOCABULARY_DETECTION>` per class phrase (CPU, ~0.23B params) | Gemini returns `box_2d` natively, normalised 0-1000, and can return masks too ([docs](https://ai.google.dev/gemini-api/docs/image-understanding)). It scored best on localisation in the building benchmark ([arXiv 2603.20148](https://arxiv.org/html/2603.20148v1)). Florence-2 is MIT and small ([model card](https://huggingface.co/microsoft/Florence-2-large)) |
| Verify (optional) | Claude on each crop: "is this a {class}? yes/no + why" | skip | Claude counted defects best in the benchmark (crack-count MAE 0.06) but localised worse than Gemini ([arXiv 2603.20148](https://arxiv.org/html/2603.20148v1)). Use it to cut false positives, not to place boxes |
| Mask | SAM 2.1 tiny with the box as prompt (CPU) | same | 111 MB, Apache-2.0 ([HF ONNX card](https://huggingface.co/vietanhdev/segment-anything-2.1-onnx-models)). Under the 500 MB bar, but still flag it |
| Hole (model-free) | depth recess vs wall plane (LiDAR tier only) | same | **(own)** A 6.4 cm hole at 1.5 m spans about 6 LiDAR pixels (256 px over ~60° FOV). Marginal, so use it as a confirm signal only |
| Project + size | ray / wall-plane intersection (section below) | same | Uses geometry we already trust |
| Merge views | cluster detections in wall (u, v) coords | same | **(own)** One damage seen in 5 frames must count once |
| Rules + scope | tables below, pure Python | same | Deterministic, explainable, no network |
| Benchmark only | SAM 3 text prompts on Kaggle T4 (fp16), cached JSON | n/a | 848M params, too big for the laptop ([Voxel51](https://voxel51.com/blog/how-to-use-segment-anything-model-sam3)). Good second opinion on the 26 photos |

Order of work **(own)**: (1) Gemini boxes on the 26 photos of the staged bedroom, hand-check;
(2) projection + interval, test against the hole (6.4 cm, centre 1.42 m up, 2.29 m from the
right wall; area π·3.2² ≈ 32 cm²); (3) rules + scope; (4) offline fallback last.
Disclose the hosted API in the report, as `requirements.md` says.

## 1. Approach comparison

| Approach | Size | Laptop (M4 CPU/MPS)? | Licence | Evidence on wall damage |
|---|---|---|---|---|
| Gemini (hosted) | n/a | API only | Google API terms | Building benchmark: classification recall 0.97; object detection P 0.36 / R 0.53 / F1 0.42 (best of all models) ([arXiv 2603.20148](https://arxiv.org/html/2603.20148v1)). Native boxes + masks ([docs](https://ai.google.dev/gemini-api/docs/image-understanding)) |
| Claude (hosted) | n/a | API only | Anthropic API terms | Same benchmark: spatial-reasoning F1 0.77, best counting (MAE 0.06 on cracks) ([arXiv 2603.20148](https://arxiv.org/html/2603.20148v1)). Authors: LMMs know "what", not precise "where" |
| GPT-4o / GPT-5.x (hosted) | n/a | API only | OpenAI API terms | GPT-5.1-chat classification F1 0.80; GPT-5.2-pro spatial F1 0.80; most models count with MAE ≈ 1 ([arXiv 2603.20148](https://arxiv.org/html/2603.20148v1)) |
| Grounding DINO-T | 172M params | CPU possible, slow | Apache-2.0 ([model page](https://telemetry.superlinked.com/models/idea-research-grounding-dino-tiny.md)) | 52.5 AP COCO zero-shot ([Forasoft](https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/open-vocabulary-detection-grounding-dino-florence-2-rtdetr-rfdetr)). No wall-damage benchmark; crack use is anecdotal ([Reddit](https://www.reddit.com/r/computervision/comments/17rlm2f/crack_detection_with_grounding_dino_and_segment/)) |
| Grounded SAM / SAM 2 | DINO + SAM | as above | Apache-2.0 | Same as DINO; SAM only refines the box |
| OWLv2 | base / large | CPU possible | Apache-2.0 ([model card](https://huggingface.co/google/owlv2-base-patch16-ensemble), [summary](https://www.aimodels.fyi/models/huggingFace/owlv2-base-patch16-ensemble-google)) | No wall-damage numbers found |
| Florence-2 | 0.23B / 0.77B | base: yes on CPU | MIT ([model card](https://huggingface.co/microsoft/Florence-2-large), [Reddit](https://www.reddit.com/r/LocalLLaMA/comments/1diz8en/microsoft_releases_florence2_vision_foundation/)) | 43.4 AP COCO zero-shot, below Grounding DINO 1.5 ([Grounded-SAM-2 #34](https://github.com/IDEA-Research/Grounded-SAM-2/issues/34)) |
| YOLO-World | small, real-time | yes | GPL-3.0, "supported for commercial usage" ([repo](https://github.com/ailab-cvc/yolo-world)) | No wall-damage numbers found |
| SAM 3 (text prompts) | 848M | no (Kaggle) | SAM License: commercial use with restrictions ([Voxel51](https://voxel51.com/blog/how-to-use-segment-anything-model-sam3), [repo](https://github.com/facebookresearch/sam3)) | Short noun phrases only, no complex queries ([Meta](https://ai.meta.com/blog/segment-anything-model-3/)). No wall-damage numbers |
| SAM 2.1 tiny (box prompt) | 111 MB | yes | Apache-2.0 ([HF](https://huggingface.co/vietanhdev/segment-anything-2.1-onnx-models)) | Mask refiner only; no text input |
| CLIP patch scoring (WinCLIP-style) | ~150M+ | yes | depends on CLIP weights | Zero-shot anomaly segmentation on industrial parts ([WinCLIP, arXiv 2303.14814](https://arxiv.org/abs/2303.14814)). Finds "something unusual", not which class |
| Trained YOLO crack/defect models | 3-70M | yes | Ultralytics models are AGPL **(check)** | Supervised YOLOv8n on 6 building-defect classes: mAP50 0.69, crack 0.69 ([MDPI Buildings 2025](https://www.mdpi.com/2075-5309/15/11/1865)). Outdoor/concrete data, domain gap to painted drywall |

Takeaways: open-vocabulary detectors are tuned for objects, and damage is "stuff" with a
vague edge **(own)**. The only head-to-head zero-shot numbers on building defects are for
hosted LMMs ([arXiv 2603.20148](https://arxiv.org/html/2603.20148v1)). That benchmark's
image-editing models reached mIoU 0.74 on defect masks, so zero-shot masks are viable.

## 2. Datasets and checkpoints

Licences were not shown on the scraped pages. Check each dataset's version page before use.

| Name | Images | Classes (vs our 5) | Checkpoint | Link |
|---|---|---|---|---|
| Wall damage detection | ~4.9k | crack, flaking paint, missing piece, water damage (4 of 5) | Roboflow 3.0 detector, hosted API | [Universe](https://universe.roboflow.com/wall-damage-detection/wall-damage-detection) |
| rentsafe-defects | 6.6k-8.1k | mold, hole in the wall, wall crack, floor/window damage (3 of 5) | Roboflow 3.0 instance seg, hosted API | [Universe](https://universe.roboflow.com/rentsafe-ihdlw/rentsafe-defects-hssck) |
| Building Defect Detection 7 | 9.6k | crack, leak, wall_mold, wall_stain, wall_deterioration (3-4 of 5) | yes, hosted | [Universe](https://universe.roboflow.com/hello-b0waw/building-defect-detection-7-ks0im) |
| Defect Images - Property | 376-902 | Mold, Wall Hole, Wall crack, Water Damage (4 of 5) | YOLOv11, hosted | [Universe](https://universe.roboflow.com/labelling-4pr77/defect-images-property) |
| elia | 3.6k | Mold-Mildew, Paint damage, Paint blisters, Stains on paint, cracks (4 of 5, mostly exterior) | Roboflow 3.0, hosted | [Universe](https://universe.roboflow.com/uoh-r6spu/elia) |
| Damp / peeling searches | many small | damp, peeling | varies | [damp](https://universe.roboflow.com/search?q=class%3Adamp+wall), [peeling](https://universe.roboflow.com/search?q=class%3Apeeling) |
| OpenSistemas YOLOv8-crack-seg | n/a | crack only | weights on HF (n to x) | [HF](https://huggingface.co/OpenSistemas/YOLOv8-crack-seg) |

Use **(own)**: no dataset matches all five classes on interior drywall. Combining "Wall
damage detection" and "rentsafe-defects" covers all five. A light fine-tune on Kaggle is a
stretch goal, not the plan. Calling the Roboflow hosted models needs a network and an API
key, so they are no better offline than Gemini. Their best use is a few labelled images to
sanity-check our zero-shot prompts.

## 3. From a 2D mask to a size on the wall

Published practice fuses image masks with LiDAR geometry. A SAM-refined crack mask fused with
visual-inertial LiDAR reached < 0.1 mm mean absolute width error on concrete
([arXiv 2501.09203](https://arxiv.org/pdf/2501.09203)). Consumer mobile LiDAR gave ±0.5 mm
with reference targets but > 1.5 mm without them
([Erciyes](https://avesis.erciyes.edu.tr/publication/details/f02a9c53-16cf-4f97-8c6c-fcaa8f8e6632/oai)).
Smartphone LiDAR vs TLS crack accuracy is also studied
([UiTM record](https://update.library.uitm.edu.my/Record/WOS:001308267400022)).
Our steps below are **(own)**, built on those ideas and our existing frames.

1. **Pick the surface.** For each mask, sample depth (LiDAR) or predicted points (Pi3X)
   inside it. Assign the wall / floor / ceiling whose plane is within ~5 cm of the median
   point and whose extent contains it.
2. **Project the outline, not the depth.** Cast a ray from the camera centre through each
   boundary pixel (intrinsics K, camera-to-world pose). Intersect it with that surface's
   plane `n·X = d`. A plane is less noisy than per-pixel depth.
3. **Go to wall coordinates.** u = distance along the wall from its start, v = height above
   the floor. Floor / ceiling use plan (x, y).
4. **Measure.** Area = shoelace formula on the (u, v) polygon. Extent = width × height of its
   box. Cracks: skeletonise the mask; length = skeleton length in metres. Width only as a band
   (pixel footprint ≈ distance / focal; about 1 mm at 1.5 m on 1920 px RGB, so "< 1 mm" is
   not resolvable but "> 5 mm" is).
5. **Merge views.** Cluster detections of the same class on the same surface by centre
   distance in (u, v). Point estimate = median over views.
6. **90% interval by Monte Carlo** (e.g. 500 draws per detection):
   - mask boundary: erode / dilate by 0-2 px (main term for small items like the hole);
   - plane offset: our wall-plane interval from `lidar.py`;
   - pose: small rotation / translation noise (LiDAR) or the scale-bias interval from
     `intervals.py` (video / photo tiers);
   - take the 5th / 95th percentile. Widen it to cover the spread across views (bootstrap
     over views when ≥ 3).
7. **Validate on the staged hole.** Truth: 32 cm², centre (2.29 m from right wall, 1.42 m
   up). Report whether the interval contains it.

## 4. Concealed-damage rule table

| Id | Trigger (our detections + geometry) | Flag text | Source |
|---|---|---|---|
| R1 | water_stain on a ceiling | Possible roof or plumbing leak above. Moisture-meter check advised; cannot tell past from active leak | [InterNACHI forum](https://forum.nachi.org/t/moisture-intrusion-question/255944), [InterNACHI forum](https://forum.nachi.org/t/ceiling-stains/43576) |
| R2 | water_stain or peeling on a wall, bottom edge ≤ 0.1 m and top ≤ 1.2 m above the floor | Possible rising damp (tide mark from skirting level) | [Permagard](https://www.permagard.co.uk/advice/how-to-treat-rising-damp), [Timber and Damp](https://timberanddamp.co.uk/how-to-spot-rising-damp/), [Wise](https://www.wisepropertycare.com/damp-proofing/rising-damp/) |
| R3 | mould on any surface | Hidden moisture source likely (leak or condensation); fix the source before cleaning | [EPA](https://www.epa.gov/mold/mold-cleanup-your-home), [RestoreAdvisor](https://www.restoreadvisor.com/mold-remediation/when-is-mold-remediation-required) |
| R4 | mould total area > 0.93 m² (10 sq ft), interval upper bound used | Professional remediation scale; growth may continue inside the wall cavity | [EPA](https://www.epa.gov/mold/mold-cleanup-your-home), [Env. Education](https://environmentaleducation.com/level-2-mold-remediation-safety-steps-rules/) |
| R5 | peeling paint (blistering / flaking) | Possible moisture behind the finish | [Luxcando](https://luxcando.com/common-symptoms/peeling-paint/), [InterNACHI forum](https://forum.nachi.org/t/moisture-intrusion-question/255944) |
| R6 | crack starting at a door / window corner, angle 30-60° | Possible differential settlement; monitor for change | [InterNACHI forum](https://forum.nachi.org/t/diagonal-cracks-above-interior-doors/209652), [RMSS](https://rmssco.com/diagonal-drywall-cracks-above-door-frames-fix-cause-guide/) |
| R7 | crack width band > 5 mm (BRE category ≥ 3) | Structural movement possible; refer to a structural engineer | [BRE](https://www.bre.co.uk/page.jsp?id=3356&/1000), [BRE 251 guide](https://propertysurvey.pro/info/tools/crack-damage-categoriser) |
| R8 | crack width band ≤ 5 mm (BRE 0-2) | Usually aesthetic; redecorate and monitor (a "no concern" flag, still logged) | [BRE](https://www.bre.co.uk/page.jsp?id=3356&/1000) |
| R9 | water_stain and mould on the same surface within 0.5 m | Ongoing moisture likely (not a one-off event) | **(own)**, from R1 + R3 |
| R10 | crack or hole within ~0.3 m of a switch / socket / wiring run | Possible damage to concealed wiring; electrician check | **(own)**; no source found. The staged room has cracks around wiring |

Note: the InterNACHI SOP does not require inspectors to inspect paint or finishes
([SOP](https://www.nachi.org/sop.htm)). Our rules go beyond a standard home inspection, so
the report should call them "flags", not findings.

## 5. Repair scope line items (no pricing)

Xactimate groups items by trade prefix (DRY/DRW drywall, PNT painting, WTR water, HMR
hazardous material) and uses SF, LF and EA units
([CapOut](https://capout.ai/resources/blog/xactimate-line-item-cheat-sheet),
[Wave](https://buildwithwave.com/blog/mold-remediation-xactimate-line-items)).
We output metric units (m², m, each) with intervals, and keep the code as a reference.

| Damage | Item | Ref code | Quantity basis | Unit | Source |
|---|---|---|---|---|---|
| crack | Tape, fill and finish crack | DRY LF-style | crack length | m | [Docsity code list](https://www.docsity.com/en/docs/codes-for-xactimate-or-complete-questions-and-answers-or-2024-study-set/12123631/) |
| crack, hole, stain, peeling | Seal and paint wall (2 coats) | PNT S/P | wall face area **(own: whole face, to match colour)** | m² | [Docsity](https://www.docsity.com/en/docs/codes-for-xactimate-or-complete-questions-and-answers-or-2024-study-set/12123631/) |
| hole (≤ ~0.37 m², i.e. 4 sq ft) | Drywall patch | DRY PATCH | count | each | [Docsity](https://www.docsity.com/en/docs/codes-for-xactimate-or-complete-questions-and-answers-or-2024-study-set/12123631/) |
| hole (larger) | Remove and replace drywall | R&R drywall | damaged area + margin | m² | [CapOut](https://capout.ai/resources/blog/xactimate-line-item-cheat-sheet) |
| water_stain | Seal with stain blocker | PNTSP | stain area | m² | [Facebook adjuster group](https://www.facebook.com/groups/386231336177135/posts/1240017857465141/) |
| water_stain (ceiling) | Drywall ceiling R&R if wet | DRYCL | stain area | m² | [Facebook adjuster group](https://www.facebook.com/groups/386231336177135/posts/1240017857465141/) |
| mould | Apply antimicrobial agent | WTRGRM | mould area | m² | [Reets](https://reetsdryingacademy.com/blog/xactimate-line-items-for-water-mitigation/) |
| mould (R4 fired) | Containment + HEPA clean + clearance test | WTR / HMR items | mould area / count | m² / each | [Wave](https://buildwithwave.com/blog/mold-remediation-xactimate-line-items), [KnowHow](https://tryknowhow.com/template/understand-best-estimating-practices-for-mold-in-xactimate) |
| mould on drywall | Remove and replace drywall | WTRDRYW / R&R drywall | mould area + margin | m² | [Reets](https://reetsdryingacademy.com/blog/xactimate-line-items-for-water-mitigation/) |
| peeling paint | Scrape, prep, seal and paint | PNT S/P (+ prep) | peeling area; paint whole face | m² | [Docsity](https://www.docsity.com/en/docs/codes-for-xactimate-or-complete-questions-and-answers-or-2024-study-set/12123631/) |

Scope rows carry the quantity interval from section 3. Each row names its surface id and the
detection ids it came from **(own)**.

## 6. Risks

1. **False positives** from shadows, outlets, picture hooks and wood grain. Zero-shot LMMs
   over-report: precision 0.36 on detection ([arXiv 2603.20148](https://arxiv.org/html/2603.20148v1)).
   Mitigate with the Claude verify step and a multi-view vote **(own)**.
2. **Loose boxes.** LMM boxes are imprecise ([arXiv 2603.20148](https://arxiv.org/html/2603.20148v1)),
   so SAM refinement is needed before measuring area.
3. **Hairline cracks are thinner than a pixel** at room distance (step 4 above). Report
   length, and width only as a BRE band.
4. **Class confusion.** Water stain vs mould vs dirt is hard even for people. A moisture meter
   is the usual tie-breaker ([InterNACHI forum](https://forum.nachi.org/t/need-for-moisture-meter/199644)).
5. **No network at the walk-in.** The fallback is weaker and the hosted model's results cannot
   be cached ahead for a new room. Rehearse the offline path once.
6. **Laptop memory.** Florence-2-base + SAM 2.1 tiny is under ~1 GB, but it is still a model
   on the laptop. Get the user's OK, or ship the depth-recess hole check and VLM-only path.
7. **Licences.** SAM 3 has a custom licence; YOLO-World is GPL-3.0; Ultralytics weights are
   likely AGPL; Roboflow dataset licences are unverified (section 2).
8. **Rules are heuristics.** R9 and R10 have no external source; label them as ours.
9. **Video / photo tiers** carry a scale bias, so damage areas there inherit wider intervals.
10. **Data privacy.** Sending a friend's home photos to a hosted API needs the user's OK,
    same as the Kaggle rule in `CLAUDE.md`.
