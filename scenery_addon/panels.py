"""UI panels for the scenery add-on: scene settings (3D View N-panel) +
per-object role + per-material region."""

import bpy
from bpy.types import Panel, UIList


class VGS_UL_tiles(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.label(text="", icon="MESH_PLANE")
        row.prop(item, "x", text="X")
        row.prop(item, "y", text="Y")
        row.prop(item, "clearance", text="Clr")


class VGS_UL_lights(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.label(text="", icon="LIGHT")
        row.prop(item, "type", text="")
        row.prop(item, "strength", text="")


class VGS_PT_scenery(Panel):
    bl_label = "OpenRCT2 Scenery"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OpenRCT2"

    def draw(self, context):
        layout = self.layout
        ss = context.scene.vgs_scenery

        layout.prop(ss, "object_type")

        box = layout.box()
        box.label(text="Identity", icon="INFO")
        box.prop(ss, "id")
        box.prop(ss, "name")
        box.prop(ss, "authors")
        box.prop(ss, "version")

        box = layout.box()
        box.label(text="Placement", icon="TOOL_SETTINGS")
        row = box.row(align=True)
        row.prop(ss, "price")
        row.prop(ss, "removal_price")
        box.prop(ss, "cursor")
        box.prop(ss, "scenery_group")
        box.prop(ss, "has_primary_colour")
        box.prop(ss, "has_secondary_colour")

        if ss.object_type == "scenery_small":
            box = layout.box()
            box.label(text="Small Scenery", icon="MESH_CUBE")
            box.prop(ss, "shape")
            box.prop(ss, "height")
            col = box.column(align=True)
            col.prop(ss, "is_rotatable")
            col.prop(ss, "is_stackable")
            col.prop(ss, "requires_flat_surface")
            col.prop(ss, "prohibit_walls")
            col.prop(ss, "is_tree")
        else:
            box = layout.box()
            box.label(text="Large Scenery", icon="MESH_GRID")
            col = box.column(align=True)
            col.prop(ss, "has_tertiary_colour")
            col.prop(ss, "is_photogenic")
            box.prop(ss, "scrolling_mode")
            box.label(text="Tiles (x/y are tile indices):")
            row = box.row()
            row.template_list("VGS_UL_tiles", "", ss, "tiles", ss, "tile_index", rows=3)
            colb = row.column(align=True)
            colb.operator("vgs.tile_add", icon="ADD", text="")
            colb.operator("vgs.tile_remove", icon="REMOVE", text="")
            if ss.tiles:
                t = ss.tiles[ss.tile_index]
                sub = box.column(align=True)
                rr = sub.row(align=True)
                rr.prop(t, "x")
                rr.prop(t, "y")
                rr = sub.row(align=True)
                rr.prop(t, "z")
                rr.prop(t, "clearance")
            else:
                box.label(text="No tiles - add at least one.", icon="ERROR")

        box = layout.box()
        row = box.row()
        row.prop(
            ss, "show_lights",
            icon="TRIA_DOWN" if ss.show_lights else "TRIA_RIGHT", emboss=False,
        )
        row.label(text="", icon="LIGHT_SUN")
        if ss.show_lights:
            row = box.row()
            row.template_list("VGS_UL_lights", "", ss, "lights", ss, "light_index", rows=3)
            col = row.column(align=True)
            col.operator("vgs.light_add", icon="ADD", text="")
            col.operator("vgs.light_remove", icon="REMOVE", text="")
            if ss.lights:
                light = ss.lights[ss.light_index]
                sub = box.column()
                sub.prop(light, "type")
                sub.prop(light, "shadow")
                sub.prop(light, "direction")
                sub.prop(light, "strength")
            else:
                box.label(text="No lights - using the default rig.", icon="INFO")

        layout.prop(ss, "preview")

        col = layout.column(align=True)
        col.scale_y = 1.3
        col.operator("vgs.test_render", icon="RENDER_STILL")
        col.operator("vgs.export_parkobj", icon="EXPORT")


class VGS_PT_object(Panel):
    bl_label = "OpenRCT2 Scenery"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "MESH"

    def draw(self, context):
        layout = self.layout
        layout.prop(context.object.vgs_object, "role")


class VGS_PT_material(Panel):
    bl_label = "OpenRCT2 Scenery Material"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    @classmethod
    def poll(cls, context):
        return context.material is not None

    def draw(self, context):
        layout = self.layout
        ms = context.material.vgs_material
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
    VGS_UL_tiles,
    VGS_UL_lights,
    VGS_PT_scenery,
    VGS_PT_object,
    VGS_PT_material,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
