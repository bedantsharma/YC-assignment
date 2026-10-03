"""Command line: `floorplan run <capture> [--tier lidar|video|photo] [--out outputs]`."""

import argparse
import sys
from pathlib import Path

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
    args = parser.parse_args(argv)

    try:
        result = run(args.capture, args.tier)
    except ValueError as err:
        print(f"floorplan: {err}", file=sys.stderr)
        return 2

    out_dir = args.out / f"{result.capture.id}_{result.capture.tier}"
    path = write_json(result, out_dir / "plan.json")
    render_plan(result, out_dir / "plan.png")
    print(f"{result.capture.id} [{result.capture.tier}] -> {path} (+ plan.png)")
    for warning in result.warnings:
        print(f"  warning: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
