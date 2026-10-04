import numpy as np
from scipy.spatial.transform import Rotation

from floorplan.damage_frames import NEED, patches, sees, select, still_segments
from floorplan.damage_geom import surface_planes
from floorplan.output import Measurement, Room, Wall

FPS = 30.0
K = np.array([[1340.0, 0, 960], [0, 1340.0, 720], [0, 0, 1]])
SIZE = (1920, 1440)


def _m(v, half=0.01, unit="m"):
    return Measurement(v, v - half, v + half, unit)


def _room(w=4.0, d=3.0) -> Room:
    poly = [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]
    walls = [
        Wall(f"r1.w{k + 1}", poly[k], poly[(k + 1) % 4], _m(w if k % 2 == 0 else d))
        for k in range(4)
    ]
    return Room("r1", "r1", poly, _m(w * d, 0.1, "m2"), _m(2.5), walls)


def _looking(yaw_deg: float, at=(2.0, 1.5, 1.5)) -> np.ndarray:
    """Camera-to-world pose (OpenCV axes, z up) looking horizontally along yaw."""
    yaw = np.radians(yaw_deg)
    fwd = np.array([np.cos(yaw), np.sin(yaw), 0.0])
    down = np.array([0.0, 0.0, -1.0])
    right = np.cross(down, fwd)
    pose = np.eye(4)
    pose[:3, :3] = np.column_stack([right, down, fwd])
    pose[:3, 3] = at
    return pose


def test_still_segments_finds_the_hold():
    poses = []
    for k in range(int(6 * FPS)):  # walk 2 s, hold 2 s, walk 2 s
        t = k / FPS
        x = t if t < 2 else 2.0 if t < 4 else 2.0 + (t - 4)
        poses.append(_looking(0.0, (x, 1.0, 1.5)))
    segs = still_segments(np.array(poses), FPS)
    assert len(segs) == 1
    a, b = segs[0]
    assert abs(a / FPS - 2.0) < 0.4 and abs(b / FPS - 4.0) < 0.4


def test_turning_on_the_spot_is_not_a_pause():
    poses = np.array([_looking(30.0 * k / FPS) for k in range(int(4 * FPS))])  # 30 deg/s
    assert still_segments(poses, FPS) == []


def test_sees_face_on_wall_not_behind_or_far_or_hidden():
    room = _room()
    pts, normals, ids = patches(surface_planes([room], 0.0))
    facing_w1 = _looking(-90.0, (2.0, 1.5, 1.5))  # looking at y = 0 (wall r1.w1)
    vis = sees(facing_w1, K, SIZE, pts, normals)
    ids = np.array(ids)
    assert vis[ids == "r1.w1.face"].mean() >= 0.25  # ~2.1 x 1.6 m of a 4 x 2.5 m wall
    assert not vis[ids == "r1.w3.face"].any()  # behind the camera
    far = _looking(-90.0, (2.0, 2.9, 1.5))  # 2.9 m from the wall: still in range
    assert sees(far, K, SIZE, pts, normals)[ids == "r1.w1.face"].any()
    wall_dist = np.full((192, 256), 0.5)  # something 0.5 m in front of the camera everywhere
    assert not sees(facing_w1, K, SIZE, pts, normals, wall_dist).any()


def test_select_puts_pauses_first_and_covers_the_room():
    room = _room()
    planes = surface_planes([room], 0.0)
    # 12 s turning slowly on the spot (1 deg per frame), then a 2 s hold facing r1.w2
    poses = [_looking(float(k)) for k in range(360)]
    poses += [_looking(0.0)] * int(2 * FPS)
    sel = select(np.array(poses), K, SIZE, planes, FPS, budget=20)
    assert len(sel.pauses) == 1
    a, b = sel.pauses[0]
    assert a <= sel.frames[0] <= b  # pause frames come first
    assert 0 < len(sel.frames) <= 20
    # from the centre at 1.5 m height, the walls are seen; the ceiling only partly
    assert sel.seen_once > 0.5
    assert 0.0 <= sel.seen_need <= sel.seen_once <= 1.0
    assert "r1.w1.face" not in sel.unseen or sel.unseen["r1.w1.face"] < 0.6


def test_select_respects_budget_and_gap():
    room = _room()
    planes = surface_planes([room], 0.0)
    poses = np.array([_looking(float(k)) for k in range(360)])
    sel = select(poses, K, SIZE, planes, FPS, budget=3)
    assert len(sel.frames) <= 3
    assert all(abs(a - b) >= 10 for i, a in enumerate(sel.frames) for b in sel.frames[i + 1 :])


def test_need_is_two():
    assert NEED == 2


def test_rotation_helper_is_orthonormal():
    r = _looking(37.0)[:3, :3]
    assert np.allclose(r.T @ r, np.eye(3))
    assert Rotation.from_matrix(r).magnitude() > 0


def test_dwell_catches_a_slow_look_that_is_not_a_still_hold():
    from floorplan.damage_frames import dwell_segments

    room = _room()
    planes = surface_planes([room], 0.0)
    poses = []
    for k in range(int(5 * FPS)):  # 5 s drifting 8 cm/s sideways, eyes on one spot of r1.w1
        x = 1.8 + 0.08 * k / FPS
        target = np.array([2.0, 0.0, 1.5])
        yaw = np.degrees(np.arctan2(target[1] - 1.0, target[0] - x))
        poses.append(_looking(yaw, (x, 1.0, 1.5)))
    poses = np.array(poses)
    assert still_segments(poses, FPS) == []  # too fast to count as still
    segs = dwell_segments(poses, np.broadcast_to(K, (len(poses), 3, 3)), SIZE, planes, FPS)
    assert segs and segs[0][1] - segs[0][0] >= 3 * FPS
