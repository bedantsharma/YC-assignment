"""Where the model runs: Kaggle first, this machine as the fallback, low-memory windows."""

import numpy as np
import pytest
from PIL import Image

from floorplan import mvs, mvs_local, remote

REAL_SAFE = mvs_local.reconstruct_safe  # before the autouse fixture replaces it


def _frames(n):
    return [Image.new("RGB", (8, 6), (i, 0, 0)) for i in range(n)]


def _rec(frames, model="pi3x"):
    """A fake model: each frame's points depend only on the frame, so windows chain exactly."""
    ids = [np.asarray(f)[0, 0, 0] for f in frames]
    pts = np.stack([np.random.default_rng(int(i)).random((4, 5, 3)) for i in ids])
    keep = np.ones(pts.shape[:3], bool)
    return mvs.Reconstruction(pts, keep, np.tile(np.eye(4), (len(frames), 1, 1)), 1.0, model)


def test_window_from_ram():
    assert mvs_local.window_for(16) == 10  # the 16 GB M4: 30-frame passes peaked at 12.8 GB
    assert mvs_local.window_for(64) == mvs_local.MAX_WINDOW
    assert mvs_local.window_for(4) == mvs_local.MIN_WINDOW


def test_failed_window_retries_smaller_and_chains(monkeypatch):
    monkeypatch.setenv(mvs_local.WINDOW_ENV, "12")
    sizes = []

    def worker(frames, model):  # "out of memory" above 6 frames
        sizes.append(len(frames))
        if len(frames) > 6:
            raise mvs_local.WorkerFailed("MPS backend out of memory")
        return _rec(frames, model)

    frames = _frames(10)
    rec = REAL_SAFE(frames, "pi3x", worker)
    assert sizes[0] == 10 and max(sizes[1:]) <= 6  # one pass failed, then windows of 6
    np.testing.assert_allclose(rec.view_points, _rec(frames).view_points, atol=1e-9)


def test_kaggle_failure_falls_back_to_this_machine(monkeypatch):
    calls = []

    def kaggle(jobs, model):
        raise remote.Unavailable("no network to kaggle.com")

    def local(frames, model):
        calls.append(len(frames))
        return _rec(frames, model)

    monkeypatch.setattr(remote, "run", kaggle)
    monkeypatch.setattr(mvs_local, "reconstruct_safe", local)
    monkeypatch.setattr(mvs.shutil, "which", lambda name: None)  # not a GPU machine
    a, b = _frames(3), _frames(5)
    mvs.ensure([a, b, a], "pi3x")  # the repeated set runs once
    assert calls == [3, 5]
    assert any("Kaggle not used" in n for n in mvs.pop_notes())
    rec = mvs.reconstruct(b, "pi3x")  # now a cache hit: nothing runs
    assert calls == [3, 5] and rec.view_points.shape[0] == 5


def test_kaggle_success_runs_nothing_here(monkeypatch):
    def kaggle(jobs, model):
        for path, frames in jobs:
            mvs.save(path, _rec(frames, model))
        return 300.0

    monkeypatch.setattr(remote, "run", kaggle)
    monkeypatch.setattr(mvs.shutil, "which", lambda name: None)
    mvs.ensure([_frames(4)], "pi3x")
    assert mvs.pop_notes() == ["reconstruction ran on Kaggle (GPU job, 5 min)"]


def test_kaggle_only_backend_raises(monkeypatch):
    monkeypatch.setenv(mvs.BACKEND_ENV, "kaggle")
    monkeypatch.setattr(remote, "run", lambda jobs, model: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(RuntimeError, match="Kaggle reconstruction failed"):
        mvs.ensure([_frames(2)], "pi3x")


def test_image_sets_match_the_chained_windows():
    from floorplan.pipeline import VIDEO_OVERLAP, image_sets

    imgs = list(range(70))
    sets = image_sets(imgs, 30)
    assert [s[0] for s in sets] == [0, 20, 40]
    assert all(len(s) == 30 for s in sets) and sets[1][:VIDEO_OVERLAP] == sets[0][-VIDEO_OVERLAP:]
    assert image_sets(imgs[:12], 30) == [imgs[:12]]


def test_child_processes_killed_for_memory_retry_smaller(monkeypatch, capsys):
    """Real child processes: a window that gets killed (as by the OS out of memory) is
    retried with smaller windows, and the chained result covers every frame."""
    monkeypatch.setattr(mvs_local, "WORKER_MODULE", "tests.fake_mvs_worker")
    monkeypatch.setenv(mvs_local.WINDOW_ENV, "10")
    frames = [Image.new("RGB", (16, 12), (i, 2 * i, 0)) for i in range(9)]
    rec = REAL_SAFE(frames, "pi3x")
    assert rec.view_points.shape == (9, 28, 37, 3)
    err = capsys.readouterr().err
    assert "killed by signal 9" in err and "retrying with 5 frames per window" in err


def test_tiny_window_setting_is_raised_to_the_minimum(monkeypatch):
    """FLOORPLAN_LOCAL_WINDOW below MIN_WINDOW cannot overlap: it runs at MIN_WINDOW."""
    monkeypatch.setenv(mvs_local.WINDOW_ENV, "2")
    sizes = []

    def worker(frames, model):
        sizes.append(len(frames))
        return _rec(frames, model)

    frames = _frames(9)
    rec = REAL_SAFE(frames, "pi3x", worker)
    assert max(sizes) == mvs_local.MIN_WINDOW
    np.testing.assert_allclose(rec.view_points, _rec(frames).view_points, atol=1e-9)


def test_kaggle_poll_survives_a_network_blip_but_not_an_outage(monkeypatch):
    """A failed status call while the GPU job runs does not abandon it; repeated ones do."""
    import time

    monkeypatch.setattr(remote, "POLL_S", 0)
    answers = iter([RuntimeError("blip"), False, RuntimeError("blip"), True])

    def done():
        a = next(answers)
        if isinstance(a, Exception):
            raise a
        return a

    remote._wait(done, time.perf_counter() + 60, "GPU job")  # returns on True

    def down():
        raise RuntimeError("kaggle kernels status failed: connection refused")

    with pytest.raises(RuntimeError, match="connection refused"):
        remote._wait(down, time.perf_counter() + 60, "GPU job")
