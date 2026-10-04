import json

import numpy as np
import pytest
from PIL import Image

from floorplan import damage
from floorplan.damage import Detection, outline, parse_items
from floorplan.damage_geom import View, merge, place, surface_planes
from floorplan.damage_lidar import _rot_pixels, upright
from floorplan.damage_rules import build
from floorplan.output import Capture, Measurement, Result, Room, Wall

FLOOR_Z = -1.4


def _m(v, half=0.01, unit="m"):
    return Measurement(v, v - half, v + half, unit)


def _room() -> Room:
    """4 x 3 m room, counter-clockwise from (0, 0); 2.5 m ceiling."""
    poly = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
    walls = [
        Wall(f"r1.w{k + 1}", poly[k], poly[(k + 1) % 4], _m(4.0 if k % 2 == 0 else 3.0))
        for k in range(4)
    ]
    return Room("r1", "r1", poly, _m(12.0, 0.1, "m2"), _m(2.5), walls)


def _camera_facing_w1(x=1.5, y=2.0, height=1.5):
    """Camera inside the room looking straight at wall r1.w1 (y = 0), image upright."""
    pose = np.eye(4)
    # camera axes in world: x right = -world x, y down = -world z, z forward = -world y
    pose[:3, :3] = np.column_stack([[-1, 0, 0], [0, 0, -1], [0, -1, 0]])
    pose[:3, 3] = [x, y, FLOOR_Z + height]
    K = np.array([[1000.0, 0, 640], [0, 1000.0, 480], [0, 0, 1]])
    return View("v0", pose, K, (1280, 960)), K


def _square_mask(cx, cy, half, shape=(960, 1280)):
    m = np.zeros(shape, bool)
    m[int(cy - half) : int(cy + half), int(cx - half) : int(cx + half)] = True
    return m


def test_square_on_wall_has_its_true_size_and_position():
    room = _room()
    view, K = _camera_facing_w1()
    # 100 px square at the image centre, wall 2 m away, f = 1000: 0.2 m side
    det = Detection("v0", "hole", 0.9, (590, 430, 690, 530), mask=_square_mask(640, 480, 50))
    planes = surface_planes([room], FLOOR_Z)
    p = place(view, 0.0, planes, [room], det, np.random.default_rng(0))
    assert p.surface.surface_id == "r1.w1.face"
    assert p.area == pytest.approx(0.04, rel=0.03)
    # wall runs from x=0 to x=4; camera at x=1.5 and 1.5 m up
    assert p.centre[0] == pytest.approx(1.5, abs=0.01)
    assert p.centre[1] == pytest.approx(1.5, abs=0.01)
    lo, hi = np.percentile(p.area_draws, [5, 95])
    assert lo < 0.04 < hi
    assert p.distance_m == pytest.approx(2.0, abs=0.01)


def test_plan_rotation_is_undone():
    """Same scene with the world rotated by 30 degrees and the plan angle set to 30."""
    room = _room()
    view, K = _camera_facing_w1()
    t = np.radians(30.0)
    rz = np.eye(4)
    rz[:2, :2] = [[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]]
    rotated = View("v0", rz @ view.pose, K, view.size)
    det = Detection("v0", "hole", 0.9, (590, 430, 690, 530), mask=_square_mask(640, 480, 50))
    planes = surface_planes([room], FLOOR_Z)
    p = place(rotated, 30.0, planes, [room], det, np.random.default_rng(0))
    assert p.surface.surface_id == "r1.w1.face"
    assert p.centre[0] == pytest.approx(1.5, abs=0.01)


def test_merge_pools_views_of_one_damage():
    room = _room()
    planes = surface_planes([room], FLOOR_Z)
    placed = []
    for k, x in enumerate((1.4, 1.5, 1.6)):
        view, _ = _camera_facing_w1(x=x)
        cx = 640 + (x - 1.5) * 500  # keep the same wall spot in view
        det = Detection(f"v{k}", "hole", 0.8, (0, 0, 1, 1), mask=_square_mask(cx, 480, 50))
        placed.append(place(view, 0.0, planes, [room], det, np.random.default_rng(k)))
    merged = merge(placed)
    assert len(merged) == 1
    assert len(merged[0].views) == 3


def test_upright_turn_keeps_projection():
    rng = np.random.default_rng(1)
    w, h = 1920, 1440
    K = np.array([[1340.0, 0, 962], [0, 1340.0, 723], [0, 0, 1]])
    # sideways phone: camera x axis points down in the world
    pose = np.eye(4)
    pose[:3, :3] = np.column_stack([[0, 0, -1], [-1, 0, 0], [0, 1, 0]])
    turns, pn, Kn = upright(pose, K, (w, h))
    assert -pn[:3, 1] @ [0, 0, 1] > 0.99  # image up is world up
    A = _rot_pixels(turns, w, h)
    for _ in range(5):
        X = np.array([rng.uniform(-1, 1), 3.0, rng.uniform(-1, 1)])
        xc = np.linalg.inv(pose)[:3] @ np.append(X, 1)
        raw = K @ xc
        raw = raw / raw[2]
        xn = np.linalg.inv(pn)[:3] @ np.append(X, 1)
        new = Kn @ xn
        new = new / new[2]
        assert np.allclose((A @ raw)[:2], new[:2], atol=1e-6)


def test_rot_pixels_matches_numpy():
    img = np.zeros((4, 6))
    img[1, 4] = 1  # x = 4, y = 1
    for turns in range(4):
        rot = np.rot90(img, turns)
        y, x = np.argwhere(rot == 1)[0]
        A = _rot_pixels(turns, 6, 4)
        mapped = A @ np.array([4.5, 1.5, 1])
        assert mapped[:2] == pytest.approx([x + 0.5, y + 0.5])


def test_parse_items_cleans_and_drops():
    items = [
        {"label": "Mold", "box_2d": [100, 200, 300, 400], "confidence": 0.7},
        {"label": "hole", "box_2d": [500, 900, 400, 800], "confidence": 2},  # swapped, >1
        {"label": "chair", "box_2d": [0, 0, 10, 10]},
        {"label": "crack", "box_2d": [1, 2, 3]},
        "junk",
    ]
    out = parse_items(items)
    assert [o["label"] for o in out] == ["mould", "hole"]
    assert out[1]["box_2d"] == [400, 800, 500, 900]
    assert out[1]["confidence"] == 1.0


def test_outline_finds_dark_disk():
    yy, xx = np.mgrid[0:200, 0:200]
    grey = np.full((200, 200), 200, np.uint8)
    grey[(xx - 100) ** 2 + (yy - 100) ** 2 <= 20**2] = 40
    image = Image.fromarray(grey).convert("RGB")
    mask, source = outline(image, (70, 70, 130, 130))  # loose box
    assert source == "contrast"
    assert mask.sum() == pytest.approx(np.pi * 20**2, rel=0.1)


def test_outline_falls_back_to_ellipse_on_blank_wall():
    image = Image.new("RGB", (100, 100), (180, 180, 180))
    mask, source = outline(image, (40, 40, 60, 60))
    assert source == "ellipse"
    assert mask.sum() == pytest.approx(np.pi * 10**2, rel=0.15)


def test_detect_replays_cache_without_network(tmp_path, monkeypatch):
    monkeypatch.setenv(damage.CACHE_ENV, str(tmp_path))
    monkeypatch.setenv(damage.CACHE_ONLY_ENV, "1")
    image = Image.new("RGB", (200, 100), (180, 180, 180))
    with pytest.raises(RuntimeError, match="cache miss"):
        damage.detect("x", image)
    path = damage._cache_path(damage._encode(image), damage.model_name())
    path.parent.mkdir(parents=True)
    items = [{"label": "hole", "box_2d": [400, 450, 600, 550], "confidence": 0.9}]
    path.write_text(json.dumps({"items": items}))
    dets = damage.detect("x", image)
    assert len(dets) == 1
    assert dets[0].box == pytest.approx((90, 40, 110, 60))


def test_parse_json_strips_fences():
    assert damage._parse_json('```json\n[{"a": 1}]\n```') == [{"a": 1}]
    assert damage._parse_json("Here: [] done") == []
    assert damage._parse_json("nonsense") == []


def _placed_on_w1(label, mask, x=1.5, score=0.9):
    room = _room()
    view, _ = _camera_facing_w1(x=x)
    det = Detection("v0", label, score, (0, 0, 1, 1), mask=mask)
    planes = surface_planes([room], FLOOR_Z)
    return room, place(view, 0.0, planes, [room], det, np.random.default_rng(0))


def test_rules_and_scope_for_a_hole_next_to_a_socket():
    room, hole = _placed_on_w1("hole", _square_mask(640, 480, 20))
    _, socket = _placed_on_w1("outlet_or_switch", _square_mask(740, 480, 15))
    surfs, dmg, flags, scope = build(merge([hole, socket]), [room])
    assert [d.damage_class for d in dmg] == ["hole"]
    assert {f.rule_id for f in flags} == {"R10"}
    actions = [s.action for s in scope]
    assert any(a.startswith("DRY PATCH") for a in actions)
    assert any(a.startswith("PNT S/P") for a in actions)
    result = Result(Capture("c", "lidar", "x"), [room], surfaces=surfs, damage=dmg,
                    flags=flags, scope=scope)  # fmt: skip
    assert result.validate() == []
    assert result.to_dict()["damage"][0]["centre"][1] == pytest.approx(1.5, abs=0.01)


def test_large_mould_fires_professional_remediation():
    # 800 px square at 2 m with f = 1000: 1.6 m side, 2.56 m2
    room, mould = _placed_on_w1("mould", _square_mask(640, 480, 400))
    _, dmg, flags, scope = build(merge([mould]), [room])
    assert {"R3", "R4"} <= {f.rule_id for f in flags}
    assert any(s.action.startswith("WTR / HMR") for s in scope)


def test_crack_gets_length_and_aesthetic_band():
    mask = np.zeros((960, 1280), bool)
    mask[478:482, 440:840] = True  # 400 px long, 4 px wide: 0.8 m x 8 mm at 2 m
    room, crack = _placed_on_w1("crack", mask)
    _, dmg, flags, _ = build(merge([crack]), [room])
    assert dmg[0].length.value == pytest.approx(0.8, rel=0.05)
    assert dmg[0].length.lo <= 0.8 <= dmg[0].length.hi
    # 8 mm wide but only 4 px: 8 - 4 = 4 mm is not confidently above 5 mm
    assert {f.rule_id for f in flags} == {"R8"}


def test_parse_crack_items():
    items = [
        {"points": [[100, 200], [150, 260], ["x", 1]], "confidence": 0.8, "note": "hairline"},
        {"points": [[1, 2]]},  # too short
        {"box_2d": [1, 2, 3, 4]},
    ]
    out = damage.parse_crack_items(items)
    assert len(out) == 1
    assert out[0]["points"] == [(100.0, 200.0), (150.0, 260.0)]


def test_crack_pass_replaces_overlapping_main_crack(tmp_path, monkeypatch):
    monkeypatch.setenv(damage.CACHE_ENV, str(tmp_path))
    monkeypatch.setenv(damage.CACHE_ONLY_ENV, "1")
    image = Image.new("RGB", (1000, 500), (180, 180, 180))
    data, model = damage._encode(image), damage.model_name()
    main = [
        {"label": "crack", "box_2d": [100, 100, 300, 400], "confidence": 0.6},
        {"label": "hole", "box_2d": [600, 600, 700, 700], "confidence": 0.9},
    ]
    crack = [{"points": [[150, 150], [250, 350]], "confidence": 0.7, "note": "faint"}]
    for items, version in ((main, damage.PROMPT_VERSION), (crack, damage.CRACK_PROMPT_VERSION)):
        path = damage._cache_path(data, model, version)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"items": items}))
    dets = damage.detect("x", image, crack_pass=True)
    assert sorted((d.label, d.source) for d in dets) == [("crack", "crack"), ("hole", "main")]
    traced = next(d for d in dets if d.source == "crack")
    assert traced.mask_source == "polyline"
    assert traced.points[0] == pytest.approx((150.0, 75.0))
