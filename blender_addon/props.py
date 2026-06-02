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
    FloatVectorProperty,
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
    TILE_SIZE,
    VEHICLE_FLAG_NAMES,
)

_ADDON_DIR = os.path.dirname(__file__)


def _title(name: str) -> str:
    return name.replace("_", " ").title()


def _simple_items(names):
    """(identifier, label, description) tuples for a single-select enum."""
    return [(n, _title(n), "") for n in names]


# Each multi-select flag group is exposed as one BoolProperty per flag
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
]

OBJECT_ROLE_ITEMS = [
    ("IGNORE", "Ignore", "Not part of the vehicle"),
    ("BODY", "Body", "Static part of the car"),
    ("RESTRAINT", "Restraint", "Lap bar / restraint that animates"),
    ("RIDER", "Rider seat", "A peep mesh; paired into seat rows by Rider Number"),
]


# Slot identifiers map onto CarIndex in the exporter. `second`/`third` are
# parsed by the loader but not emitted to object.json today, so we hide them
# until that path is wired up.
SLOT_ITEMS = [
    ("NONE", "(none)", "Don't include this car type in the output"),
    ("DEFAULT", "Default", "Standard car for the middle of the train"),
    ("FRONT", "Front (head car)", "Used for the lead car"),
    ("REAR", "Rear (tail car)", "Used for the last car"),
]


def _slot_update(self, context):
    """Enforce slot uniqueness: clear the slot on any other car type that holds it."""
    if self.slot == "NONE":
        return
    rs = self.id_data.vg_ride
    me = self.as_pointer()
    for ct in rs.car_types:
        if ct.as_pointer() == me:
            continue
        if ct.slot == self.slot:
            ct.slot = "NONE"


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
    no_ao: BoolProperty(name="No Ambient Occlusion", default=False)
    edge: BoolProperty(name="Edge AA", default=False)
    dark_edge: BoolProperty(name="Dark Edge AA", default=False)
    no_bleed: BoolProperty(name="No Bleed", default=False)
    texture: PointerProperty(
        name="Texture",
        description="Optional image; must be saved to disk (its file is read at export)",
        type=bpy.types.Image,
    )
    # --- Shading (the renderer's Phong model, set directly) -----------------
    # These drive the renderer's Material fields without going through Blender's
    # PBR shader. Specular is always taken from here; diffuse colour falls back
    # to the shader's Base Color unless overridden below.
    use_color_override: BoolProperty(
        name="Override Color",
        description="Use the color below instead of the shader's Base Color",
        default=False,
    )
    diffuse_color: FloatVectorProperty(
        name="Color",
        description="Flat diffuse color (used when Override Color is on)",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(0.8, 0.8, 0.8),
    )
    specular_intensity: FloatProperty(
        name="Specular Intensity",
        description="Brightness of the specular highlight (scales the specular color)",
        default=0.5,
        min=0.0,
        soft_max=1.0,
    )
    specular_exponent: FloatProperty(
        name="Specular Hardness",
        description="Tightness of the specular highlight (higher = smaller, sharper)",
        default=50.0,
        min=1.0,
        soft_max=256.0,
    )
    use_specular_tint: BoolProperty(
        name="Tint Highlight",
        description="Tint the specular highlight with the color below (off = white)",
        default=False,
    )
    specular_tint: FloatVectorProperty(
        name="Specular Tint",
        description="Specular highlight color (used when Tint Highlight is on)",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0),
    )


class VGObjectSettings(PropertyGroup):
    role: EnumProperty(
        name="Role",
        description="This object's part in the vehicle",
        items=OBJECT_ROLE_ITEMS,
        default="IGNORE",
    )
    rider_number: IntProperty(
        name="Rider Number",
        description=(
            "Order this peep among the car's riders. Peeps are sorted by this "
            "number and paired into seat rows: 0+1 = first row, 2+3 = second row, "
            "and so on."
        ),
        default=0,
        min=0,
    )
    restraint_swing_deg: FloatProperty(
        name="Restraint Swing",
        description=(
            "Total degrees the restraint swings across its 4 animation frames. "
            "Set the object's ORIGIN to the hinge so it pivots correctly. "
            "Ignored if the object has keyframes — the keyframed transform is "
            "sampled instead."
        ),
        default=90.0,
    )
    anim_start_frame: IntProperty(
        name="Anim Start Frame",
        description=(
            "First scene frame to sample for keyframed restraint animation. "
            "Only used when the object has keyframes."
        ),
        default=1,
        min=0,
    )
    anim_end_frame: IntProperty(
        name="Anim End Frame",
        description=(
            "Last scene frame to sample. The four animation states are sampled "
            "at evenly-spaced ticks across [start, end]."
        ),
        default=4,
        min=0,
    )


class VGCarType(PropertyGroup):
    """One car-type variant (default/front/rear). Becomes one entry in vehicles[]."""

    name: StringProperty(name="Name", default="Car Type")
    collection: PointerProperty(
        name="Collection",
        description="Blender Collection containing this car type's objects",
        type=bpy.types.Collection,
    )
    slot: EnumProperty(
        name="Slot",
        description="Which OpenRCT2 car slot this car type fills",
        items=SLOT_ITEMS,
        default="NONE",
        update=_slot_update,
    )
    mass: IntProperty(name="Mass", default=100, min=0)
    spacing: FloatProperty(name="Spacing", default=2.0, min=0.0)
    draw_order: IntProperty(name="Draw Order", default=1, min=0)
    effect_visual: IntProperty(name="Effect Visual", default=1, min=0)
    # Per-flag vehicle-flag bools are injected after this class


# Light type identifiers
LIGHT_TYPE_ITEMS = [
    ("diffuse", "Diffuse", "Directional diffuse light"),
    ("specular", "Specular", "Specular highlight light"),
]


class VGLight(PropertyGroup):
    """One entry in a custom lighting rig. Mirrors a `lights[]` config entry."""

    type: EnumProperty(name="Type", items=LIGHT_TYPE_ITEMS, default="diffuse")
    shadow: BoolProperty(
        name="Casts Shadow",
        description="Whether this light contributes to ambient-occlusion shadowing",
        default=False,
    )
    direction: FloatVectorProperty(
        name="Direction",
        description="Direction in OBJ space (+X forward, +Y up, +Z right); normalized at render",
        size=3,
        default=(0.0, 1.0, 0.0),
        subtype="XYZ",
    )
    strength: FloatProperty(name="Strength", description="Light intensity", default=0.5, min=0.0)


# Render-scale presets
SCALE_PRESET_VALUES = {
    "REALISTIC": TILE_SIZE,
    "TILE": 1.0,
}
SCALE_PRESET_ITEMS = [
    ("REALISTIC", f"Realistic ({TILE_SIZE:g} m/tile)", "Match RCT2's real-world tile scale"),
    ("TILE", "1 unit = 1 tile", "Model in tiles: one OBJ unit spans one tile"),
    ("CUSTOM", "Custom", "Set the units-per-tile value manually"),
]


def _scale_preset_update(self, _context):
    """Write the preset's units-per-tile into the consumed value (Custom: no-op)."""
    value = SCALE_PRESET_VALUES.get(self.scale_preset)
    if value is not None:
        self.units_per_tile = value


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
    scale_preset: EnumProperty(
        name="Scale",
        description="How many OBJ units map to one OpenRCT2 tile",
        items=SCALE_PRESET_ITEMS,
        default="REALISTIC",
        update=_scale_preset_update,
    )
    units_per_tile: FloatProperty(
        name="Units / Tile",
        description=(
            "OBJ units per OpenRCT2 tile. Drives sprite size and the model->game "
            "conversions for car spacing and rider positions."
        ),
        default=TILE_SIZE,
        min=0.01,
        soft_max=16.0,
    )
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
    zero_cars: IntProperty(
        name="Zero Cars",
        description="Cars at the front that carry no riders (engines, etc.)",
        default=0,
        min=0,
    )
    build_menu_priority: IntProperty(name="Build Menu Priority", default=0, min=0)

    # --- Default colours (up to 3 build-menu presets) -----------------------
    color_presets: CollectionProperty(type=VGColorPreset)
    color_preset_index: IntProperty(default=0)

    # --- Car types ---------------------------------------------------------
    # A train can mix several car-type variants (default/front/rear). Each
    # entry maps to one vehicles[] entry; the slot assignments become the
    # configuration block. With no entries, the whole scene is rendered as a
    # single default car using built-in defaults.
    car_types: CollectionProperty(type=VGCarType)
    car_type_index: IntProperty(default=0)

    # --- Custom lighting ---------------------------------------------------
    # An optional override rig. With no entries the renderer uses the built-in
    # default lights; with one or more entries those replace the defaults.
    lights: CollectionProperty(type=VGLight)
    light_index: IntProperty(default=0)
    show_lights: BoolProperty(
        name="Custom Lighting",
        description="Override the default lighting rig with a custom one",
        default=False,
    )

    preview: StringProperty(
        name="Preview Image",
        description="Path to a preview image on disk",
        subtype="FILE_PATH",
        default="",
    )


# Inject one BoolProperty per flag before registration
for _prefix, _names in FLAG_GROUPS.items():
    target = VGCarType if _prefix == "vf_" else VGRideSettings
    for _name in _names:
        target.__annotations__[_prefix + _name] = BoolProperty(
            name=_title(_name), default=(_prefix == "sg_" and _name == "flat")
        )


_CLASSES = (VGColorPreset, VGLight, VGMaterialSettings, VGObjectSettings, VGCarType, VGRideSettings)


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
