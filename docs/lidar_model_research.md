# Pretrained models for the LiDAR tier (Oct 4)

Our LiDAR backend is hand-built geometry (`plan2d.py`, `rooms.py`): wall evidence from
vertical extent, Manhattan orientation, enclosure test, watershed rooms. The user asked
whether pretrained models do this better. This note surveys them (Firecrawl, Oct 4) and
picks what to test. All model runs happen on Kaggle (T4), never on the laptop.

## What we would want a model to fix

Measured against Polycam (Apple RoomPlan) on home C (`data/gt/home_c_polycam.json`), our
LiDAR rooms are 6 to 57 cm smaller on every dimension. Two causes are visible in the cloud:

1. **Doubled walls** (pose drift): each wall appears 2-3 times, 15-50 cm apart, and we snap
   to the innermost copy. A model given the same cloud sees the same copies.
2. **Furniture as wall** (fix map 04): wardrobes and kitchen cabinets fill the wall band,
   so the room stops at their front faces.

A model can help with 2 (it knows what a wardrobe is) and with openings (Phase 5, not
built). It cannot undo 1; at best it picks a better copy.

## Candidates

| Model | Input → output | Trained on | Weights / license | Runs on Kaggle T4? | Verdict |
|---|---|---|---|---|---|
| **SpatialLM 1.1** (NeurIPS 2025; Qwen-0.5B, Llama-1B) | coloured point cloud (z up) → walls (segment, height, thickness), doors, windows, object boxes | 12k synthetic scenes, fine-tuned on Structured3D; ARKitScenes fine-tune recipe given | HF, open download; **CC BY-NC** (Sonata encoder) | yes, with flash attention off (T4 is pre-Ampere); own Python 3.11 venv | **Test (round 3)**: the only open model that outputs walls *and* openings from any point cloud |
| SpatialLM 1.0 | same; SceneScript encoder | same | CC BY-NC | needs torchsparse built from source | skip: 1.1 supersedes it |
| SceneScript (Meta, 2024) | Aria semi-dense points → walls, doors, windows | Aria Synthetic Environments | **gated, academic only**, CC BY-NC | no access | skip: no weights without approval, different sensor |
| RoomFormer (CVPR 2023) / PolyRoom (ECCV 2024) / FRI-Net | top-down density image → room polygons | Structured3D (synthetic), SceneCAD (ScanNet) | MIT code, checkpoints on polybox | torch 1.9 era; custom CUDA ops to compile | second choice: room polygons only, no metric heights, no openings; SpatialLM beats RoomFormer on Structured3D (F1 94.3 vs 83.4) |
| Sonata / PTv3 (Pointcept, CVPR 2025) | point cloud → per-point labels (ScanNet 20 classes: wall, floor, cabinet, bed, ...) | 140k scenes incl. ARKitScenes, ScanNet | HF `facebook/sonata`, **CC BY-NC** | yes (same stack as SpatialLM) | candidate for fix map 04: drop furniture points before our wall test |
| Apple RoomPlan | iPhone LiDAR session → parametric rooms | Apple | iOS API only | no | it *is* the competitor (Polycam uses it) |
| FloorSAM (2025) | density map + SAM → room masks | zero-shot | SAM Apache | yes | skip: segmentation only, our rooms are already found 4/4 |

Published accuracy is topological (wall F1 at IoU 0.25/0.5), never centimetres. On noisy
point clouds reconstructed from video, SpatialLM's zero-shot wall F1@0.25 is 68-69, doors
47-49, windows 47-51. Nobody reports dimension error, so the bake-off has to measure it.

## Bake-off round 3 (Kaggle, `kaggle/lidar_bakeoff/`)

- Input: home C's three LiDAR recordings fused exactly as the LiDAR tier does, plus the
  colour of each depth pixel (`scripts/export_clouds.py`), as private dataset
  `bedantsharma/floorplan-lidar-c`.
- Models: SpatialLM 1.1 Qwen-0.5B and Llama-1B, "arch" mode (walls, doors, windows), 3
  seeds each (generation samples, so the spread is part of the result).
- Scored locally against our LiDAR plan and Polycam, per room: wall-to-wall width and
  depth, and whether doors and windows are found. Tape measurements replace both
  references when they arrive.

Results: pending.
