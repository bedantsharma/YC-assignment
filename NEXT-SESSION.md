# Next session

State and findings: [HANDOVER.md](HANDOVER.md). Each step ends with a commit and the
ROADMAP status updated. **No model runs on the laptop: Kaggle only** (CLAUDE.md).

The graded fix is done ([docs/fix_declaration.md](docs/fix_declaration.md), tags
`fixloop-before` / `fixloop-after`): LiDAR vs ground truth 29 → 5 cm median, head-to-head
with Polycam beat or tie on 6 of 8 (75%). Do not change wall geometry again without
rerunning `uv run scripts/lidar_summary.py` and `uv run scripts/gt_table.py` and recording
the change.

## 1. Done after the fix (this session)

Kaggle refilled every replay cache (`kaggle/cache_runs`, dataset `floorplan-video-c2` now
holds the fixed code); calibration (`scripts/calibration.py`), openings (`openings.py`),
benchmark report (`scripts/benchmark.py`), technical report, `scripts/reproduce.sh`.

Next: the friend's real photo folders (once sorted) through `kaggle/cache_runs` (add the
folders to the dataset, user's OK first), replay, add rows to `gt_table.py`; check the photo
residual (fitted on C's stills) against them.

## 2. Then, in order

1. **Windows and door widths** (`docs/openings.md`): the door is found 34 cm narrow,
   windows not at all; SpatialLM (seed-voted) is a candidate for windows.
2. **Phase 5 damage**: the bedroom hole (2.5 in, centre 4.66 ft up, 7.5 ft from the right
   wall) is the test case.
3. **Walk-in**: the brief runs the pipeline on our laptop; image tiers need the model
   (Kaggle with internet, or a one-off local run): decide with the user.
4. Fresh-clone test (README, < 15 min).

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
