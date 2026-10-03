import numpy as np
from PIL import Image

from floorplan.capture import load_lidar
from floorplan.cloud import fuse, voxel_downsample


def test_fused_flat_depth_lands_on_one_plane_in_world(stray_capture):
    # Fixture camera: 1.5 m up, identity rotation in Stray's y-up world, so its optical
    # axis maps to -y in our z-up frame; flat 2 m depth -> the plane y = -2.
    points = fuse(load_lidar(stray_capture), voxel=0.0)
    np.testing.assert_allclose(points[:, 1], -2.0, atol=1e-6)
    centre = points[np.argmin(np.abs(points[:, 0]) + np.abs(points[:, 2] - 1.5))]
    np.testing.assert_allclose(centre, [0.0, -2.0, 1.5], atol=0.02)


def test_fuse_drops_low_confidence_and_far_depth(stray_capture):
    conf = np.full((192, 256), 2, np.uint8)
    conf[:, :128] = 1  # left half low confidence
    for name in ("000000", "000001"):
        Image.fromarray(conf).save(stray_capture / "confidence" / f"{name}.png")
    points = fuse(load_lidar(stray_capture), voxel=0.0)
    assert len(points) == 2 * 192 * 128
    assert len(fuse(load_lidar(stray_capture), voxel=0.0, max_depth=1.5)) == 0


def test_voxel_downsample_keeps_one_point_per_cell():
    pts = np.array([[0.001, 0.001, 0.001], [0.004, 0.002, 0.003], [0.5, 0.5, 0.5]])
    out = voxel_downsample(pts, 0.01)
    assert len(out) == 2
    np.testing.assert_allclose(out[out[:, 0] < 0.1][0], [0.0025, 0.0015, 0.002])
