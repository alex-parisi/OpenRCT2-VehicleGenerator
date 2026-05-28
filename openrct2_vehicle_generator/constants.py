"""Constants ported from src/rct2-ride-gen/Constants.hpp and
src/iso-render/Renderer.hpp / Mesh.hpp.
"""

from enum import IntEnum, IntFlag, auto

TILE_SIZE = 3.3

RENDER_WIDTH = 255
RENDER_HEIGHT = 256
UNITS_PER_TILE = 4096
UNITS_PER_PIXEL = 128
FRAGMENT_UNUSED = 255
REGION_MASK = 0x7
MAX_REGIONS = 8


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
    "flat", "gentle_slopes", "steep_slopes", "vertical_slopes",
    "diagonals", "banked_turns", "inline_twists", "slope_bank_transition",
    "diagonal_bank_transition", "sloped_bank_transition", "banked_sloped_turns",
    "banked_slope_transition", "corkscrews", "zero_g_rolls",
    "diagonal_sloped_bank_transition", "dive_loops",
]

RIDE_FLAG_NAMES = ["no_collision_crashes", "rider_controls_speed"]

VEHICLE_FLAG_NAMES = [
    "secondary_remap", "tertiary_remap", "riders_scream", "restraint_animation",
]

RUNNING_SOUND_NAMES = [
    "wooden_old", "wooden", "steel", "steel_smooth", "train", "engine",
]

SECONDARY_SOUND_NAMES = ["scream1", "scream2", "scream3", "bell"]

COLOR_NAMES = [
    "black", "grey", "white", "dark_purple", "light_purple", "bright_purple",
    "dark_blue", "light_blue", "icy_blue", "teal", "aquamarine",
    "saturated_green", "dark_green", "moss_green", "bright_green",
    "olive_green", "dark_olive_green", "bright_yellow", "yellow",
    "dark_yellow", "light_orange", "dark_orange", "light_brown",
    "saturated_brown", "dark_brown", "salmon_pink", "bordeaux_red",
    "saturated_red", "bright_red", "dark_pink", "bright_pink", "light_pink",
]

CATEGORY_NAMES = ["transport", "gentle", "water", "rollercoaster"]

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


# Material flags (from src/iso-render/Mesh.hpp).
MATERIAL_HAS_TEXTURE = 1 << 0
MATERIAL_IS_REMAPPABLE = 1 << 1
MATERIAL_IS_MASK = 1 << 2
MATERIAL_NO_AO = 1 << 3
MATERIAL_BACKGROUND_AA = 1 << 4
MATERIAL_BACKGROUND_AA_DARK = 1 << 5
MATERIAL_IS_VISIBLE_MASK = 1 << 6
MATERIAL_NO_BLEED = 1 << 7
MATERIAL_IS_FLAT_SHADED = 1 << 8


# Mesh flags (RayTrace.hpp).
MESH_MASK = 1 << 0
MESH_GHOST = 1 << 1


# Light types (Renderer.hpp).
LIGHT_HEMI = 0
LIGHT_DIFFUSE = 1
LIGHT_SPECULAR = 2


# AA / AO sample counts (Renderer.cpp).
AA_NUM_SAMPLES_U = 4
AA_NUM_SAMPLES_V = 4
AO_NUM_SAMPLES_U = 8
AO_NUM_SAMPLES_V = 4
