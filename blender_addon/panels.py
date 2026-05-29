"""UI panels: ride settings (3D View N-panel) + per-object/per-material roles."""

import bpy
from bpy.types import Panel


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
            box.prop(rs, "sprites", expand=True)

        box = layout.box()
        box.label(text="Train", icon="AUTO")
        row = box.row(align=True)
        row.prop(rs, "min_cars")
        row.prop(rs, "max_cars")
        box.prop(rs, "build_menu_priority")
        box.prop(rs, "running_sound")
        box.prop(rs, "secondary_sound")
        box.prop(rs, "ride_flags", expand=True)

        box = layout.box()
        box.label(text="Default Colours", icon="COLOR")
        box.prop(rs, "color_main")
        box.prop(rs, "color_secondary")
        box.prop(rs, "color_tertiary")

        box = layout.box()
        box.label(text="Vehicle", icon="MOD_PHYSICS")
        box.prop(rs, "vehicle_flags", expand=True)
        row = box.row(align=True)
        row.prop(rs, "mass")
        row.prop(rs, "spacing")
        row = box.row(align=True)
        row.prop(rs, "draw_order")
        row.prop(rs, "effect_visual")

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
            layout.prop(os_, "rider_row")
        elif os_.role == "RESTRAINT":
            layout.prop(os_, "restraint_swing_deg")
            layout.label(text="Set object origin to the hinge", icon="INFO")


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


_CLASSES = (VG_PT_ride, VG_PT_object, VG_PT_material)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
