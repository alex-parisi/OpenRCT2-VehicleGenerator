#!/usr/bin/env python3
"""
One-time extraction of track type → vehicle sprite requirements from objects-master.

Run this whenever objects-master is updated:
    python build_track_types.py ~/Downloads/objects-master track_types.json
"""

import json
import sys
from pathlib import Path

# spriteGroups key (new format) → RCTGen sprites flag name
_SPRITE_GROUPS_MAP = {
    "slopeFlat":            "flat",
    "slopes12":             "gentle_slopes",
    "slopes25":             "gentle_slopes",
    "slopes42":             "steep_slopes",
    "slopes60":             "steep_slopes",
    "slopes75":             "vertical_slopes",
    "slopes90":             "vertical_slopes",
    "slopesLoop":           "vertical_slopes",
    "slopeInverted":        "vertical_slopes",
    "slopes8":              "diagonals",
    "slopes16":             "diagonals",
    "slopes50":             "diagonals",
    "flatBanked22":         "banked_turns",
    "flatBanked45":         "banked_turns",
    "flatBanked67":         "inline_twists",
    "flatBanked90":         "inline_twists",
    "inlineTwists":         "inline_twists",
    "slopes12Banked22":     "slope_bank_transition",
    "slopes8Banked22":      "diagonal_bank_transition",
    "slopes25Banked22":     "sloped_bank_transition",
    "slopes8Banked45":      "diagonal_sloped_bank_transition",
    "slopes16Banked22":     "diagonal_sloped_bank_transition",
    "slopes16Banked45":     "diagonal_sloped_bank_transition",
    "slopes25Banked45":     "banked_sloped_turns",
    "slopes12Banked45":     "banked_slope_transition",
    "slopes25Banked67":     "zero_g_rolls",
    "slopes25Banked90":     "zero_g_rolls",
    "slopes25InlineTwists": "zero_g_rolls",
    "slopes42Banked22":     "zero_g_rolls",
    "slopes42Banked45":     "zero_g_rolls",
    "slopes42Banked67":     "zero_g_rolls",
    "slopes42Banked90":     "zero_g_rolls",
    "slopes60Banked22":     "zero_g_rolls",
    "slopes50Banked45":     "dive_loops",
    "slopes50Banked67":     "dive_loops",
    "slopes50Banked90":     "dive_loops",
    "corkscrews":           "corkscrews",
    # restraintAnimation → vehicle flag, handled separately
}

# frames key (old RCT2 boolean format) → RCTGen sprites flag name
_FRAMES_MAP = {
    "flat":                                     "flat",
    "gentleSlopes":                             "gentle_slopes",
    "steepSlopes":                              "steep_slopes",
    "verticalSlopes":                           "vertical_slopes",
    "diagonalSlopes":                           "diagonals",
    "flatBanked":                               "banked_turns",
    "inlineTwists":                             "inline_twists",
    "flatToGentleSlopeBankedTransitions":       "slope_bank_transition",
    "diagonalGentleSlopeBankedTransitions":     "diagonal_bank_transition",
    "gentleSlopeBankedTransitions":             "sloped_bank_transition",
    "gentleSlopeBankedTurns":                   "banked_sloped_turns",
    "flatToGentleSlopeWhileBankedTransitions":  "banked_slope_transition",
    "corkscrews":                               "corkscrews",
    "zeroGRolls":                               "zero_g_rolls",
    "diveLoops":                                "dive_loops",
    # restraintAnimation → vehicle flag, handled separately
}

# Canonical output order matching kSpriteGroupNames in Constants.hpp
_FLAG_ORDER = [
    "flat", "gentle_slopes", "steep_slopes", "vertical_slopes",
    "diagonals", "banked_turns", "inline_twists", "slope_bank_transition",
    "diagonal_bank_transition", "sloped_bank_transition", "banked_sloped_turns",
    "banked_slope_transition", "corkscrews", "zero_g_rolls",
    "diagonal_sloped_bank_transition", "dive_loops",
]


def _extract_car(car: dict) -> tuple[list[str], list[str]]:
    """Return (sprites, vehicle_flags) for a single car definition."""
    flags: set[str] = set()
    vehicle_flags: list[str] = []

    if "spriteGroups" in car:
        for key in car["spriteGroups"]:
            if key == "restraintAnimation":
                vehicle_flags.append("restraint_animation")
            elif key in _SPRITE_GROUPS_MAP:
                flags.add(_SPRITE_GROUPS_MAP[key])
    elif "frames" in car:
        for key, val in car["frames"].items():
            if not val:
                continue
            if key == "restraintAnimation":
                vehicle_flags.append("restraint_animation")
            elif key in _FRAMES_MAP:
                flags.add(_FRAMES_MAP[key])

    sprites = [f for f in _FLAG_ORDER if f in flags]
    return sprites, vehicle_flags


def _extract_all_cars(cars: list[dict]) -> tuple[list[str], list[dict]]:
    """Return (project_sprites, per_car_info) across all car definitions.

    project_sprites is the union of every car's sprite flags — all cars ride
    the same track so they're almost always identical, but taking the union is
    the safe default.
    """
    all_flags: set[str] = set()
    car_infos: list[dict] = []

    for car in cars:
        sprites, vflags = _extract_car(car)
        all_flags.update(sprites)
        car_infos.append({"vehicle_flags": sorted(set(vflags))})

    project_sprites = [f for f in _FLAG_ORDER if f in all_flags]
    return project_sprites, car_infos


def _extract_configuration(props: dict) -> dict:
    """Map objects-master headCars/tailCars/defaultCar → RCTGen configuration format.

    RCTGen slots: default, front, second, third, rear.
    objects-master headCars can be an int or a list (e.g. miniature_railway has
    two different locomotive options [0, 1] mapping to front and second).
    """
    config: dict = {"default": props.get("defaultCar", 0)}

    head = props.get("headCars")
    if head is not None:
        if isinstance(head, list):
            slots = ["front", "second", "third"]
            for slot, idx in zip(slots, head, strict=False):
                config[slot] = idx
        else:
            config["front"] = head

    tail = props.get("tailCars")
    if tail is not None:
        config["rear"] = tail

    return config


def _ride_type(properties: dict) -> str | None:
    t = properties.get("type")
    if isinstance(t, list):
        return t[0] if t else None
    return t


def _display_name(obj: dict) -> str:
    name = obj.get("strings", {}).get("name", {})
    if isinstance(name, dict):
        return name.get("en-GB") or name.get("en-US") or ""
    return str(name) if name else ""


def build(objects_root: Path) -> dict:
    track_types: dict = {}

    for path in sorted(objects_root.rglob("*.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        if obj.get("objectType") != "ride":
            continue

        props = obj.get("properties", {})
        ride_type = _ride_type(props)
        if not ride_type:
            continue

        # Flat rides (merry-go-round, 3D cinema, etc.) declare carsPerFlatRide.
        # Their vehicles are baked into the ride type and cannot be replaced by
        # a custom vehicle object. minCarsPerTrain is optional in objects-master
        # (many legitimate coasters omit it), so we only filter on carsPerFlatRide.
        if "carsPerFlatRide" in props:
            continue

        cars_raw = props.get("cars", [])
        if not cars_raw:
            continue
        # cars can be a single object or an array of objects
        cars = cars_raw if isinstance(cars_raw, list) else [cars_raw]

        project_sprites, car_infos = _extract_all_cars(cars)
        if not project_sprites:
            continue  # nothing renderable

        # Keep whichever entry has the most sprites (richer object wins)
        existing = track_types.get(ride_type)
        if existing and len(project_sprites) <= len(existing["sprites"]):
            continue

        track_types[ride_type] = {
            "name": _display_name(obj),
            "sprites": project_sprites,
            "cars": car_infos,
            "configuration": _extract_configuration(props),
            "source": path.stem,
        }

    return dict(sorted(track_types.items()))


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: build_track_types.py <objects-master-dir> <output.json>")
        sys.exit(1)

    root = Path(sys.argv[1])
    output = Path(sys.argv[2])

    if not root.is_dir():
        print(f"Error: {root} is not a directory")
        sys.exit(1)

    print(f"Scanning {root} ...")
    track_types = build(root)
    output.write_text(json.dumps(track_types, indent=2), encoding="utf-8")
    print(f"Wrote {len(track_types)} track types → {output}")


if __name__ == "__main__":
    main()
