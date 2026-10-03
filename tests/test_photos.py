from pathlib import Path

import numpy as np
from PIL import Image

from floorplan.output import Measurement, Room
from floorplan.photos import PHOTO_LONG_SIDE, few_photo_warnings, label_rooms, load_images


def _room(rid, x0, y0, x1, y1):
    poly = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return Room(rid, rid, poly, Measurement(1.0, 1.0, 1.0, "m2"))


def test_rooms_are_named_after_the_folder_photographed_from_inside():
    rooms = [_room("r1", 0, 0, 4, 4), _room("r2", 5, 0, 9, 4)]
    cams = np.array([[1, 1], [2, 2], [3, 1], [6, 1], [7, 2], [8.5, 3.5]])
    folders = ["kitchen", "kitchen", "hall", "bedroom", "bedroom", "bedroom"]
    warnings = label_rooms(rooms, 0.0, cams, folders)
    assert [r.label for r in rooms] == ["kitchen", "bedroom"]
    assert warnings == ["no plan room found for folder(s): hall"]


def test_labels_use_the_plan_frame_rotation():
    rooms = [_room("r1", 0, 0, 4, 4)]  # plan frame, rotated 90 deg from world
    cams_world = np.array([[-2.0, 2.0]])  # plan (2, 2) after rotating world by -90 deg
    label_rooms(rooms, 90.0, cams_world, ["study"])
    assert rooms[0].label == "study"


def test_room_without_photos_inside_takes_the_nearest_folder_and_warns():
    rooms = [_room("r1", 0, 0, 4, 4), _room("r2", 10, 0, 14, 4)]
    cams = np.array([[1, 1], [9, 2]])
    warnings = label_rooms(rooms, 0.0, cams, ["kitchen", "hall"])
    assert [r.label for r in rooms] == ["kitchen", "hall"]
    assert any("r2: no photo taken inside" in w for w in warnings)


def test_folder_spanning_two_rooms_gets_numbered_labels():
    rooms = [_room("r1", 0, 0, 4, 4), _room("r2", 5, 0, 9, 4)]
    label_rooms(rooms, 0.0, np.array([[1, 1], [6, 1]]), ["living", "living"])
    assert [r.label for r in rooms] == ["living", "living (2)"]


def test_load_images_applies_exif_rotation_and_resizes(tmp_path):
    img = Image.new("RGB", (2000, 1500), "white")
    exif = img.getexif()
    exif[0x0112] = 6  # stored landscape, display rotated 90 deg (portrait)
    img.save(tmp_path / "a.jpg", exif=exif)
    (out,) = load_images([tmp_path / "a.jpg"])
    assert out.size == (720, PHOTO_LONG_SIDE)


def test_photo_tier_end_to_end_names_rooms_from_folders(photo_capture, monkeypatch):
    # the model is replaced by a synthetic two-room cloud; everything after it is real.
    # Folders (sorted): "Room 1 Kitchen" (3 photos) shot in room A, "Room 2 Hallway" (2) in B
    from floorplan import mvs
    from floorplan.pipeline import run
    from tests.synthetic import two_rooms

    pts = two_rooms(angle_deg=0.0)
    cams = {3: [(1, 1), (2, 2), (3, 1)], 2: [(5, 1), (6, 2)]}

    def fake(images, model):
        n = len(images)
        poses = np.tile(np.eye(4), (n, 1, 1))
        poses[:, :3, :3] = [[1, 0, 0], [0, 0, 1], [0, -1, 0]]  # image down = world -z
        poses[:, :2, 3] = cams[n]
        poses[:, 2, 3] = 1.5
        keep = np.ones((1, len(pts), 1), bool)
        return mvs.Reconstruction(pts[None, :, None, :], keep, poses, 0.1, model)

    monkeypatch.setattr(mvs, "reconstruct", fake)
    result = run(photo_capture)
    assert result.capture.tier == "photo"
    area = {r.label: r.floor_area.value for r in result.rooms}
    assert sorted(area) == ["Room 1 Kitchen", "Room 2 Hallway"]
    assert area["Room 1 Kitchen"] > area["Room 2 Hallway"]  # room A 3.95 x 3, room B 2.95 x 3
    assert any("NOT stitched" in w for w in result.warnings)
    assert all(r.floor_area.lo < r.floor_area.value < r.floor_area.hi for r in result.rooms)
    xs = [np.asarray(r.polygon)[:, 0] for r in result.rooms]  # laid out without overlap
    assert xs[0].max() < xs[1].min() or xs[1].max() < xs[0].min()


def test_warns_about_folders_with_too_few_photos():
    w = few_photo_warnings({"hall": [Path("a")] * 3, "kitchen": [Path("b")] * 6})
    assert len(w) == 1 and "'hall': 3 photos" in w[0]
