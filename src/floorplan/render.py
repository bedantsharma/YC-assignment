"""Draw a Result as a dimensioned floor plan (PNG). Uses only the Result, so every tier
renders the same way."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from floorplan.output import Measurement, Result  # noqa: E402


def render_plan(result: Result, path: Path | str) -> Path:
    path = Path(path)
    fig, ax = plt.subplots(figsize=(11, 11))
    colors = plt.cm.tab10.colors
    for k, room in enumerate(result.rooms):
        poly = np.array(room.polygon + room.polygon[:1])
        ax.fill(poly[:, 0], poly[:, 1], color=colors[k % 10], alpha=0.15)
        for wall in room.walls:
            (x0, y0), (x1, y1) = wall.start, wall.end
            style = "-" if wall.observed else ":"
            ax.plot([x0, x1], [y0, y1], style, color=colors[k % 10], lw=2.5)
            if wall.length.value >= 0.3:
                vertical = abs(x1 - x0) < abs(y1 - y0)
                ax.text(
                    (x0 + x1) / 2,
                    (y0 + y1) / 2,
                    _fmt(wall.length) + ("" if wall.observed else " ?"),
                    fontsize=7,
                    ha="center",
                    va="center",
                    rotation=90 if vertical else 0,
                    bbox={"fc": "white", "ec": "none", "alpha": 0.8, "pad": 0.5},
                )
        cx, cy = np.array(room.polygon).mean(axis=0)
        ceiling = _fmt(room.ceiling_height) if room.ceiling_height else "not captured"
        label = f"{room.label}\n{_fmt(room.floor_area, 'm²', 1)}\nceiling {ceiling}"
        ax.text(cx, cy, label, ha="center", va="center", fontsize=9, weight="bold")

    title = f"{result.capture.id} [{result.capture.tier}]"
    if result.footprint_area:
        title += f": {len(result.rooms)} rooms, footprint {_fmt(result.footprint_area, 'm²', 1)}"
    ax.set_title(f"{title}\nvalues with 90% intervals; dotted walls were not observed")
    ax.set_aspect("equal")
    ax.grid(alpha=0.25)
    ax.set_xlabel("m")
    ax.set_ylabel("m")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return path


def _fmt(m: Measurement, unit: str = "m", digits: int = 2) -> str:
    half = (m.hi - m.lo) / 2
    return f"{m.value:.{digits}f} ± {half:.{max(digits, 2)}f} {unit}"
