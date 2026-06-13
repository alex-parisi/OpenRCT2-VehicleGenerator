"""Blender operators: fast test render and the threaded .parkobj export.

NOTE: no ``from __future__ import annotations``; the operators declare bpy
properties (``filepath``/``filter_glob``) as annotations, and PEP 563 would
stringify them and break registration.
"""

import os
import tempfile
import time

import bpy
from bpy.props import StringProperty
from bpy.types import Operator
from openrct2_object_common.blender.lights import lights_from_items
from openrct2_object_common.blender.modal import RenderModalBase
from openrct2_vehicle_generator.exporter import export_ride_test, export_ride_to
from openrct2_vehicle_generator.loader import build_ride
from openrct2_x7_renderer.ray_trace import Context

from . import scene_to_ride
from .progress_overlay import ProgressOverlay


def _build_ride_from_scene(context):
    """Main-thread step: read bpy data into a Ride (raises on invalid scenes)."""
    config, meshes, preview = scene_to_ride.build_config_and_meshes(context)
    return build_ride(config, meshes, preview)


class VG_OT_test_render(Operator):
    bl_idname = "vg.test_render"
    bl_label = "Test Render"
    bl_description = "Render one viewpoint quickly and show it in the Image Editor"

    def execute(self, context):
        try:
            ride = _build_ride_from_scene(context)
        except scene_to_ride.SceneError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        except Exception as e:  # validation errors from the core loader
            self.report({"ERROR"}, f"Invalid vehicle: {e}")
            return {"CANCELLED"}

        ctx = Context(
            lights=lights_from_items(context.scene.vg_ride.lights),
            dither=context.scene.vg_ride.dither,
            upt=ride.units_per_tile,
            stability=context.scene.vg_ride.dither_stability,
        )
        tmp = tempfile.mkdtemp(prefix="vg_test_")
        try:
            export_ride_test(ride, ctx, tmp)
        except Exception as e:
            self.report({"ERROR"}, f"Render failed: {e}")
            return {"CANCELLED"}

        png = os.path.join(tmp, "car_0_0.png")
        if not os.path.exists(png):
            self.report({"WARNING"}, "Render produced no sprite")
            return {"CANCELLED"}

        img = bpy.data.images.load(png, check_existing=False)
        for area in context.screen.areas:
            if area.type == "IMAGE_EDITOR":
                area.spaces.active.image = img
                break
        self.report({"INFO"}, f"Test sprite loaded: {img.name}")
        return {"FINISHED"}


class VG_OT_export_parkobj(RenderModalBase):
    bl_idname = "vg.export_parkobj"
    bl_label = "Export .parkobj"
    bl_description = "Render every sprite and write an OpenRCT2 .parkobj"

    _status_verb = "Exporting .parkobj"
    _invalid_prefix = "Invalid vehicle"
    _clean_error_types = (scene_to_ride.SceneError,)

    filepath: StringProperty(subtype="FILE_PATH")
    filename_ext = ".parkobj"
    filter_glob: StringProperty(default="*.parkobj", options={"HIDDEN"})

    def invoke(self, context, event):
        rs = context.scene.vg_ride
        if not self.filepath:
            base = (rs.id or "vehicle").replace("/", "_")
            self.filepath = bpy.path.ensure_ext(base, ".parkobj")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def _build(self, context):
        return _build_ride_from_scene(context)

    def _prepare(self, context, ride) -> None:
        # Read scene data on the main thread; the worker must not touch bpy data.
        self._lights = lights_from_items(context.scene.vg_ride.lights)
        self._dither = context.scene.vg_ride.dither
        self._dither_stability = context.scene.vg_ride.dither_stability
        self._parkobj = bpy.path.abspath(self.filepath)
        self._work = tempfile.mkdtemp(prefix="vg_export_")
        # In-viewport progress bar; the shared base also drives a status-bar
        # percentage from the same set_progress() calls.
        self._overlay = ProgressOverlay()
        self._overlay.add()

    def _render(self, ride) -> None:
        def on_progress(done: int, total: int) -> None:
            # Plain int writes from the worker; the modal timer reads them to
            # repaint. No lock needed for single-word assignments.
            self.set_progress(done, total)
            self._overlay.done = done
            self._overlay.total = total

        ctx = Context(
            lights=self._lights,
            dither=self._dither,
            upt=ride.units_per_tile,
            stability=self._dither_stability,
        )
        export_ride_to(ride, ctx, self._parkobj, self._work, progress=on_progress)

    def _set_status(self, context) -> None:
        super()._set_status(context)
        self._overlay.tag_redraw(context)

    def _finish(self, context):
        self._overlay.remove()
        self._overlay.tag_redraw(context)
        return super()._finish(context)

    def _on_success(self, context):
        elapsed = int(time.monotonic() - self._start_time)
        self.report({"INFO"}, f"Exported {os.path.basename(self._parkobj)} in {elapsed}s")
        return {"FINISHED"}


class VG_OT_color_preset_add(Operator):
    bl_idname = "vg.color_preset_add"
    bl_label = "Add Colour Preset"
    bl_description = "Add another default colour preset (OpenRCT2 supports up to 3)"

    def execute(self, context):
        rs = context.scene.vg_ride
        if len(rs.color_presets) >= 3:
            self.report({"WARNING"}, "OpenRCT2 supports at most 3 colour presets")
            return {"CANCELLED"}
        rs.color_presets.add()
        rs.color_preset_index = len(rs.color_presets) - 1
        return {"FINISHED"}


class VG_OT_color_preset_remove(Operator):
    bl_idname = "vg.color_preset_remove"
    bl_label = "Remove Colour Preset"
    bl_description = "Remove the selected colour preset"

    def execute(self, context):
        rs = context.scene.vg_ride
        if not rs.color_presets:
            return {"CANCELLED"}
        rs.color_presets.remove(rs.color_preset_index)
        rs.color_preset_index = max(0, min(rs.color_preset_index, len(rs.color_presets) - 1))
        return {"FINISHED"}


class VG_OT_car_type_add(Operator):
    bl_idname = "vg.car_type_add"
    bl_label = "Add Car Type"
    bl_description = "Add another car-type variant (default / front / rear)"

    def execute(self, context):
        rs = context.scene.vg_ride
        ct = rs.car_types.add()
        ct.name = f"Car Type {len(rs.car_types)}"
        # First car type defaults to the Default slot so a fresh setup is valid.
        if len(rs.car_types) == 1:
            ct.slot = "DEFAULT"
        rs.car_type_index = len(rs.car_types) - 1
        return {"FINISHED"}


class VG_OT_car_type_remove(Operator):
    bl_idname = "vg.car_type_remove"
    bl_label = "Remove Car Type"
    bl_description = "Remove the selected car type"

    def execute(self, context):
        rs = context.scene.vg_ride
        if not rs.car_types:
            return {"CANCELLED"}
        rs.car_types.remove(rs.car_type_index)
        rs.car_type_index = max(0, min(rs.car_type_index, len(rs.car_types) - 1))
        return {"FINISHED"}


class VG_OT_light_add(Operator):
    bl_idname = "vg.light_add"
    bl_label = "Add Light"
    bl_description = "Add a light to the custom lighting rig"

    def execute(self, context):
        rs = context.scene.vg_ride
        rs.lights.add()
        rs.light_index = len(rs.lights) - 1
        return {"FINISHED"}


class VG_OT_light_remove(Operator):
    bl_idname = "vg.light_remove"
    bl_label = "Remove Light"
    bl_description = "Remove the selected light from the custom lighting rig"

    def execute(self, context):
        rs = context.scene.vg_ride
        if not rs.lights:
            return {"CANCELLED"}
        rs.lights.remove(rs.light_index)
        rs.light_index = max(0, min(rs.light_index, len(rs.lights) - 1))
        return {"FINISHED"}


_CLASSES = (
    VG_OT_test_render,
    VG_OT_export_parkobj,
    VG_OT_color_preset_add,
    VG_OT_color_preset_remove,
    VG_OT_car_type_add,
    VG_OT_car_type_remove,
    VG_OT_light_add,
    VG_OT_light_remove,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
