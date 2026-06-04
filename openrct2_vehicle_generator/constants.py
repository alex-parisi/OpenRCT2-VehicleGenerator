"""
Vehicle-specific constants. Shared rendering primitives (TILE_SIZE and the
LightType/MaterialFlag/MeshFlag enums) live in openrct2_x7_renderer.constants
and are re-exported here for convenience.

Ported from X7's rendering engine
https://github.com/X123M3-256/RCTGen
"""

from enum import IntEnum, IntFlag, auto

from openrct2_x7_renderer.constants import (
    TILE_SIZE,
    LightType,
    MaterialFlag,
    MeshFlag,
)

# Max animation frames per mesh placement (the restraint-animation frame count).
# Lived in openrct2_x7_renderer.types as MAX_FRAMES before the v0.2 renderer
# rework dropped it; kept here as the vehicle front-end is its only consumer.
MAX_FRAMES = 4

__all__ = [
    # Re-exported shared rendering primitives.
    "TILE_SIZE",
    "LightType",
    "MaterialFlag",
    "MeshFlag",
    "MAX_FRAMES",
    # Vehicle-specific.
    "SpriteFlag",
    "RideFlag",
    "VehicleFlag",
    "CarEntryAnimation",
    "RunningSound",
    "SecondarySound",
    "CarIndex",
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


class CarEntryAnimation(IntEnum):
    # Values mirror OpenRCT2's CarEntryAnimation enum (CarEntry.h).
    NONE = 0
    SIMPLE_VEHICLE = 1
    STEAM_LOCOMOTIVE = 2
    SWAN_BOAT = 3
    MONORAIL_CYCLE = 4
    MULTI_DIMENSION = 5
    OBSERVATION_TOWER = 6
    ANIMAL_FLYING = 7


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


class Category(IntEnum):
    TRANSPORT_RIDE = 0
    GENTLE_RIDE = 1
    ROLLERCOASTER = 2
    THRILL_RIDE = 3
    WATER_RIDE = 4
    SHOP = 5


# Mirror order/values in Constants.hpp.

SPRITE_GROUP_NAMES = [
    "flat",
    "gentle_slopes",
    "steep_slopes",
    "vertical_slopes",
    "diagonals",
    "banked_turns",
    "inline_twists",
    "slope_bank_transition",
    "diagonal_bank_transition",
    "sloped_bank_transition",
    "banked_sloped_turns",
    "banked_slope_transition",
    "corkscrews",
    "zero_g_rolls",
    "diagonal_sloped_bank_transition",
    "dive_loops",
]

RIDE_FLAG_NAMES = ["no_collision_crashes", "rider_controls_speed"]

VEHICLE_FLAG_NAMES = [
    "secondary_remap",
    "tertiary_remap",
    "riders_scream",
    "restraint_animation",
]

# Must stay index-aligned with FRICTION_SOUND_IDS below: the loader maps a
# config name to its index here and the exporter looks that index up in
# FRICTION_SOUND_IDS. (kRunningSoundValues order, incl. waterslide.)
RUNNING_SOUND_NAMES = [
    "wooden_old",
    "wooden",
    "steel",
    "steel_smooth",
    "waterslide",
    "train",
    "engine",
]

# Index-aligned with the SecondarySound enum values (the index is written
# directly as object.json `soundRange`), so "whistle" (3) must precede "bell" (4).
SECONDARY_SOUND_NAMES = ["scream1", "scream2", "scream3", "whistle", "bell"]

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

# Indexed by the Category enum value (NOT a free-standing order). Must stay
# aligned with the Category IntEnum above so CATEGORY_NAMES[Category.X] is the
# OpenRCT2 object.json category string for X.
CATEGORY_NAMES = ["transport", "gentle", "rollercoaster", "thrill", "water", "shop"]

# friction_sound_id table, indexed by running_sound enum index (Constants.hpp
# kRunningSoundValues + the engine value appended by ProjectExporter.cpp).
FRICTION_SOUND_IDS = [
    RunningSound.WOODEN_OLD.value,
    RunningSound.WOODEN_MODERN.value,
    RunningSound.STEEL.value,
    RunningSound.STEEL_SMOOTH.value,
    RunningSound.WATERSLIDE.value,
    RunningSound.TRAIN.value,
    RunningSound.ENGINE.value,
]
