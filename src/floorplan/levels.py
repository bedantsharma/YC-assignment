"""Floor and ceiling heights from the vertical distribution of points (z up)."""

from dataclasses import dataclass

import numpy as np

BIN_M = 0.01
REFINE_M = 0.025  # points within this of the peak bin define the plane
FLOOR_MIN_FRACTION = 0.25  # floor bin needs this share of the densest bin's count
CEILING_MIN_FRACTION = 0.05  # ceilings are scanned far less than floors
CEILING_MIN_ABOVE_FLOOR_M = 2.0
MIN_PLANE_POINTS = 50
SEPARATION_DIP = 0.5  # a ceiling peak must dip below this share of its count before a bigger one


@dataclass
class Level:
    z: float  # median height of the plane's points
    spread: float  # robust std of those points (plane thickness, sensor noise)
    n: int


def floor_level(z: np.ndarray) -> Level:
    """Lowest height that is nearly as dense as the densest one."""
    counts, edges = _histogram(z)
    dense = np.flatnonzero(counts >= FLOOR_MIN_FRACTION * counts.max())
    return _refine(z, edges[dense[0]] + BIN_M / 2)


def ceiling_level(z: np.ndarray, floor_z: float) -> Level | None:
    """Highest dense, separate peak at least 2 m above the floor, or None if never scanned.

    Separate: the histogram dips below half the peak's count between it and every bigger
    peak below it, so ripples on the upper tail of a broad ceiling peak don't count.
    """
    counts, edges = _histogram(z)
    centres = edges[:-1] + BIN_M / 2
    threshold = max(CEILING_MIN_FRACTION * counts.max(), MIN_PLANE_POINTS)
    padded = np.pad(counts, 1)
    peaks = (counts >= padded[:-2]) & (counts >= padded[2:]) & (counts >= threshold)
    candidates = np.flatnonzero(peaks & (centres >= floor_z + CEILING_MIN_ABOVE_FLOOR_M))
    for i in candidates[::-1]:
        if _separated(counts, i):
            return _refine(z, centres[i])
    return None


def _separated(counts: np.ndarray, i: int) -> bool:
    """No bigger bin below i without a dip under SEPARATION_DIP * counts[i] in between."""
    bigger = np.flatnonzero(counts[:i] > counts[i])
    if not len(bigger):
        return True
    return counts[bigger[-1] : i + 1].min() < SEPARATION_DIP * counts[i]


def _histogram(z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    edges = np.arange(z.min(), z.max() + 2 * BIN_M, BIN_M)
    counts, edges = np.histogram(z, bins=edges)
    return np.convolve(counts, np.ones(3) / 3, mode="same"), edges


def _refine(z: np.ndarray, centre: float) -> Level:
    near = z[np.abs(z - centre) < REFINE_M]
    med = float(np.median(near))
    spread = float(1.4826 * np.median(np.abs(near - med)))
    return Level(med, spread, len(near))
