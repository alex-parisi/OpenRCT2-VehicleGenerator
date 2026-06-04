"""
Usage:
    openrct2-vehicle-generator [--test|--skip-render] <input.json|.yaml>
    python -m openrct2_vehicle_generator [--test|--skip-render] <input.json|.yaml>
"""

import argparse
import sys

from openrct2_x7_renderer.cli import make_context, output_directory_of, run_cli
from openrct2_x7_renderer.types import Light

from .exporter import export_ride, export_ride_test
from .loader import load_ride


def _render(args: argparse.Namespace, root: dict, lights: list[Light]) -> None:
    ride = load_ride(args.input)
    context = make_context(lights, ride.units_per_tile, args.test)
    if args.test:
        export_ride_test(ride, context)
    else:
        export_ride(ride, context, output_directory_of(root), skip_render=args.skip_render)


def main(argv: list[str] | None = None) -> int:
    return run_cli("openrct2-vehicle-generator", argv, _render)


if __name__ == "__main__":
    sys.exit(main())
