"""Tiny fake captures in each supported format, written to a temp directory."""

import numpy as np
import pytest
from PIL import Image


def _depth_png(path, metres=2.0):
    Image.fromarray(np.full((192, 256), int(metres * 1000), np.uint16)).save(path)


def _conf_png(path):
    Image.fromarray(np.full((192, 256), 2, np.uint8)).save(path)


@pytest.fixture
def stray_capture(tmp_path):
    """Stray Scanner layout: 2 frames, camera 1.5 m above the origin (y is up), no rotation."""
    d = tmp_path / "stray01"
    (d / "depth").mkdir(parents=True)
    (d / "confidence").mkdir()
    rows = ["timestamp, frame, x, y, z, qx, qy, qz, qw, fx, fy, cx, cy"]
    for i in range(2):
        _depth_png(d / "depth" / f"{i:06d}.png")
        _conf_png(d / "confidence" / f"{i:06d}.png")
        rows.append(f"{i * 0.1}, {i:06d}, 0.0, 1.5, 0.0, 0, 0, 0, 1, 1500, 1500, 960, 720")
    (d / "odometry.csv").write_text("\n".join(rows) + "\n")
    (d / "camera_matrix.csv").write_text("1500, 0, 960\n0, 1500, 720\n0, 0, 1")
    (d / "rgb.mp4").write_bytes(b"")
    (d / "imu.csv").write_text("timestamp, a_x, a_y, a_z, alpha_x, alpha_y, alpha_z\n")
    return d


@pytest.fixture
def arkit_capture(tmp_path):
    """ARKitScenes layout: 3 depth frames, 2 poses (world-to-camera, translation 0, 0, -1).

    The depth frame at t=10.200 has no pose within 10 ms and must be dropped.
    """
    d = tmp_path / "42444946"
    for sub in ("lowres_depth", "confidence", "lowres_wide_intrinsics"):
        (d / sub).mkdir(parents=True)
    for t in ("10.000", "10.100", "10.200"):
        name = f"42444946_{t}"
        _depth_png(d / "lowres_depth" / f"{name}.png")
        _conf_png(d / "confidence" / f"{name}.png")
        (d / "lowres_wide_intrinsics" / f"{name}.pincam").write_text(
            "256 192 214.0 214.0 128.0 96.0"
        )
    (d / "lowres_wide.traj").write_text("10.002 0 0 0 0 0 -1\n10.098 0 0 0 0 0 -1\n")
    (d / "42444946.mov").write_bytes(b"")
    return d


@pytest.fixture
def photo_capture(tmp_path):
    """Per-room photo folders."""
    d = tmp_path / "photos01"
    for room, n in (("Room 2 Hallway", 2), ("Room 1 Kitchen", 3)):
        (d / room).mkdir(parents=True)
        for i in range(n):
            Image.new("RGB", (8, 6)).save(d / room / f"IMG_{i}.jpg")
    (d / "Room 1 Kitchen" / "notes.txt").write_text("not a photo")
    return d
