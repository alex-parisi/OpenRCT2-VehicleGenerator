"""
Usage:
    openrct2-scenery-generator [--test|--skip-render] <input.json|.yaml>
    python -m openrct2_scenery_generator [--test|--skip-render] <input.json|.yaml>
"""

import argparse
import sys
from pathlib import Path

from openrct2_iso_core.config import LoadError, parse_config
from openrct2_iso_core.lights import default_lights, load_lights
from openrct2_iso_core.ray_trace import Context

from .exporter import (
    export_large_scenery,
    export_large_scenery_test,
    export_small_scenery,
    export_small_scenery_test,
    export_wall_scenery,
    export_wall_scenery_test,
)
from .loader import (
    load_large_scenery,
    load_small_scenery,
    load_wall_scenery,
    object_type_of,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openrct2-scenery-generator")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--test", action="store_true", help="single-viewpoint render to test/")
    group.add_argument(
        "--skip-render", action="store_true", help="reuse previously rendered sprites"
    )
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

    lights = default_lights()
    if "lights" in root:
        try:
            lights = load_lights(root["lights"])
        except LoadError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    try:
        obj_type = object_type_of(root)
    except LoadError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    def _context_for(units_per_tile: float) -> Context:
        # Load first so the object's configured render scale (units_per_tile)
        # drives the camera. Test mode renders 8x zoomed for fast eyeballing.
        upt = 0.125 * units_per_tile if args.test else units_per_tile
        return Context.make(lights=lights, dither=True, upt=upt)

    try:
        if obj_type == "scenery_large":
            large = load_large_scenery(args.input)
            context = _context_for(large.units_per_tile)
            if args.test:
                export_large_scenery_test(large, context)
            else:
                export_large_scenery(
                    large, context, output_directory, skip_render=args.skip_render
                )
        elif obj_type == "scenery_wall":
            wall = load_wall_scenery(args.input)
            context = _context_for(wall.units_per_tile)
            if args.test:
                export_wall_scenery_test(wall, context)
            else:
                export_wall_scenery(
                    wall, context, output_directory, skip_render=args.skip_render
                )
        else:
            small = load_small_scenery(args.input)
            context = _context_for(small.units_per_tile)
            if args.test:
                export_small_scenery_test(small, context)
            else:
                export_small_scenery(
                    small, context, output_directory, skip_render=args.skip_render
                )
    except LoadError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
