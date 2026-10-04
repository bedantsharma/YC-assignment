from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from floorplan import mvs


def _fake(calls):
    def infer(frames, model):
        calls.append(len(frames))
        pts = np.random.default_rng(0).random((len(frames), 4, 5, 3), dtype=np.float32)
        keep = np.ones(pts.shape[:3], bool)
        return mvs.Reconstruction(pts, keep, np.tile(np.eye(4), (len(frames), 1, 1)), 1.5, model)

    return infer


def test_cache_replays_without_the_model(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(mvs, "_infer", _fake(calls))
    monkeypatch.setenv(mvs.CACHE_ENV, str(tmp_path))
    monkeypatch.setenv(mvs.BACKEND_ENV, "here")
    frames = [Image.new("RGB", (8, 6), (i, 0, 0)) for i in range(3)]
    first = mvs.reconstruct(frames, "pi3x")
    second = mvs.reconstruct(frames, "pi3x")
    assert calls == [3]
    np.testing.assert_array_equal(first.view_points, second.view_points)
    assert second.seconds == 1.5 and second.model == "pi3x"

    monkeypatch.setenv(mvs.CACHE_ONLY_ENV, "1")
    other = [Image.new("RGB", (8, 6), (9, 9, 9))]
    with pytest.raises(RuntimeError, match="no cached reconstruction"):
        mvs.reconstruct(other, "pi3x")


def test_failed_cache_write_leaves_nothing_behind(tmp_path, monkeypatch):
    """A write that fails part-way leaves neither the entry nor a temp file."""
    pts = np.zeros((1, 2, 2, 3), np.float32)
    rec = mvs.Reconstruction(pts, np.ones((1, 2, 2), bool), np.eye(4)[None], 1.0, "pi3x")

    def broken(path, **arrays):
        Path(path).write_bytes(b"half")
        raise OSError("disk full")

    monkeypatch.setattr(mvs.np, "savez_compressed", broken)
    with pytest.raises(OSError, match="disk full"):
        mvs.save(tmp_path / "entry.npz", rec)
    assert list(tmp_path.iterdir()) == []
