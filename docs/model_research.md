# Model research: which model turns a phone video into metric 3D?

Sat Oct 3, ~00:15 IST (Sun). Done with Firecrawl after the spike, because the spike tested
only one model and its choice of candidates came from the roadmap, not from a survey.

## What the video tier needs

1. Many RGB frames in, one consistent 3D cloud out (multi-view, no poses given).
2. **Metric scale** (metres), since the plan reports wall lengths.
3. Runs on a 16 GB M4 Mac (MPS) within minutes.
4. Indoor rooms with large blank walls.
5. A license we can disclose for a take-home demo (commercial use is a plus).

## Candidates (as of Oct 2026)

| Model | Venue | Metric scale | Weights license | Size | Notes |
|---|---|---|---|---|---|
| **MapAnything** ([paper](https://arxiv.org/abs/2509.13414), [code](https://github.com/facebookresearch/map-anything)) | 3DV 2026, Meta + CMU | **Yes**, predicts one metric scale factor per scene | **Apache 2.0** (`map-anything-apache`); CC BY-NC for the stronger full model | ~1B | Beats VGGT on its own dense N-view benchmark (ETH3D, ScanNet++ v2, TartanAir); has MPS support; wraps the other models below behind one interface |
| **Depth Anything 3** ([paper](https://openreview.net/forum?id=yirunib8l8), [code](https://github.com/ByteDance-Seed/depth-anything-3)) | ICLR 2026 oral, ByteDance | **Yes** via `DA3NESTED-GIANT-LARGE-1.1` (multi-view + metric model, output in metres) | Nested/Giant/Large: **CC BY-NC 4.0**; Base/Small/Metric-Large: Apache 2.0 | 1.4B (nested) | Claims +35.7% pose and +23.6% geometry accuracy over VGGT on its own benchmark; MPS fix merged Nov 2025 |
| **Pi3X** ([code](https://github.com/yyfz/Pi3), [weights](https://huggingface.co/yyfz233/Pi3X)) | Dec 2025 update of π³ | **Approximate** metric scale | **CC BY-NC 4.0** | 1B | Can take intrinsics as input; authors "expect" it to beat MapAnything but have no published evaluation of it ([issue 113](https://github.com/yyfz/Pi3/issues/113)) |
| **VGGT-Ω** ([code](https://github.com/facebookresearch/vggt-omega)) | CVPR 2026 oral / best-paper finalist | Not stated | Gated on Hugging Face; license not stated on the page | 1B | Peak memory 6 GB (1 frame) to 43 GB (500 frames) on an A100: too big for many frames here |
| VGGT | CVPR 2025 best paper | No (up to scale) | | 1B | Superseded by the above |
| CUT3R / StreamVGGT / VGGT-Long / LongStream | 2025–26 | Mixed | | | Streaming / long video; one 2026 benchmark shows CUT3R and StreamVGGT drift badly on long sequences, VGGT-Long and LongStream much better. Relevant only if whole-home walks exceed what one pass can hold |

Not candidates for this tier, but noted: MoGe-2 (Pi3 authors recommend it over multi-view
models for single images), Apple RoomPlan (needs LiDAR).

## What the published numbers do and don't tell us

- Each paper wins on its own benchmark. None of them reports **room dimensions from a
  handheld phone video**, which is our task; ScanNet++ is the closest indoor set.
- No independent comparison of MapAnything vs DA3-nested vs Pi3X on metric indoor
  reconstruction was found.
- So the choice has to be made **on our data**: the same 30 frames of `c_damage_01`
  through each model and the same backend, scored against the LiDAR of the same
  recording (as in [model_spike.md](model_spike.md)).

## Practical point

MapAnything's `model_factory` already wraps `da3_nested`, `pi3x` and `vggt_omega`, so all
candidates can run through one script with the same frames and evaluation. DA3-nested and
Pi3X are each another ~4–6 GB download (26 GB disk free).

## License consequence

Only MapAnything ships a metric multi-view model under Apache 2.0. If DA3 or Pi3X wins, the
submission must disclose that its weights are non-commercial (fine for a take-home demo,
not for Cozmo's product without a license).
