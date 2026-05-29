#!/usr/bin/env python3
"""
Generate makeride-compatible vehicle JSON for a given track type.

Reads the track_types.json produced by build_track_types.py.

Commands:
    python ride_gen.py list
    python ride_gen.py info <ride_type>
    python ride_gen.py generate <ride_type> --id <id> --name <name> [options]
"""

import argparse
import json
import sys
from pathlib import Path

_TRACK_TYPES_FILE = Path(__file__).parent / "track_types.json"

# Valid values accepted by makeride (from Constants.hpp)
VALID_RUNNING_SOUNDS = ["wooden_old", "wooden", "steel", "steel_smooth", "train", "engine"]
VALID_SECONDARY_SOUNDS = ["scream1", "scream2", "scream3", "bell"]
VALID_VEHICLE_FLAGS = ["secondary_remap", "tertiary_remap", "riders_scream", "restraint_animation"]


def load_track_types() -> dict:
    if not _TRACK_TYPES_FILE.exists():
        sys.exit(f"Error: {_TRACK_TYPES_FILE} not found. Run build_track_types.py first.")
    return json.loads(_TRACK_TYPES_FILE.read_text(encoding="utf-8"))


def resolve_ride_type(track_types: dict, ride_type: str) -> dict:
    info = track_types.get(ride_type)
    if not info:
        matches = [k for k in track_types if ride_type.lower() in k.lower()]
        hint = f"\nDid you mean: {', '.join(matches)}" if matches else \
               "\nRun 'ride_gen.py list' to see all available types."
        sys.exit(f"Unknown ride type: '{ride_type}'.{hint}")
    return info


def _mesh_for_car(meshes: list[str], car_index: int) -> str:
    """Return the mesh to use for a given car index.

    If the caller supplied one mesh per car, use the matching one.
    If fewer meshes than cars, reuse the last mesh for the remainder.
    """
    return meshes[min(car_index, len(meshes) - 1)]


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_list(track_types: dict, _args) -> None:
    for ride_type, info in track_types.items():
        n = len(info["cars"])
        car_label = f"{n} car type{'s' if n != 1 else ''}"
        print(f"  {ride_type:<42} {info['name']}  ({car_label})")


def cmd_info(track_types: dict, args) -> None:
    info = resolve_ride_type(track_types, args.ride_type)
    cfg = info["configuration"]

    print(f"ride_type:     {args.ride_type}")
    print(f"name:          {info['name']}")
    print(f"sprites:       {info['sprites']}")
    print(f"source object: {info['source']}")
    print()

    slot_names = {v: k for k, v in cfg.items()}  # index → slot name
    for i, car in enumerate(info["cars"]):
        slots = [slot_names[i]] if i in slot_names else []
        label = f"  car[{i}]"
        label += f"  [{', '.join(slots)}]" if slots else "  [unassigned]"
        print(label)
        print(f"    vehicle_flags: {car['vehicle_flags']}")

    print()
    print(f"configuration: {cfg}")


def cmd_generate(track_types: dict, args) -> None:
    info = resolve_ride_type(track_types, args.ride_type)
    cars = info["cars"]
    cfg = info["configuration"]

    if not args.meshes:
        sys.exit("Error: --meshes requires at least one file path.")

    vehicles = []
    for i, car in enumerate(cars):
        # Merge required flags from the track type with any user-supplied extras
        vflags = sorted(set(car["vehicle_flags"]) | set(args.extra_flags))
        vehicles.append({
            "flags": vflags,
            "model": [{"mesh_index": i, "position": [0, 0, 0], "orientation": [0, 0, 0]}],
            "mass": args.mass,
            "spacing": args.spacing,
            "draw_order": args.draw_order,
        })

    # meshes list: one entry per distinct mesh path (deduplicated by car index)
    meshes = [_mesh_for_car(args.meshes, i) for i in range(len(cars))]

    out = {
        "id": args.id,
        "ride_type": args.ride_type,
        "name": args.name,
        "description": args.description,
        "capacity": args.capacity,
        "authors": args.authors,
        "version": "1.0",
        "sprites": info["sprites"],
        "flags": [],
        "zero_cars": 0,
        "min_cars_per_train": args.min_cars,
        "max_cars_per_train": args.max_cars,
        "build_menu_priority": 5,
        "preview_tab_car": cfg.get("default", 0),
        "running_sound": args.running_sound,
        "secondary_sound": args.secondary_sound,
        "default_colors": [["bright_red", "bright_red", "yellow"]] * len(cars),
        "configuration": cfg,
        "meshes": meshes,
        "vehicles": vehicles,
    }

    text = json.dumps(out, indent=2)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate makeride vehicle JSON for an existing in-game track type."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    sub.add_parser("list", help="List all available ride types")

    # info
    p_info = sub.add_parser("info", help="Show car layout and sprite requirements for a ride type")
    p_info.add_argument("ride_type")

    # generate
    p_gen = sub.add_parser("generate", help="Generate a skeleton vehicle JSON")
    p_gen.add_argument("ride_type")
    p_gen.add_argument("--id",    required=True, help="Object ID (e.g. mymod.ride.mycoaster)")
    p_gen.add_argument("--name",  required=True, help="Display name")
    p_gen.add_argument("--description", default="", metavar="TEXT")
    p_gen.add_argument("--capacity",    default="", metavar="TEXT",
                       help="Capacity string shown in the ride info window")
    p_gen.add_argument("--authors",     nargs="*", default=[], metavar="NAME",
                       help="One or more author names")
    p_gen.add_argument("--meshes", nargs="+", default=["vehicle.obj"], metavar="FILE",
                       help=(
                           "Mesh file path(s) for each car type. Provide one path per car "
                           "type in the same order as 'info' lists them (default=car[0], "
                           "front=car[1], etc.). If fewer paths than car types are given, "
                           "the last path is reused for remaining cars."
                       ))
    p_gen.add_argument("--min-cars",   type=int,   default=1)
    p_gen.add_argument("--max-cars",   type=int,   default=1)
    p_gen.add_argument("--mass",       type=int,   default=500)
    p_gen.add_argument("--spacing",    type=float, default=1.9,
                       help="Car spacing in tile units (default: 1.9)")
    p_gen.add_argument("--draw-order", type=int,   default=6)
    p_gen.add_argument("--running-sound",   default="steel",
                       choices=VALID_RUNNING_SOUNDS)
    p_gen.add_argument("--secondary-sound", default="scream1",
                       choices=VALID_SECONDARY_SOUNDS)
    p_gen.add_argument("--extra-flags", nargs="+", default=[],
                       choices=VALID_VEHICLE_FLAGS, metavar="FLAG",
                       help="Additional vehicle flags to add to every car type")
    p_gen.add_argument("--output", "-o", metavar="FILE",
                       help="Write JSON to this file instead of stdout")

    args = parser.parse_args()
    track_types = load_track_types()

    {"list": cmd_list, "info": cmd_info, "generate": cmd_generate}[args.command](
        track_types, args
    )


if __name__ == "__main__":
    main()
