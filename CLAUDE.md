# floorplan

Phone captures of a home → dimensioned floor plan (walls, wall lengths, floor area, ceiling
height) with a confidence interval on every measurement. Built for the Cozmo AI "Applied AI"
take-home (brief: `Applied AI.pdf`, gitignored). Current scope: the LiDAR tier only.

## Commands

- `uv sync`: install dependencies (Python 3.12, managed by uv; never use pip directly)
- `uv add <pkg>` / `uv add --dev <pkg>`: add dependencies
- `uv run ruff check --fix . && uv run ruff format .`: run before every commit
- `uv run scripts/fuse_topdown.py`: fuse all captures, write `outputs/topdown_overview.png`

## Layout

- `src/floorplan/`: the pipeline package
- `scripts/`: exploration and one-off analysis scripts
- `data/raw/<capture-id>/`: Stray Scanner captures (gitignored, ~0.1–0.5 GB each)
- `outputs/`: generated plots and results (gitignored)

## Data conventions (verified against the captures)

- `depth/*.png` is 16-bit depth in **millimetres** at 256x192; `confidence/*.png` is 0/1/2.
  Use only confidence 2 for geometry.
- `odometry.csv` holds camera-to-world poses; quaternion order is `qx, qy, qz, qw`
  (matches `scipy.spatial.transform.Rotation.from_quat`).
- Back-project depth with the **OpenCV camera convention** (x right, y down, z forward) and
  apply the pose directly. The ARKit convention (x, -y, -z) produces a smeared cloud.
- World `y` is vertical (up). Floor sits around y ≈ -1.4 to -1.5 m in each capture.
- Scale `camera_matrix.csv` intrinsics from 1920x1440 down to the 256x192 depth resolution.
- The three captures walk the **same multi-room apartment**. `c7d28f72c6` is the most
  complete and the only one with the ceiling visible (~3.07 m, tentative).
- There is no tape or laser ground truth, so state accuracy claims as "consistent with
  LiDAR", not "correct".

## Working rules

- Commit small and often with descriptive messages: commit history is graded, and a repo
  that appears in one or two commits scores zero on process.
- Every reported number must be regenerable by a single command from `data/raw/`.
- Prefer numpy/scipy; justify any heavy dependency (e.g. open3d) before adding it.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **YC-assignment** (34 symbols, 33 relationships, 0 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/YC-assignment/context` | Codebase overview, check index freshness |
| `gitnexus://repo/YC-assignment/clusters` | All functional areas |
| `gitnexus://repo/YC-assignment/processes` | All execution flows |
| `gitnexus://repo/YC-assignment/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->