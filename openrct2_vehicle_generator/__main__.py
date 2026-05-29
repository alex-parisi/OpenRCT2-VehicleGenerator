"""
Usage:
    openrct2-vehicle-generator [--test|--skip-render] <input.json|.yaml>
    python -m openrct2_vehicle_generator [--test|--skip-render] <input.json|.yaml>
"""


import argparse
import sys
from pathlib import Path

import numpy as np

from .constants import LIGHT_DIFFUSE, LIGHT_SPECULAR, TILE_SIZE
from .exporter import export_ride, export_ride_test
from .loader import LoadError, load_lights, load_ride, parse_config
from .ray_trace import Context
from .types import Light


def _normalize(v: list[float]) -> np.ndarray:
    arr = np.array(v, dtype=np.float64)
    n = np.linalg.norm(arr)
    if n > 0:
        arr = arr / n
    return arr


def _default_lights() -> list[Light]:
    # Mirrors the hand-tuned rig in src/rct2-ride-gen/main.cpp.
    return [
        Light(LIGHT_DIFFUSE, 0, _normalize([0.0, -1.0, 0.0]), 0.1),
        Light(LIGHT_DIFFUSE, 0, _normalize([0.0, 0.5, -1.0]), 0.8),
        Light(LIGHT_SPECULAR, 1, _normalize([1.0, 1.65, -1.0]), 0.5),
        Light(LIGHT_DIFFUSE, 1, _normalize([1.0, 1.7, -1.0]), 0.8),
        Light(LIGHT_DIFFUSE, 0, np.array([0.0, 1.0, 0.0], dtype=np.float64), 0.45),
        Light(LIGHT_DIFFUSE, 0, _normalize([-1.0, 0.85, 1.0]), 0.475),
        Light(LIGHT_DIFFUSE, 0, _normalize([0.75, 0.4, -1.0]), 0.6),
        Light(LIGHT_DIFFUSE, 0, _normalize([1.0, 0.25, 0.0]), 0.5),
        Light(LIGHT_DIFFUSE, 0, _normalize([-1.0, -0.5, 0.0]), 0.1),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openrct2-vehicle-generator")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--test", action="store_true",
                       help="single-viewpoint render to test/")
    group.add_argument("--skip-render", action="store_true",
                       help="reuse previously rendered sprites")
    parser.add_argument("input", type=Path)
    args = parser.parse_args(argv)

    try:
        root = parse_config(args.input)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    output_directory = Path(".")
    if isinstance(root.get("output_directory"), str):
        output_directory = Path(root["output_directory"])

    lights = _default_lights()
    if "lights" in root:
        try:
            lights = load_lights(root["lights"])
        except LoadError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    try:
        ride = load_ride(args.input)
    except LoadError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    upt = 0.125 * TILE_SIZE if args.test else TILE_SIZE
    context = Context.make(lights=lights, dither=True, upt=upt)

    try:
        if args.test:
            export_ride_test(ride, context)
        else:
            export_ride(ride, context, output_directory,
                        skip_render=args.skip_render)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
