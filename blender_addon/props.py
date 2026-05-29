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


def _flag_items(names):
    """4-tuples with explicit bit values for an ENUM_FLAG (multi-select)."""
    return [(n, _title(n), "", 1 << i) for i, n in enumerate(names)]


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
    sprites: EnumProperty(
        name="Sprite Groups",
        items=_flag_items(SPRITE_GROUP_NAMES),
        options={"ENUM_FLAG"},
        default={"flat"},
    )
    ride_flags: EnumProperty(
        name="Ride Flags",
        items=_flag_items(RIDE_FLAG_NAMES),
        options={"ENUM_FLAG"},
        default=set(),
    )
    running_sound: EnumProperty(name="Running Sound", items=_simple_items(RUNNING_SOUND_NAMES))
    secondary_sound: EnumProperty(
        name="Secondary Sound", items=_simple_items(SECONDARY_SOUND_NAMES)
    )
    min_cars: IntProperty(name="Min Cars / Train", default=1, min=1)
    max_cars: IntProperty(name="Max Cars / Train", default=8, min=1)
    build_menu_priority: IntProperty(name="Build Menu Priority", default=0, min=0)

    # --- Default colours (one preset) --------------------------------------
    color_main: EnumProperty(name="Main", items=_simple_items(COLOR_NAMES), default="bright_red")
    color_secondary: EnumProperty(
        name="Secondary", items=_simple_items(COLOR_NAMES), default="black"
    )
    color_tertiary: EnumProperty(
        name="Tertiary", items=_simple_items(COLOR_NAMES), default="grey"
    )

    # --- Single vehicle params ---------------------------------------------
    vehicle_flags: EnumProperty(
        name="Vehicle Flags",
        description="restraint_animation is added automatically when a Restraint object exists",
        items=_flag_items([n for n in VEHICLE_FLAG_NAMES if n != "restraint_animation"]),
        options={"ENUM_FLAG"},
        default=set(),
    )
    mass: IntProperty(name="Mass", default=100, min=0)
    spacing: FloatProperty(name="Spacing", default=2.0, min=0.0)
    draw_order: IntProperty(name="Draw Order", default=1, min=0)
    effect_visual: IntProperty(name="Effect Visual", default=1, min=0)

    preview: PointerProperty(name="Preview Image", type=bpy.types.Image)


_CLASSES = (VGMaterialSettings, VGObjectSettings, VGRideSettings)


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
