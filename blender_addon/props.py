"""Blender PropertyGroups: the scene/object/material data the add-on reads.

These mirror the config the core `build_ride` consumes (see scene_to_ride.py),
but expressed as native Blender properties so the whole vehicle is authored in
the UI — no YAML. Enum item lists are sourced from the installed
`openrct2_vehicle_generator` package so they can never drift from what the
loader validates against.

NOTE: do not add ``from __future__ import annotations`` here — PEP 563 turns
the ``prop: SomeProperty(...)`` definitions into strings, which breaks Blender's
property registration.
"""

import json
import os

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Material, Object, PropertyGroup, Scene
from openrct2_vehicle_generator.constants import (
    COLOR_NAMES,
    RIDE_FLAG_NAMES,
    RUNNING_SOUND_NAMES,
    SECONDARY_SOUND_NAMES,
    SPRITE_GROUP_NAMES,
    VEHICLE_FLAG_NAMES,
)

_ADDON_DIR = os.path.dirname(__file__)


def _title(name: str) -> str:
    return name.replace("_", " ").title()


def _simple_items(names):
    """(identifier, label, description) tuples for a single-select enum."""
    return [(n, _title(n), "") for n in names]


# Each multi-select flag group is exposed as one BoolProperty per flag (prefixed
# by group), not a single ENUM_FLAG: Blender draws flag-enum buttons with
# exclusive, radio-like plain-click selection, whereas independent checkboxes are
# the behaviour we want. Sourced from the constant lists so they can't drift.
FLAG_GROUPS = {
    "sg_": SPRITE_GROUP_NAMES,
    "rf_": RIDE_FLAG_NAMES,
    "vf_": [n for n in VEHICLE_FLAG_NAMES if n != "restraint_animation"],
}


def flag_items(prefix: str):
    """(property_attr, flag_name) pairs for a group, e.g. ("rf_x", "x")."""
    return [(prefix + n, n) for n in FLAG_GROUPS[prefix]]


def _ride_type_items(_self, _context):
    """Ride-type identifiers, read from the add-on's bundled track_types.json.

    Cached on the function object so Blender's repeated enum callbacks don't
    re-read the file (and so the returned tuples aren't garbage-collected —
    a known EnumProperty-callback pitfall).
    """
    cached = getattr(_ride_type_items, "_cache", None)
    if cached is None:
        path = os.path.join(_ADDON_DIR, "track_types.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            names = sorted(data.keys()) if isinstance(data, dict) else []
        except (OSError, ValueError):
            names = ["classic_wooden_rc"]
        cached = _simple_items(names) or [("classic_wooden_rc", "Classic Wooden RC", "")]
        _ride_type_items._cache = cached
    return cached


# Material region identifiers map onto mesh.Material.region / flag bits in
# scene_to_ride.py. "NONE" leaves the material as a plain shaded colour.
MATERIAL_REGION_ITEMS = [
    ("NONE", "None", "Plain shaded colour"),
    ("REMAP1", "Remap 1 (main colour)", "Recoloured by the ride's main colour"),
    ("REMAP2", "Remap 2 (secondary)", "Recoloured by the secondary colour"),
    ("REMAP3", "Remap 3 (tertiary)", "Recoloured by the tertiary colour"),
    ("GREYSCALE", "Greyscale", "Greyscale shading region"),
    ("PEEP", "Peep", "Rider/peep region"),
    ("CHAIN", "Chain", "Lift-chain region"),
]

OBJECT_ROLE_ITEMS = [
    ("IGNORE", "Ignore", "Not part of the vehicle"),
    ("BODY", "Body", "Static part of the car"),
    ("RESTRAINT", "Restraint", "Lap bar / restraint that animates"),
    ("RIDER", "Rider seat", "A peep mesh; grouped into rows by Rider Row"),
]


class VGColorPreset(PropertyGroup):
    main: EnumProperty(name="Main", items=_simple_items(COLOR_NAMES), default="bright_red")
    secondary: EnumProperty(name="Secondary", items=_simple_items(COLOR_NAMES), default="black")
    tertiary: EnumProperty(name="Tertiary", items=_simple_items(COLOR_NAMES), default="grey")


class VGMaterialSettings(PropertyGroup):
    region: EnumProperty(
        name="Region",
        description="How OpenRCT2 treats this material's pixels",
        items=MATERIAL_REGION_ITEMS,
        default="NONE",
    )
    is_mask: BoolProperty(name="Mask", default=False)
    is_visible_mask: BoolProperty(name="Visible Mask", default=False)
    no_ao: BoolProperty(name="No Ambient Occlusion", default=False)
    edge: BoolProperty(name="Edge AA", default=False)
    dark_edge: BoolProperty(name="Dark Edge AA", default=False)
    no_bleed: BoolProperty(name="No Bleed", default=False)
    flat_shaded: BoolProperty(name="Flat Shaded", default=False)
    specular_exponent: FloatProperty(name="Specular Exponent", default=50.0, min=1.0)
    texture: PointerProperty(
        name="Texture",
        description="Optional image; must be saved to disk (its file is read at export)",
        type=bpy.types.Image,
    )


class VGObjectSettings(PropertyGroup):
    role: EnumProperty(
        name="Role",
        description="This object's part in the vehicle",
        items=OBJECT_ROLE_ITEMS,
        default="IGNORE",
    )
    rider_row: IntProperty(
        name="Rider Row",
        description="Seat row index (riders are grouped into rows, not individuals)",
        default=0,
        min=0,
    )
    empty_seat: BoolProperty(
        name="Empty Seat (engine overlays peep)",
        description=(
            "Don't bake this rider's mesh into the sprite. The engine will draw "
            "the actual guest peep on top, preserving per-guest clothing colors."
        ),
        default=False,
    )
    restraint_swing_deg: FloatProperty(
        name="Restraint Swing",
        description=(
            "Total degrees the restraint swings across its 4 animation frames. "
            "Set the object's ORIGIN to the hinge so it pivots correctly."
        ),
        default=90.0,
    )


class VGRideSettings(PropertyGroup):
    # --- Identity -----------------------------------------------------------
    id: StringProperty(
        name="Object ID",
        description="Unique id, e.g. openrct2vg.ride.my_coaster (avoid vanilla ids)",
        default="openrct2vg.ride.my_vehicle",
    )
    name: StringProperty(name="Name", default="My Vehicle")
    description: StringProperty(name="Description", default="")
    capacity: StringProperty(name="Capacity", default="2 people per car")
    authors: StringProperty(name="Authors", description="Comma-separated", default="")
    version: StringProperty(name="Version", default="1.0")

    # --- Ride ---------------------------------------------------------------
    ride_type: EnumProperty(name="Ride Type", items=_ride_type_items)
    sprites_all: BoolProperty(
        name="All Sprite Groups",
        description="Render every sprite group (safe default; larger output)",
        default=True,
    )
    # Per-flag sprite-group / ride-flag bools are injected after the class (see
    # FLAG_GROUPS).
    running_sound: EnumProperty(name="Running Sound", items=_simple_items(RUNNING_SOUND_NAMES))
    secondary_sound: EnumProperty(
        name="Secondary Sound", items=_simple_items(SECONDARY_SOUND_NAMES)
    )
    min_cars: IntProperty(name="Min Cars / Train", default=1, min=1)
    max_cars: IntProperty(name="Max Cars / Train", default=8, min=1)
    build_menu_priority: IntProperty(name="Build Menu Priority", default=0, min=0)

    # --- Default colours (up to 3 build-menu presets) -----------------------
    color_presets: CollectionProperty(type=VGColorPreset)
    color_preset_index: IntProperty(default=0)

    # --- Single vehicle params ---------------------------------------------
    # Per-flag vehicle-flag bools are injected after the class (see FLAG_GROUPS).
    # restraint_animation is excluded -- it's added automatically when a
    # Restraint object exists.
    mass: IntProperty(name="Mass", default=100, min=0)
    spacing: FloatProperty(name="Spacing", default=2.0, min=0.0)
    draw_order: IntProperty(name="Draw Order", default=1, min=0)
    effect_visual: IntProperty(name="Effect Visual", default=1, min=0)

    preview: PointerProperty(name="Preview Image", type=bpy.types.Image)


# Inject one BoolProperty per flag into VGRideSettings before registration, so
# register_class picks them up from __annotations__. "flat" is on by default to
# preserve the old sprite-group default.
for _prefix, _names in FLAG_GROUPS.items():
    for _name in _names:
        VGRideSettings.__annotations__[_prefix + _name] = BoolProperty(
            name=_title(_name), default=(_prefix == "sg_" and _name == "flat"))


_CLASSES = (VGColorPreset, VGMaterialSettings, VGObjectSettings, VGRideSettings)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    Scene.vg_ride = PointerProperty(type=VGRideSettings)
    Object.vg_object = PointerProperty(type=VGObjectSettings)
    Material.vg_material = PointerProperty(type=VGMaterialSettings)


def unregister():
    del Material.vg_material
    del Object.vg_object
    del Scene.vg_ride
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
