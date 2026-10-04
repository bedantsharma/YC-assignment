# Next session

State and findings: [HANDOVER.md](HANDOVER.md). Each step ends with a commit and the
ROADMAP status updated. **No model runs on the laptop: Kaggle only** (CLAUDE.md).

The graded fix is done ([docs/fix_declaration.md](docs/fix_declaration.md), tags
`fixloop-before` / `fixloop-after`): LiDAR vs ground truth 29 → 5 cm median, head-to-head
with Polycam beat or tie on 6 of 8 (75%). Do not change wall geometry again without
rerunning `uv run scripts/lidar_summary.py` and `uv run scripts/gt_table.py` and recording
the change.

## 1. Kaggle rerun of the plans that have no replay cache

`gt_table.py` marks them "pre-fix geometry (no cache)": the `c_home_01` LiDAR recording's
video (90 frames) and the photo-tier runs on video stills. Also the real photo folders, once
the user has sorted them.

1. Re-upload `src/floorplan` to the Kaggle dataset `floorplan-video-c2` (its copy is from
   before the fix), plus the photo folders (private dataset, user's OK first).
2. In `kaggle/video_runs` (or a new `kaggle/photo_runs`): run with
   `FLOORPLAN_RECON_CACHE` set, so the laptop can replay; dry-run the setup locally first
   (CLAUDE.md checklist).
3. Replay locally, rerun `uv run scripts/gt_table.py`; add rows for the real photos.
4. Check the video scale bias on the held-out rooms (`uv run scripts/video_scale.py
   outputs/bakeoff/c_damage_0*__*.npz outputs/video_eval/*.npz`): one bias leaves ±10%
   per room (drawing room ≈ +10%); report it, widen `RESIDUAL_REL` if the held-out rooms
   say so.

## 2. Then, in order

1. **Openings** (doors, windows): GT has the bedroom door 3.4 ft and window 7 ft, living
   room openings; `lintel_mask` in `plan2d.py` finds door heads. SpatialLM (seed-voted) is
   a candidate for windows.
2. **Phase 5 damage**: the bedroom hole (2.5 in, centre 4.66 ft up, 7.5 ft from the right
   wall) is the test case.
3. **Interval calibration** (fix map 03, gate G10): area intervals hold the truth in 3 of
   6 rooms; walls now carry the smear's spread as sigma. Calibrate per tier against C's
   ground truth and the repeat scans.
4. Phase 7: benchmark report (`scripts/benchmark.py`: all gates, repeatability table),
   technical report, compliance, fresh-clone test.

## Waiting on

- User: sorted photo folders (one folder per room).
- Friend (one message, see HANDOVER): original-quality videos/photos via Drive/iCloud,
  Polycam app version + any export; optionally a 1-2 min eye-level house video.
- Architect: blind laser measurements for B → `data/gt/arkitscenes_421337.yaml` (would
  verify fix 09's growth of B's room by 1.2-2.2 m²).

## Open, lower priority

- Dining & living room short side −23 cm: its west wall was never scanned (fix map 01c).
  **Accepted as a capture limit (user, Oct 4): no rescan; do not tune for it**, state it in
  the report.
- Whole-house Camera-app video fails: windows fold rooms onto each other
  (`docs/home_c_new_captures.md`). Try shorter windows, skip ceiling frames, or a new clip.
- Drift correction that does no harm (brief G5).
- B's three scans differ by up to 0.9 m in extent (fix map 02b); fix 09 widened it.
