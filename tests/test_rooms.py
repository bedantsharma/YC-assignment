import numpy as np
import pytest

from floorplan.plan2d import (
    Grid,
    dominant_angle,
    make_grid,
    observed_mask,
    segment_rooms,
    wall_mask,
)
from floorplan.rooms import Edge, _snap_to_surface, measure_room, rectilinear_outline, signed_area
from tests.synthetic import two_rooms

RES = 0.03


def test_outline_of_an_l_shaped_mask_has_six_axis_aligned_edges():
    grid = Grid(0.0, np.zeros(2), 0.1, (60, 60))
    mask = np.zeros(grid.shape, bool)
    mask[10:50, 10:30] = True  # 4 m x 2 m
    mask[10:30, 30:50] = True  # plus 2 m x 2 m -> L shape
    mask[25, 30:33] = False  # a nick smaller than min_edge must not create edges
    shape = rectilinear_outline(mask, grid)
    assert len(shape.edges) == 6
    assert signed_area(shape.polygon) == pytest.approx(12.0, abs=0.3)


@pytest.fixture(scope="module")
def measured():
    pts = two_rooms(angle_deg=30.0, ceiling=2.5)
    grid = make_grid(pts, dominant_angle(pts), RES)
    walls = wall_mask(pts, grid, floor_z=0.0)
    labels, _ = segment_rooms(walls, observed_mask(pts, grid, floor_z=0.0), RES)
    rooms = [measure_room(labels == k, pts, grid, walls, floor_z=0.0) for k in (1, 2)]
    return sorted(rooms, key=lambda r: r.area)


def test_walls_snap_to_the_wall_surfaces(measured):
    small, big = measured
    assert sorted(e.length for e in small.edges) == pytest.approx([2.95, 2.95, 3, 3], abs=0.01)
    assert sorted(e.length for e in big.edges) == pytest.approx([3, 3, 3.95, 3.95], abs=0.01)
    assert big.area == pytest.approx(3.95 * 3, abs=0.05)
    assert all(e.supported for e in big.edges)
    assert all(0 < e.sigma < 0.02 for e in big.edges)


def test_room_floor_and_ceiling(measured):
    room = measured[1]
    assert room.floor.z == pytest.approx(0.0, abs=0.003)
    assert room.ceiling.z - room.floor.z == pytest.approx(2.5, abs=0.005)


def _face(u, v0, v1, h1, n, rng):
    return np.stack([u + rng.normal(0, 0.004, n), rng.uniform(v0, v1, n)], 1), rng.uniform(
        0.05, h1, n
    )


def _snap(furniture_top, wall_top):
    """Edge u = 0 running +v (outward +u); furniture at u = 0.05, wall at u = 0.22."""
    rng = np.random.default_rng(1)
    parts = [
        _face(0.05, 0.2, 0.8, furniture_top, 9_000, rng),
        _face(0.05, 2.2, 2.8, furniture_top, 9_000, rng),
        _face(0.22, 0.0, 3.0, wall_top, 20_000, rng),
    ]
    uv = np.concatenate([p[0] for p in parts])
    h = np.concatenate([p[1] for p in parts])
    edge = Edge(axis=0, coord=0.0)
    _snap_to_surface(edge, np.array([0.0, 0.0]), np.array([0.0, 3.0]), uv, h)
    return edge.coord


def test_wall_snap_skips_furniture_in_front_of_a_full_height_wall():
    assert _snap(furniture_top=2.1, wall_top=3.3) == pytest.approx(0.22, abs=0.01)


def test_wall_snap_keeps_the_nearest_face_when_the_scan_stops_low():
    # A's c00a170fe1: nothing above 1.7 m, so a near face cannot be told from furniture
    assert _snap(furniture_top=1.7, wall_top=1.7) == pytest.approx(0.05, abs=0.01)


def test_room_east_wall_is_the_wall_not_the_wardrobes_in_front_of_it():
    # c_damage_02: wardrobes (top 2.1 m) 18 cm in front of a 3.3 m wall. Above the 2.3 m
    # wall band only the wall continues, so measure_room must look above the band.
    from tests.synthetic import slab, wall

    ceiling = 3.3
    wardrobes = [wall((3.82, y0), (3.82, y0 + 0.6), z1=2.1) for y0 in (0.2, 2.2)]
    pts = np.concatenate(
        [
            *wardrobes,
            *wardrobes,  # dense enough to pass the 30% face threshold, as in the scan
            wall((0, 0), (4, 0), z1=ceiling),
            wall((4, 0), (4, 3), z1=ceiling),
            wall((4, 3), (0, 3), z1=ceiling),
            wall((0, 3), (0, 0), z1=ceiling),
            slab(0, 4, 0, 3, 0.0),
            slab(0, 4, 0, 3, ceiling),
        ]
    )
    pts += np.random.default_rng(2).normal(0, 0.004, pts.shape)
    grid = make_grid(pts, 0.0, RES)
    walls = wall_mask(pts, grid, floor_z=0.0)
    mask = np.zeros(grid.shape, bool)
    ij = grid.cells(np.array([[0.15, 0.15], [3.7, 2.85]]))
    mask[ij[0, 0] : ij[1, 0], ij[0, 1] : ij[1, 1]] = True
    room = measure_room(mask, pts, grid, walls, floor_z=0.0)
    xs = room.polygon[:, 0]  # angle 0: plan u = world x
    assert xs.max() - xs.min() == pytest.approx(4.0, abs=0.02)
