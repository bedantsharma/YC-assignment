"""Command line: `floorplan run <capture> [--tier lidar|video|photo] [--out outputs]`."""

import argparse
import sys
from pathlib import Path

from floorplan.capture import detect_format, resolve_tier, unpack
from floorplan.output import TIERS, write_json
from floorplan.pipeline import run
from floorplan.render import render_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="floorplan")
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", help="process one capture into plan.json and plan.png")
    p_run.add_argument("capture", type=Path, help="capture folder or video file")
    p_run.add_argument("--tier", choices=TIERS, help="default: inferred from the capture")
    p_run.add_argument("--out", type=Path, default=Path("outputs"), help="output root")
    p_run.add_argument(
        "--drift",
        action="store_true",
        help="re-align poses on the walls (experimental, off by default: docs/drift_ablation.md)",
    )
    p_run.add_argument("--frames", type=int, default=30, help="video tier: frames to use")
    p_run.add_argument(
        "--up",
        choices=["auto", "top", "right", "bottom", "left"],
        default="auto",
        help="video tier: side of the stored frame that is up (default: metadata or brightness)",
    )
    p_run.add_argument(
        "--model",
        choices=["pi3x", "mapanything"],
        default="pi3x",
        help="video / photo tiers: pi3x (more accurate, CC BY-NC weights) or mapanything "
        "(Apache 2.0)",
    )
    p_run.add_argument(
        "--damage",
        action="store_true",
        help="detect damage on any tier (Gemini, credentials from the environment; offline "
        "fallback: see src/floorplan/damage.py)",
    )
    p_run.add_argument("--damage-frames", type=int, help="keyframes sent to the damage detector")
    p_run.add_argument(
        "--crack-pass", action="store_true", help="damage: second Gemini call tracing cracks"
    )
    p_run.add_argument(
        "--recon",
        choices=["auto", "kaggle", "local"],
        help="video / photo tiers: where the model runs (default auto: Kaggle's GPUs, else "
        "this machine in low-memory mode; also FLOORPLAN_RECON_BACKEND)",
    )
    p_dmg = sub.add_parser(
        "damage", help="detect damage on photos (no sizes): detections.json + overlays"
    )
    p_dmg.add_argument("images", type=Path, nargs="+", help="image files or folders")
    p_dmg.add_argument("--out", type=Path, default=Path("outputs/damage_photos"))
    p_dmg.add_argument(
        "--crack-pass", action="store_true", help="second Gemini call tracing cracks"
    )
    sub.add_parser("check", help="is this machine ready for each tier? (run before the walk-in)")
    args = parser.parse_args(argv)
    if args.command == "check":
        from floorplan.check import run as check

        return check()
    if args.command == "damage":
        return _damage_photos(args.images, args.out, args.crack_pass)

    if args.recon:
        import os

        from floorplan.mvs import BACKEND_ENV

        os.environ[BACKEND_ENV] = args.recon
    try:
        args.capture = unpack(args.capture)
        tier = resolve_tier(detect_format(args.capture), args.tier)
        out_dir = args.out / f"{_capture_id(args.capture)}_{tier}"
        result = run(
            args.capture,
            args.tier,
            args.drift,
            args.frames,
            args.up,
            args.model,
            damage=args.damage,
            damage_frames=args.damage_frames,
            damage_dir=out_dir / "damage" if args.damage else None,
            crack_pass=args.crack_pass,
        )
    except ValueError as err:
        print(f"floorplan: {err}", file=sys.stderr)
        return 2

    path = write_json(result, out_dir / "plan.json")
    render_plan(result, out_dir / "plan.png")
    print(f"{result.capture.id} [{result.capture.tier}] -> {path} (+ plan.png)")
    for warning in result.warnings:
        print(f"  warning: {warning}")
    return 0


def _capture_id(path: Path) -> str:
    return path.stem if path.is_file() else path.name


def _damage_photos(paths: list[Path], out: Path, crack_pass: bool = False) -> int:
    """Detection only: one row per detection, and an overlay per image with detections."""
    import json

    from PIL import Image, ImageOps

    from floorplan.capture import PHOTO_SUFFIXES
    from floorplan.damage import detect, model_name
    from floorplan.damage_lidar import overlay

    files = []
    for p in paths:
        files += (
            sorted(f for f in p.rglob("*") if f.suffix.lower() in PHOTO_SUFFIXES)
            if (p.is_dir())
            else [p]
        )
    rows = []
    for f in files:
        image = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
        image_id = f"{f.parent.name}/{f.stem}"
        dets = detect(image_id, image, crack_pass=crack_pass)
        for d in dets:
            rows.append(
                {
                    "image": str(f),
                    "label": d.label,
                    "score": d.score,
                    "box_px": [round(v, 1) for v in d.box],
                    "mask_px": int(d.mask.sum()) if d.mask is not None else None,
                    "mask_source": d.mask_source,
                    "source": d.source,
                    "points_px": [[round(x, 1), round(y, 1)] for x, y in d.points]
                    if d.points
                    else None,
                    "note": d.note,
                }
            )
        if dets:
            dest = out / "overlays" / f"{f.parent.name}_{f.stem}.jpg"
            dest.parent.mkdir(parents=True, exist_ok=True)
            overlay(image, dets, dets).save(dest, quality=85)
        print(f"{image_id}: " + (", ".join(f"{d.label} {d.score:.2f}" for d in dets) or "-"))
    out.mkdir(parents=True, exist_ok=True)
    record = {
        "model": model_name(),
        "crack_pass": crack_pass,
        "images": [str(f) for f in files],
        "detections": rows,
    }
    (out / "detections.json").write_text(json.dumps(record, indent=1))
    print(f"{len(rows)} detections on {len(files)} images -> {out}/detections.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
