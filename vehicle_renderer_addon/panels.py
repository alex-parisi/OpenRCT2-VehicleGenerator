"""UI panels: ride settings (3D View N-panel) + per-object/per-material roles."""

import bpy
from bpy.types import Panel, UIList

from . import props


class VG_UL_color_presets(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, "main", text="")
        row.prop(item, "secondary", text="")
        row.prop(item, "tertiary", text="")


class VG_UL_car_types(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, "name", text="", emboss=False, icon="MOD_PHYSICS")
        row.prop(item, "slot", text="")


class VG_UL_lights(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.label(text="", icon="LIGHT")
        row.prop(item, "type", text="")
        row.prop(item, "strength", text="")


class VG_PT_ride(Panel):
    bl_label = "OpenRCT2 Vehicle"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OpenRCT2"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        rs = context.scene.vg_ride

        box = layout.box()
        box.label(text="Identity", icon="INFO")
        box.prop(rs, "id")
        box.prop(rs, "original_id")
        box.prop(rs, "name")
        box.prop(rs, "description")
        box.prop(rs, "capacity")
        box.prop(rs, "authors")
        box.prop(rs, "version")
        box.prop(rs, "ride_type")
        box.prop(rs, "scale_preset")
        if rs.scale_preset == "CUSTOM":
            box.prop(rs, "units_per_tile")

        box = layout.box()
        box.label(text="Sprites", icon="IMAGE_DATA")
        box.prop(rs, "dither")
        box.prop(rs, "sprites_all")
        if not rs.sprites_all:
            grid = box.grid_flow(row_major=True, columns=2, even_columns=True)
            for attr, _name in props.flag_items("sg_"):
                grid.prop(rs, attr)

        box = layout.box()
        box.label(text="Train", icon="AUTO")
        row = box.row(align=True)
        row.prop(rs, "min_cars")
        row.prop(rs, "max_cars")
        box.prop(rs, "zero_cars")
        box.prop(rs, "build_menu_priority")
        box.prop(rs, "running_sound")
        box.prop(rs, "secondary_sound")
        box.label(text="Ride Flags:")
        for attr, _name in props.flag_items("rf_"):
            box.prop(rs, attr)

        box = layout.box()
        box.label(text="Default Colours", icon="COLOR")
        row = box.row()
        row.template_list(
            "VG_UL_color_presets", "", rs, "color_presets", rs, "color_preset_index", rows=3
        )
        col = row.column(align=True)
        col.operator("vg.color_preset_add", icon="ADD", text="")
        col.operator("vg.color_preset_remove", icon="REMOVE", text="")

        box = layout.box()
        box.label(text="Car Types", icon="MOD_PHYSICS")
        row = box.row()
        row.template_list("VG_UL_car_types", "", rs, "car_types", rs, "car_type_index", rows=3)
        col = row.column(align=True)
        col.operator("vg.car_type_add", icon="ADD", text="")
        col.operator("vg.car_type_remove", icon="REMOVE", text="")

        if rs.car_types:
            ct = rs.car_types[rs.car_type_index]
            sub = box.column()
            sub.prop(ct, "collection")
            sub.prop(ct, "offset")
            sub.prop(ct, "slot")
            sub.prop(ct, "preview_tab")
            row = sub.row(align=True)
            row.prop(ct, "mass")
            row.prop(ct, "spacing")
            row = sub.row(align=True)
            row.prop(ct, "draw_order")
            row.prop(ct, "effect_visual")
            sub.label(text="Vehicle Flags:")
            for attr, _name in props.flag_items("vf_"):
                sub.prop(ct, attr)
        else:
            box.label(
                text="No car types - exporting the whole scene as one default car.", icon="INFO"
            )

        box = layout.box()
        row = box.row()
        row.prop(
            rs,
            "show_lights",
            icon="TRIA_DOWN" if rs.show_lights else "TRIA_RIGHT",
            emboss=False,
        )
        row.label(text="", icon="LIGHT_SUN")
        if rs.show_lights:
            row = box.row()
            row.template_list("VG_UL_lights", "", rs, "lights", rs, "light_index", rows=3)
            col = row.column(align=True)
            col.operator("vg.light_add", icon="ADD", text="")
            col.operator("vg.light_remove", icon="REMOVE", text="")
            if rs.lights:
                light = rs.lights[rs.light_index]
                sub = box.column()
                sub.prop(light, "type")
                sub.prop(light, "shadow")
                sub.prop(light, "direction")
                sub.prop(light, "strength")
            else:
                box.label(text="No lights - using the default lighting rig.", icon="INFO")

        layout.prop(rs, "preview")

        col = layout.column(align=True)
        col.scale_y = 1.3
        col.operator("vg.test_render", icon="RENDER_STILL")
        col.operator("vg.export_parkobj", icon="EXPORT")


def _draw_material_settings(layout, ms):
    """Draw a material's OpenRCT2 region/flags/shading settings.

    Shared so the per-material controls can live in the Object panel (folded in
    next to the object's role) instead of forcing a trip to the Material
    Properties tab
    """
    layout.prop(ms, "region")
    col = layout.column(align=True)
    col.prop(ms, "is_mask")
    col.prop(ms, "no_ao")
    col.prop(ms, "edge")
    col.prop(ms, "dark_edge")
    col.prop(ms, "no_bleed")
    layout.prop(ms, "texture")

    col = layout.column(align=True)
    col.label(text="Shading")
    row = col.row(align=True)
    row.prop(ms, "use_color_override", text="")
    sub = row.row()
    sub.enabled = ms.use_color_override
    sub.prop(ms, "diffuse_color", text="Color")
    col.prop(ms, "specular_exponent")
    col.prop(ms, "specular_intensity")
    row = col.row(align=True)
    row.prop(ms, "use_specular_tint", text="")
    sub = row.row()
    sub.enabled = ms.use_specular_tint
    sub.prop(ms, "specular_tint", text="Specular Tint")


def _draw_object_settings(layout, obj):
    """Draw the active object's role, role-specific options, and its materials.

    Lives in the 3D View N-panel (next to the ride-wide settings) so the whole
    vehicle can be authored from the viewport sidebar without leaving it.
    """
    os_ = obj.vg_object
    layout.prop(os_, "role")
    if os_.role == "RIDER":
        layout.prop(os_, "rider_number")
        layout.label(text="Peeps pair into seat rows: 0+1, 2+3, ...", icon="INFO")
        layout.label(
            text="Remappable materials auto-set: left=Remap1, right=Remap2",
            icon="INFO",
        )
    elif os_.role == "RESTRAINT":
        layout.prop(os_, "restraint_swing_deg")
        layout.prop(os_, "anim_start_frame")
        layout.prop(os_, "anim_end_frame")
        layout.label(text="Set object origin to the hinge", icon="INFO")
        layout.label(
            text="Keyframe the transform to override the swing value",
            icon="INFO",
        )

    if os_.role == "IGNORE":
        return

    # Per-material settings, folded in so authoring a part never requires a
    # separate tab. Multi-material objects pick the slot to edit from the list.
    box = layout.box()
    box.label(text="Materials", icon="MATERIAL")
    if not obj.material_slots:
        box.label(text="No materials on this object.", icon="INFO")
        return
    if len(obj.material_slots) > 1:
        box.template_list(
            "MATERIAL_UL_matslots", "", obj, "material_slots",
            obj, "active_material_index", rows=2,
        )
    mat = obj.active_material
    if mat is None:
        box.label(text="Empty material slot.", icon="INFO")
    else:
        _draw_material_settings(box, mat.vg_material)


# --- Shared "Selected Object" container -------------------------------------
# The vehicle and scenery add-ons each ship an identical copy of this trivial
# parent panel and register it cooperatively (guarded by idname) so a single
# "Selected Object" panel hosts whichever add-ons are installed. Each add-on
# contributes a child sub-panel via ``bl_parent_id``; this parent owns only the
# header. The two copies MUST keep the same ``bl_idname``.
_SHARED_PARENT_IDNAME = "OPENRCT2_PT_selected_object"


class OPENRCT2_PT_selected_object(Panel):
    bl_idname = _SHARED_PARENT_IDNAME
    bl_label = "Selected Object"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OpenRCT2"
    bl_order = 1

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH"

    def draw(self, context):
        pass


def _register_shared_parent():
    """Register the shared parent unless another add-on already did."""
    if not hasattr(bpy.types, _SHARED_PARENT_IDNAME):
        bpy.utils.register_class(OPENRCT2_PT_selected_object)


def _unregister_shared_parent():
    """Drop the shared parent only once no add-on's child still nests under it.

    Call this *after* unregistering this add-on's own child panels, so the
    scan below sees only the other add-on's remaining children.
    """
    cls = getattr(bpy.types, _SHARED_PARENT_IDNAME, None)
    if cls is None:
        return
    for name in dir(bpy.types):
        if getattr(getattr(bpy.types, name, None), "bl_parent_id", "") == _SHARED_PARENT_IDNAME:
            return
    bpy.utils.unregister_class(cls)


class VG_PT_object_view3d(Panel):
    """The active object's vehicle settings, as a child of "Selected Object"."""

    bl_label = "Vehicle"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OpenRCT2"
    bl_parent_id = _SHARED_PARENT_IDNAME
    bl_order = 0

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH" and hasattr(obj, "vg_object")

    def draw(self, context):
        _draw_object_settings(self.layout, context.object)


_CLASSES = (
    VG_UL_color_presets,
    VG_UL_car_types,
    VG_UL_lights,
    VG_PT_ride,
    VG_PT_object_view3d,
)


def register():
    _register_shared_parent()
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    _unregister_shared_parent()
