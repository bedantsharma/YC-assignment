from dataclasses import fields

import numpy as np
import pytest

from floorplan.capture import (
    VideoCapture,
    detect_format,
    load_lidar,
    load_photos,
    load_video,
    resolve_tier,
)


def test_detects_each_format(stray_capture, arkit_capture, photo_capture, tmp_path):
    clip = tmp_path / "walk.MOV"
    clip.write_bytes(b"")
    assert detect_format(stray_capture) == "stray"
    assert detect_format(arkit_capture) == "arkitscenes"
    assert detect_format(clip) == "video"
    assert detect_format(photo_capture) == "photos"


def test_detect_rejects_unknown_folder(tmp_path):
    with pytest.raises(ValueError, match="not a recognised capture"):
        detect_format(tmp_path)


def test_default_tier_follows_format(stray_capture, photo_capture):
    assert resolve_tier("stray", None) == "lidar"
    assert resolve_tier("photos", None) == "photo"


def test_rejects_tier_the_format_cannot_provide():
    with pytest.raises(ValueError, match="photo tier"):
        resolve_tier("stray", "photo")


def test_stray_poses_are_converted_to_z_up(stray_capture):
    cap = load_lidar(stray_capture)
    # Stray camera sits 1.5 m up along y; in our frame "up" is z
    np.testing.assert_allclose(cap.poses[0][:3, 3], [0.0, 0.0, 1.5], atol=1e-9)


def test_stray_intrinsics_scaled_to_depth_resolution(stray_capture):
    cap = load_lidar(stray_capture)
    np.testing.assert_allclose(cap.intrinsics[0][[0, 1, 0, 1], [0, 1, 2, 2]], [200, 200, 128, 96])


def test_arkit_poses_are_inverted_to_camera_to_world(arkit_capture):
    cap = load_lidar(arkit_capture)
    # world-to-camera translation (0, 0, -1) means the camera sits at z = +1
    np.testing.assert_allclose(cap.poses[0][:3, 3], [0.0, 0.0, 1.0], atol=1e-9)


def test_arkit_drops_depth_frames_without_a_nearby_pose(arkit_capture):
    cap = load_lidar(arkit_capture)
    assert [p.name for p in cap.depth_paths] == ["42444946_10.000.png", "42444946_10.100.png"]


def test_video_from_lidar_recording_exposes_only_the_video(stray_capture):
    video = load_video(stray_capture)
    assert [f.name for f in fields(VideoCapture)] == ["path"]
    assert video.path == stray_capture / "rgb.mp4"


def test_video_from_arkitscenes_is_the_mov(arkit_capture):
    assert load_video(arkit_capture).path == arkit_capture / "42444946.mov"


def test_photo_rooms_come_from_subfolders_in_name_order(photo_capture):
    rooms = load_photos(photo_capture).rooms
    assert list(rooms) == ["Room 1 Kitchen", "Room 2 Hallway"]
    assert [p.name for p in rooms["Room 1 Kitchen"]] == ["IMG_0.jpg", "IMG_1.jpg", "IMG_2.jpg"]


def test_flat_photo_folder_is_one_room(tmp_path):
    from PIL import Image

    for i in range(2):
        Image.new("RGB", (8, 6)).save(tmp_path / f"p{i}.jpg")
    assert list(load_photos(tmp_path).rooms) == [tmp_path.name]
