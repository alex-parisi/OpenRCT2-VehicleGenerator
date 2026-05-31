"""Blender PropertyGroups for the scenery add-on.

Mirrors the config the core `build_small_scenery` / `build_large_scenery`
consume (see scene_to_scenery.py), expressed as native Blender properties so a
scenery object is authored entirely in the UI. Uses a `vgs_` prefix so this
add-on can coexist with the vehicle add-on (`vg_`).

NOTE: no ``from __future__ import annotations`` — PEP 563 would stringify the
``prop: SomeProperty(...)`` definitions and break Blender registration.
"""

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
from openrct2_scenery_generator.constants import DEFAULT_CURSOR, SMALL_SCENERY_SHAPES


def _title(name: str) -> str:
    return name.replace("_", " ").title()


def _simple_items(names):
    return [(n, _title(n), "") for n in names]


OBJECT_TYPE_ITEMS = [
    ("scenery_small", "Small Scenery", "Single-tile scenery (1 or 4 rotations)"),
    ("scenery_large", "Large Scenery", "Multi-tile scenery built from a tiles list"),
]

OBJECT_ROLE_ITEMS = [
    ("GEOMETRY", "Geometry", "Part of the scenery model"),
    ("IGNORE", "Ignore", "Not part of the scenery"),
]

SHAPE_ITEMS = [(s, s, "") for s in SMALL_SCENERY_SHAPES]

# Same material-region scheme as the vehicle add-on; "NONE" is a plain colour,
# the REMAP* regions are recoloured by the placement colours.
MATERIAL_REGION_ITEMS = [
    ("NONE", "None", "Plain shaded colour"),
    ("REMAP1", "Remap 1 (primary colour)", "Recoloured by the object's primary colour"),
    ("REMAP2", "Remap 2 (secondary)", "Recoloured by the secondary colour"),
    ("REMAP3", "Remap 3 (tertiary)", "Recoloured by the tertiary colour"),
    ("GREYSCALE", "Greyscale", "Greyscale shading region"),
    ("PEEP", "Peep", "Peep region"),
    ("CHAIN", "Chain", "Chain region"),
]

LIGHT_TYPE_ITEMS = [
    ("diffuse", "Diffuse", "Directional diffuse light"),
    ("specular", "Specular", "Specular highlight light"),
]


class VGSMaterialSettings(PropertyGroup):
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


class VGSObjectSettings(PropertyGroup):
    role: EnumProperty(
        name="Role",
        description="Whether this object is part of the scenery model",
        items=OBJECT_ROLE_ITEMS,
        default="GEOMETRY",
    )


class VGSTile(PropertyGroup):
    """One large-scenery tile. x/y are tile indices (the exporter converts to
    OpenRCT2 coordinate units); z/clearance are in coordinate units."""

    x: IntProperty(name="X", description="Tile index along OBJ +X", default=0)
    y: IntProperty(name="Y", description="Tile index along OBJ +Z", default=0)
    z: IntProperty(name="Z", description="Height offset (coordinate units)", default=0)
    clearance: IntProperty(
        name="Clearance", description="Vertical clearance (coordinate units)", default=40, min=0
    )


class VGSLight(PropertyGroup):
    type: EnumProperty(name="Type", items=LIGHT_TYPE_ITEMS, default="diffuse")
    shadow: BoolProperty(name="Casts Shadow", default=False)
    direction: FloatVectorProperty(
        name="Direction",
        description="Direction in OBJ space (+X forward, +Y up, +Z right); normalized at render",
        size=3,
        default=(0.0, 1.0, 0.0),
        subtype="XYZ",
    )
    strength: FloatProperty(name="Strength", default=0.5, min=0.0)


class VGSScenerySettings(PropertyGroup):
    # --- Type & identity ---------------------------------------------------
    object_type: EnumProperty(name="Type", items=OBJECT_TYPE_ITEMS, default="scenery_small")
    id: StringProperty(
        name="Object ID",
        description="Unique id, e.g. openrct2vg.scenery_small.my_obj (avoid vanilla ids)",
        default="openrct2vg.scenery_small.my_object",
    )
    name: StringProperty(name="Name", default="My Scenery")
    authors: StringProperty(name="Authors", description="Comma-separated", default="")
    version: StringProperty(name="Version", default="1.0")
    preview: StringProperty(
        name="Preview Image", description="Path to a preview image", subtype="FILE_PATH", default=""
    )

    # --- Common placement --------------------------------------------------
    price: FloatProperty(name="Price", default=2.0)
    removal_price: FloatProperty(name="Removal Price", default=1.0)
    cursor: StringProperty(name="Cursor", default=DEFAULT_CURSOR)
    scenery_group: StringProperty(
        name="Scenery Group", description="Optional scenery-group object id", default=""
    )
    has_primary_colour: BoolProperty(
        name="Primary Colour",
        description="Recolourable; pairs with Remap 1 materials",
        default=False,
    )
    has_secondary_colour: BoolProperty(name="Secondary Colour", default=False)

    # --- Small scenery -----------------------------------------------------
    height: IntProperty(
        name="Height", description="Clearance in Z coordinate units (8 per step)", default=64, min=0
    )
    shape: EnumProperty(name="Shape", items=SHAPE_ITEMS, default="4/4")
    is_rotatable: BoolProperty(name="Rotatable", default=True)
    is_stackable: BoolProperty(name="Stackable", default=False)
    requires_flat_surface: BoolProperty(name="Requires Flat Surface", default=False)
    prohibit_walls: BoolProperty(name="Prohibit Walls", default=False)
    is_tree: BoolProperty(name="Tree", default=False)

    # --- Large scenery -----------------------------------------------------
    has_tertiary_colour: BoolProperty(name="Tertiary Colour", default=False)
    is_photogenic: BoolProperty(name="Photogenic", default=False)
    scrolling_mode: IntProperty(
        name="Scrolling Mode",
        description="255 = none. Only set for scrolling signs.",
        default=255,
        min=0,
        max=255,
    )
    tiles: CollectionProperty(type=VGSTile)
    tile_index: IntProperty(default=0)

    # --- Custom lighting ---------------------------------------------------
    lights: CollectionProperty(type=VGSLight)
    light_index: IntProperty(default=0)
    show_lights: BoolProperty(
        name="Custom Lighting",
        description="Override the default lighting rig with a custom one",
        default=False,
    )


_CLASSES = (
    VGSMaterialSettings,
    VGSObjectSettings,
    VGSTile,
    VGSLight,
    VGSScenerySettings,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    Scene.vgs_scenery = PointerProperty(type=VGSScenerySettings)
    Object.vgs_object = PointerProperty(type=VGSObjectSettings)
    Material.vgs_material = PointerProperty(type=VGSMaterialSettings)


def unregister():
    del Material.vgs_material
    del Object.vgs_object
    del Scene.vgs_scenery
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
