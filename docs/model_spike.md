# Model spike: multi-view reconstruction for the video and photo tiers

Sat Oct 3, 20:40–21:45 IST. Question: does a pretrained multi-view model run on this Mac
(M4, 16 GB) and give geometry good enough to feed the LiDAR tier's backend?

## Setup

- Model: **MapAnything** (`facebook/map-anything-apache`, Apache 2.0, 4.9 GB), on MPS.
  Installed in a separate venv (torch 2.14), not a project dependency yet.
- Input: 30 evenly spaced frames of `c_damage_01/rgb.mp4` (one room, 62 s, 15.5 m camera
  path). Only RGB goes in.
- Reference, for evaluation only: the same recording's ARKit poses and LiDAR cloud.
  - scale: similarity fit of predicted camera centres to ARKit's (1.0 = metric scale right)
  - ATE: camera-centre error after that fit
  - cloud: model points to LiDAR points, after the fit
  - plan: the model cloud, rotated to z up with the fit's rotation but **not its scale**,
    through the LiDAR tier's `build_plan`. So the room numbers carry the model's own scale

```bash
<venv>/bin/python scripts/spike_video_model.py data/home_c/lidar/c_damage_01 [--rotate] [--focal35 24]
```

Outputs: `outputs/spike/c_damage_01_mapanything_30*/` (`summary.json`, `plan.png`,
`predictions.npz`).

## Results

| Run | Scale | ATE median / max | Cloud to LiDAR median / p90 | Room | Ceiling |
|---|---|---|---|---|---|
| frames as stored (sideways) | 0.55 | 1.00 / 2.13 m | 0.72 / 1.06 m | none found | – |
| **upright** (`--rotate`) | **1.03** | 0.29 / 1.71 m | **0.058 / 0.165 m** | 11.07 m² | 3.43 m |
| upright + 24 mm focal given | 1.02 | 0.26 / 1.77 m | 0.053 / 0.156 m | 11.10 m² | 3.42 m |
| LiDAR tier, same recording | – | – | – | 13.13 m² | 3.36 m |

Walls (upright): 3.89 / 2.91 / 2.54 / 0.19 / 1.36 / 2.72 m vs LiDAR 4.24 / 3.30 / 2.64 /
0.66 / 1.30 / 2.94 m: same L shape, walls 5–47 cm off, area 16% low.

Run time: 52 s for 30 frames (model load excluded); peak memory 12.8 GB.

## Findings

1. **Runs on this Mac**, at a usable speed. Memory is the limit: 30 frames peak at
   12.8 GB of 16 GB, so many more frames per call will not fit.
2. **Frames must be upright.** Stray stores portrait captures sideways (world up = image
   −x on all three C captures). Sideways, the model's focal estimate is 0.6× the true one
   and the reconstruction collapses. The video tier must rotate frames: from the video's
   rotation metadata (Camera-app video has it); for Stray recordings, which have none, the
   spike used ARKit gravity, which the video tier may not read (see `docs/data_plan.md`).
   An RGB-only way to pick the rotation is still needed.
3. **Metric scale is good** (2–3% vs ARKit). Geometry is good near the surfaces (5–6 cm
   median) but the room outline is not yet: 16% area error, one wall at 0.19 vs 0.66 m.
4. Giving the lens focal (Apple's 24 mm-equivalent spec, within 1% of this recording's
   calibration) **barely changed anything**; the model's output focal stays at ≈ 291 vs
   ≈ 362 px true at its input size. Not explained yet.

## Decision

Use **MapAnything** for the video and photo tiers. It is the only candidate measured: VGGT
(no metric scale on its own) and MASt3R were **not tried** (another ~5 GB download each).
Next steps for the tier, in order: frames upright, more coverage per call within memory
(keyframes chosen by view change, not evenly in time), then the interval widening for this
tier calibrated against the LiDAR result of the same recording.
