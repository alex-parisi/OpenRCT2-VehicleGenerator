"""
Vehicle-specific constants. Shared rendering primitives (TILE_SIZE and the
MaterialFlag enum) live in openrct2_x7_renderer.constants and are re-exported
here for convenience.

Ported from X7's rendering engine
https://github.com/X123M3-256/RCTGen
"""

from enum import IntEnum, IntFlag, auto

from openrct2_x7_renderer.constants import (
    TILE_SIZE,
    MaterialFlag,
)

# Max animation frames per mesh placement (the restraint-animation frame count).
# Lived in openrct2_x7_renderer.types as MAX_FRAMES before the v0.2 renderer
# rework dropped it; kept here as the vehicle front-end is its only consumer.
MAX_FRAMES = 4

__all__ = [
    # Re-exported shared rendering primitives.
    "TILE_SIZE",
    "MaterialFlag",
    "MAX_FRAMES",
    # Vehicle-specific.
    "SpriteFlag",
    "RideFlag",
    "VehicleFlag",
    "frames_for",
    "RunningSound",
    "SecondarySound",
    "CarIndex",
    "CONFIGURATION_SLOTS",
    "CAR_SLOT_ABSENT",
    "Category",
    "SPRITE_GROUP_NAMES",
    "RIDE_FLAG_NAMES",
    "VEHICLE_FLAG_NAMES",
    "RUNNING_SOUND_NAMES",
    "SECONDARY_SOUND_NAMES",
    "COLOR_NAMES",
    "CATEGORY_NAMES",
    "FRICTION_SOUND_IDS",
]


class SpriteFlag(IntFlag):
    FLAT_SLOPE = auto()
    GENTLE_SLOPE = auto()
    STEEP_SLOPE = auto()
    VERTICAL_SLOPE = auto()
    DIAGONAL_SLOPE = auto()
    BANKING = auto()
    INLINE_TWIST = auto()
    SLOPE_BANK_TRANSITION = auto()
    DIAGONAL_BANK_TRANSITION = auto()
    SLOPED_BANK_TRANSITION = auto()
    SLOPED_BANKED_TURN = auto()
    BANKED_SLOPE_TRANSITION = auto()
    CORKSCREW = auto()
    ZERO_G_ROLL = auto()
    DIAGONAL_SLOPED_BANK_TRANSITION = auto()
    DIVE_LOOP = auto()


class RideFlag(IntFlag):
    NO_COLLISION_CRASHES = auto()
    RIDER_CONTROLS_SPEED = auto()


class VehicleFlag(IntFlag):
    SECONDARY_REMAP = auto()
    TERTIARY_REMAP = auto()
    RIDERS_SCREAM = auto()
    RESTRAINT_ANIMATION = auto()


def frames_for(vehicle_flags: int) -> int:
    """Animation frames a vehicle renders: MAX_FRAMES when the restraint
    animation flag is set, else 1. Single source for the loader and exporter so
    the allocated, rendered, and declared frame counts can't drift."""
    return MAX_FRAMES if (vehicle_flags & VehicleFlag.RESTRAINT_ANIMATION) else 1


class RunningSound(IntEnum):
    WOODEN_OLD = 1
    WOODEN_MODERN = 54
    STEEL = 2
    STEEL_SMOOTH = 57
    WATERSLIDE = 32
    TRAIN = 31
    ENGINE = 21
    NONE = 255


class SecondarySound(IntEnum):
    SCREAMS1 = 0
    SCREAMS2 = 1
    SCREAMS3 = 2
    WHISTLE = 3
    BELL = 4
    NONE = 255


class CarIndex(IntEnum):
    DEFAULT = 0
    FRONT = 1
    SECOND = 2
    REAR = 3
    THIRD = 4


# The `configuration` list always has one slot per CarIndex member, and an unset
# slot is marked absent with this sentinel (the engine's "no car" value).
CONFIGURATION_SLOTS = len(CarIndex)
CAR_SLOT_ABSENT = 0xFF


class Category(IntEnum):
    TRANSPORT_RIDE = 0
    GENTLE_RIDE = 1
    ROLLERCOASTER = 2
    THRILL_RIDE = 3
    WATER_RIDE = 4
    SHOP = 5


# Config-name <-> enum mappings. Each name is bound to a specific enum member,
# and the public `*_NAMES` lists are *derived* by iterating the enum, so the
# loader's `names.index(tag)` always yields the matching bit/value. Reordering or
# extending an enum reorders its names automatically; a member with no name entry
# fails loudly at import (KeyError) instead of silently misaligning. Names mirror
# Constants.hpp.

# A flag's bit position is its index in the derived list (the loader does
# `1 << names.index(tag)`), so the names follow the enum's bit order.
_SPRITE_GROUP_NAME: dict[SpriteFlag, str] = {
    SpriteFlag.FLAT_SLOPE: "flat",
    SpriteFlag.GENTLE_SLOPE: "gentle_slopes",
    SpriteFlag.STEEP_SLOPE: "steep_slopes",
    SpriteFlag.VERTICAL_SLOPE: "vertical_slopes",
    SpriteFlag.DIAGONAL_SLOPE: "diagonals",
    SpriteFlag.BANKING: "banked_turns",
    SpriteFlag.INLINE_TWIST: "inline_twists",
    SpriteFlag.SLOPE_BANK_TRANSITION: "slope_bank_transition",
    SpriteFlag.DIAGONAL_BANK_TRANSITION: "diagonal_bank_transition",
    SpriteFlag.SLOPED_BANK_TRANSITION: "sloped_bank_transition",
    SpriteFlag.SLOPED_BANKED_TURN: "banked_sloped_turns",
    SpriteFlag.BANKED_SLOPE_TRANSITION: "banked_slope_transition",
    SpriteFlag.CORKSCREW: "corkscrews",
    SpriteFlag.ZERO_G_ROLL: "zero_g_rolls",
    SpriteFlag.DIAGONAL_SLOPED_BANK_TRANSITION: "diagonal_sloped_bank_transition",
    SpriteFlag.DIVE_LOOP: "dive_loops",
}
SPRITE_GROUP_NAMES = [_SPRITE_GROUP_NAME[f] for f in SpriteFlag]

_RIDE_FLAG_NAME: dict[RideFlag, str] = {
    RideFlag.NO_COLLISION_CRASHES: "no_collision_crashes",
    RideFlag.RIDER_CONTROLS_SPEED: "rider_controls_speed",
}
RIDE_FLAG_NAMES = [_RIDE_FLAG_NAME[f] for f in RideFlag]

_VEHICLE_FLAG_NAME: dict[VehicleFlag, str] = {
    VehicleFlag.SECONDARY_REMAP: "secondary_remap",
    VehicleFlag.TERTIARY_REMAP: "tertiary_remap",
    VehicleFlag.RIDERS_SCREAM: "riders_scream",
    VehicleFlag.RESTRAINT_ANIMATION: "restraint_animation",
}
VEHICLE_FLAG_NAMES = [_VEHICLE_FLAG_NAME[f] for f in VehicleFlag]

# One ordered table pairs each running-sound config name with its engine sound
# id. The loader maps a config name to its index in RUNNING_SOUND_NAMES; the
# exporter looks that same index up in FRICTION_SOUND_IDS. Deriving both from one
# table keeps them aligned. (kRunningSoundValues order, incl. waterslide; the
# engine value is appended by ProjectExporter.cpp.)
_RUNNING_SOUNDS: list[tuple[str, RunningSound]] = [
    ("wooden_old", RunningSound.WOODEN_OLD),
    ("wooden", RunningSound.WOODEN_MODERN),
    ("steel", RunningSound.STEEL),
    ("steel_smooth", RunningSound.STEEL_SMOOTH),
    ("waterslide", RunningSound.WATERSLIDE),
    ("train", RunningSound.TRAIN),
    ("engine", RunningSound.ENGINE),
]
RUNNING_SOUND_NAMES = [name for name, _ in _RUNNING_SOUNDS]
FRICTION_SOUND_IDS = [sound.value for _, sound in _RUNNING_SOUNDS]

# A name's index here is written directly as object.json `soundRange`, so each
# name must sit at its SecondarySound value; ordering by value guarantees it.
# (NONE is intentionally excluded -- it isn't selectable from config.)
_SECONDARY_SOUND_NAME: dict[SecondarySound, str] = {
    SecondarySound.SCREAMS1: "scream1",
    SecondarySound.SCREAMS2: "scream2",
    SecondarySound.SCREAMS3: "scream3",
    SecondarySound.WHISTLE: "whistle",
    SecondarySound.BELL: "bell",
}
SECONDARY_SOUND_NAMES = [
    _SECONDARY_SOUND_NAME[s] for s in sorted(_SECONDARY_SOUND_NAME, key=lambda m: m.value)
]

COLOR_NAMES = [
    "black",
    "grey",
    "white",
    "dark_purple",
    "light_purple",
    "bright_purple",
    "dark_blue",
    "light_blue",
    "icy_blue",
    "teal",
    "aquamarine",
    "saturated_green",
    "dark_green",
    "moss_green",
    "bright_green",
    "olive_green",
    "dark_olive_green",
    "bright_yellow",
    "yellow",
    "dark_yellow",
    "light_orange",
    "dark_orange",
    "light_brown",
    "saturated_brown",
    "dark_brown",
    "salmon_pink",
    "bordeaux_red",
    "saturated_red",
    "bright_red",
    "dark_pink",
    "bright_pink",
    "light_pink",
]

# Indexed by Category value: CATEGORY_NAMES[Category.X] is X's object.json
# category string. Derived in value order from the enum so it can't drift.
_CATEGORY_NAME: dict[Category, str] = {
    Category.TRANSPORT_RIDE: "transport",
    Category.GENTLE_RIDE: "gentle",
    Category.ROLLERCOASTER: "rollercoaster",
    Category.THRILL_RIDE: "thrill",
    Category.WATER_RIDE: "water",
    Category.SHOP: "shop",
}
CATEGORY_NAMES = [_CATEGORY_NAME[c] for c in sorted(_CATEGORY_NAME, key=lambda m: m.value)]
