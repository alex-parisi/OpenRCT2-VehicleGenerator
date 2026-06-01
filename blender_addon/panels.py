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

    def draw(self, context):
        layout = self.layout
        rs = context.scene.vg_ride

        box = layout.box()
        box.label(text="Identity", icon="INFO")
        box.prop(rs, "id")
        box.prop(rs, "name")
        box.prop(rs, "description")
        box.prop(rs, "capacity")
        box.prop(rs, "authors")
        box.prop(rs, "version")
        box.prop(rs, "ride_type")

        box = layout.box()
        box.label(text="Sprites", icon="IMAGE_DATA")
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
            sub.prop(ct, "slot")
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


class VG_PT_object(Panel):
    bl_label = "OpenRCT2 Vehicle"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "MESH"

    def draw(self, context):
        layout = self.layout
        os_ = context.object.vg_object
        layout.prop(os_, "role")
        if os_.role == "RIDER":
            layout.prop(os_, "rider_number")
            layout.label(text="Peeps pair into seat rows: 0+1, 2+3, ...", icon="INFO")
        elif os_.role == "RESTRAINT":
            layout.prop(os_, "restraint_swing_deg")
            layout.prop(os_, "anim_start_frame")
            layout.prop(os_, "anim_end_frame")
            layout.label(text="Set object origin to the hinge", icon="INFO")
            layout.label(
                text="Keyframe the transform to override the swing value",
                icon="INFO",
            )


class VG_PT_material(Panel):
    bl_label = "OpenRCT2 Material"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    @classmethod
    def poll(cls, context):
        return context.material is not None

    def draw(self, context):
        layout = self.layout
        ms = context.material.vg_material
        layout.prop(ms, "region")
        col = layout.column(align=True)
        col.prop(ms, "is_mask")
        col.prop(ms, "is_visible_mask")
        col.prop(ms, "no_ao")
        col.prop(ms, "edge")
        col.prop(ms, "dark_edge")
        col.prop(ms, "no_bleed")
        col.prop(ms, "flat_shaded")
        layout.prop(ms, "specular_exponent")
        layout.prop(ms, "texture")


_CLASSES = (
    VG_UL_color_presets,
    VG_UL_car_types,
    VG_UL_lights,
    VG_PT_ride,
    VG_PT_object,
    VG_PT_material,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
