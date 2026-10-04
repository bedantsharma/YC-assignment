"""Damage stage of the video and photo tiers: the frames the reconstruction used -> detections
-> sizes on the measured surfaces -> flags and scope.

Frames. The detector sees exactly the images the model reconstructed (the video tier's
evenly spaced frames, or a room folder's photos), so every detection has a 3D point per
pixel. Pause-based frame choice for video is a ROADMAP item; even frames are the fallback.

Sizing. No intrinsics are stored, but the reconstruction gives a 3D point for every pixel
(`view_points`, at the model's resolution: the frame resized to cover it, centre-cropped).
The mask's outline pixels are looked up there, put through the same up-axis and scale
correction as the tier's cloud, rotated into the plan frame, and projected straight onto
the surface the mask's median point lies on (nearest plane within SURFACE_TOL_M, inside its
extent). Area = shoelace on the (u, v) outline. 90% interval by Monte Carlo: outline grown
or shrunk by +-MASK_PX pixels, horizontal and vertical scale drawn from the tier's measured
residual (intervals.RESIDUAL_REL), and the in-plane noise of the point map (spread of the
outline points about a smooth fit). Views are merged as on the LiDAR tier; an item seen
once is kept and marked unconfirmed (no depth images here to apply the two-view rule).
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from matplotlib.path import Path as MplPath
from PIL import Image

from floorplan.damage import detect, model_name
from floorplan.damage_geom import (
    MASK_PX,
    MC_DRAWS,
    Placed,
    SurfacePlane,
    _centroid,
    _shoelace,
    mask_outline,
    merge,
    surface_planes,
)
from floorplan.damage_lidar import DETECT_WORKERS, _overlay, _where
from floorplan.damage_rules import build
from floorplan.intervals import RESIDUAL_REL, correct_scale
from floorplan.output import Room

SURFACE_TOL_M = 0.3  # point maps are noisier than LiDAR planes
WALL_TOL_M = 0.15
INTERIOR_SAMPLES = 400
SEED = 0


def run_damage(
    images: list[Image.Image],
    ids: list[str],
    rec,
    vertical: np.ndarray,
    model: str,
    tier: str,
    rooms: list[Room],
    angle_deg: float,
    floor_z: float,
    overlay_dir: Path | None = None,
    crack_pass: bool = False,
):
    """(surfaces, damage, flags, scope, warnings) for the images of one reconstruction."""
    from floorplan.video import z_up

    planes = surface_planes(rooms, floor_z)
    rel_h, rel_v = RESIDUAL_REL[(tier, model)]
    rng = np.random.default_rng(SEED)
    with ThreadPoolExecutor(DETECT_WORKERS) as pool:
        found = list(
            pool.map(
                lambda a: detect(a[0], a[1], crack_pass=crack_pass), zip(ids, images, strict=True)
            )
        )

    def to_plan(p: np.ndarray) -> np.ndarray:
        q = correct_scale(z_up(p.astype(float), vertical), model, tier)
        t = np.radians(angle_deg)
        c, s = np.cos(t), np.sin(t)
        return np.column_stack([q[:, 0] * c + q[:, 1] * s, -q[:, 0] * s + q[:, 1] * c, q[:, 2]])

    placed, counts = [], {"detections": 0, "off_surface": 0}
    for v, (image_id, image, dets) in enumerate(zip(ids, images, found, strict=True)):
        counts["detections"] += len(dets)
        pts_map, keep = rec.view_points[v], rec.view_keep[v]
        kept = []
        for det in dets:
            p = place_from_points(
                det, image.size, pts_map, keep, to_plan, planes, rel_h, rel_v, rng
            )
            if p is None:
                counts["off_surface"] += 1
                continue
            p.image_id = image_id
            placed.append(p)
            kept.append(det)
        if overlay_dir is not None and dets:
            _overlay(image, dets, kept, overlay_dir / f"{image_id.replace('/', '_')}.jpg")

    merged = merge(placed)
    for m in merged:
        if len(set(m.views)) < 2:
            m.notes.append("seen in one image only (unconfirmed)")
    surfs, damage, flags, scope = build(merged, rooms)
    warnings = [
        f"damage: {model_name()} ({_where()}) on the {len(images)} {tier} images the "
        f"reconstruction used: {counts['detections']} detections, {counts['off_surface']} not "
        f"on a measured surface; {len(damage)} damage items after merging views; sizes from "
        "the model's point map projected onto the walls, intervals include the tier's scale "
        f"error ({100 * rel_h:.0f}% horizontal, {100 * rel_v:.0f}% vertical)"
    ]
    single = [d.id for d in damage if len(d.views) == 1]
    if single:
        warnings.append(f"damage: seen in one image only (unconfirmed): {', '.join(single)}")
    return surfs, damage, flags, scope, warnings


def model_pixels(px: np.ndarray, frame: tuple[int, int], grid: tuple[int, int]) -> np.ndarray:
    """Frame pixel (x, y) -> (row, col) in a point map of shape grid = (H, W), assuming the
    frame was resized to cover the grid and centre-cropped (MapAnything's preprocessing)."""
    w, h = frame
    gh, gw = grid
    s = max(gw / w, gh / h)
    ox, oy = (w * s - gw) / 2, (h * s - gh) / 2
    col = np.clip((px[:, 0] * s - ox).astype(int), 0, gw - 1)
    row = np.clip((px[:, 1] * s - oy).astype(int), 0, gh - 1)
    return np.column_stack([row, col])


def place_from_points(det, frame_size, pts_map, keep, to_plan, planes, rel_h, rel_v, rng):
    """One detection on the surface its point-map points lie on, with Monte Carlo draws."""
    if det.mask is None or not det.mask.any():
        return None
    outline = mask_outline(det.mask)
    if len(outline) < 3:
        return None
    grid = pts_map.shape[:2]
    ys, xs = np.nonzero(det.mask)
    pick = np.linspace(0, len(xs) - 1, min(INTERIOR_SAMPLES, len(xs))).astype(int)
    inner = model_pixels(np.column_stack([xs[pick], ys[pick]]) + 0.5, frame_size, grid)
    ok = keep[inner[:, 0], inner[:, 1]]
    if ok.sum() < 3:
        return None
    centre3d = np.median(to_plan(pts_map[inner[ok, 0], inner[ok, 1]]), axis=0)
    plane = _surface_of(centre3d, planes)
    if plane is None:
        return None

    rc = model_pixels(outline, frame_size, grid)
    good = keep[rc[:, 0], rc[:, 1]]
    if good.sum() < 3:
        return None
    pts = to_plan(pts_map[rc[good, 0], rc[good, 1]]) - plane.origin
    uv = np.column_stack([pts @ plane.u_axis, pts @ plane.v_axis])
    area = abs(_shoelace(uv))
    mask_px = float(det.mask.sum())
    px_size = float(np.sqrt(area / mask_px)) if mask_px else 0.0
    c = _centroid(uv)
    # in-plane noise of the point map: outline points' spread about a 3-point moving mean
    smooth = (np.roll(uv, 1, axis=0) + uv + np.roll(uv, -1, axis=0)) / 3
    noise = float(np.median(np.linalg.norm(uv - smooth, axis=1)))
    r_eq = np.sqrt(max(mask_px, 1.0) / np.pi)
    draws = np.empty(MC_DRAWS)
    for k in range(MC_DRAWS):
        grow = max(0.05, 1.0 + rng.uniform(-MASK_PX, MASK_PX) / r_eq)
        sh, sv = 1 + rng.normal(0, rel_h), 1 + rng.normal(0, rel_v)
        jitter = rng.normal(0, noise, uv.shape)
        q = c + (uv - c) * grow + jitter
        q = c + (q - c) * np.array([sh, sv] if plane.kind == "wall" else [sh, sh])
        draws[k] = abs(_shoelace(q))
    return Placed(
        image_id="",
        label=det.label,
        score=det.score,
        surface=plane,
        outline_uv=uv,
        area=area,
        area_draws=draws,
        region=(
            float(uv[:, 0].min()),
            float(uv[:, 1].min()),
            float(uv[:, 0].max()),
            float(uv[:, 1].max()),
        ),  # fmt: skip
        centre=(float(c[0]), float(c[1])),
        length=None,
        length_draws=None,
        px_size_m=px_size,
        note=det.note,
        traced=det.mask_source == "polyline",
    )


def _surface_of(p: np.ndarray, planes: list[SurfacePlane]) -> SurfacePlane | None:
    best, best_d = None, SURFACE_TOL_M
    for pl in planes:
        q = p - pl.origin
        d = abs(float(q @ pl.normal))
        if d >= best_d:
            continue
        u, v = float(q @ pl.u_axis), float(q @ pl.v_axis)
        if pl.kind == "wall":
            inside = pl.u_range[0] - WALL_TOL_M <= u <= pl.u_range[1] + WALL_TOL_M
            inside &= pl.v_range[0] - WALL_TOL_M <= v <= pl.v_range[1] + WALL_TOL_M
        else:
            inside = MplPath(pl.polygon).contains_point((u, v), radius=WALL_TOL_M)
        if inside:
            best, best_d = pl, d
    return best
