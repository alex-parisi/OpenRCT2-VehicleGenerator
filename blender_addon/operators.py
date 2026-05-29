"""Blender operators: fast test render and the threaded .parkobj export.

NOTE: no ``from __future__ import annotations`` — the operators declare bpy
properties (``filepath``/``filter_glob``) as annotations, and PEP 563 would
stringify them and break registration.
"""

import os
import tempfile
import threading
import traceback

import bpy
import numpy as np
from bpy.props import StringProperty
from bpy.types import Operator
from openrct2_vehicle_generator.constants import LIGHT_DIFFUSE, LIGHT_SPECULAR, TILE_SIZE
from openrct2_vehicle_generator.exporter import export_ride_test, export_ride_to
from openrct2_vehicle_generator.loader import build_ride
from openrct2_vehicle_generator.ray_trace import Context
from openrct2_vehicle_generator.types import Light

from . import scene_to_ride


def _normalize(v):
    arr = np.array(v, dtype=np.float64)
    n = np.linalg.norm(arr)
    return arr / n if n > 0 else arr


def _default_lights() -> list[Light]:
    # Same hand-tuned rig as the CLI's __main__._default_lights.
    return [
        Light(LIGHT_DIFFUSE, 0, _normalize([0.0, -1.0, 0.0]), 0.1),
        Light(LIGHT_DIFFUSE, 0, _normalize([0.0, 0.5, -1.0]), 0.8),
        Light(LIGHT_SPECULAR, 1, _normalize([1.0, 1.65, -1.0]), 0.5),
        Light(LIGHT_DIFFUSE, 1, _normalize([1.0, 1.7, -1.0]), 0.8),
        Light(LIGHT_DIFFUSE, 0, np.array([0.0, 1.0, 0.0], dtype=np.float64), 0.45),
        Light(LIGHT_DIFFUSE, 0, _normalize([-1.0, 0.85, 1.0]), 0.475),
        Light(LIGHT_DIFFUSE, 0, _normalize([0.75, 0.4, -1.0]), 0.6),
        Light(LIGHT_DIFFUSE, 0, _normalize([1.0, 0.25, 0.0]), 0.5),
        Light(LIGHT_DIFFUSE, 0, _normalize([-1.0, -0.5, 0.0]), 0.1),
    ]


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

        ctx = Context.make(lights=_default_lights(), dither=True, upt=0.125 * TILE_SIZE)
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


class VG_OT_export_parkobj(Operator):
    bl_idname = "vg.export_parkobj"
    bl_label = "Export .parkobj"
    bl_description = "Render every sprite and write an OpenRCT2 .parkobj"

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

    def execute(self, context):
        # Build the Ride on the main thread (it reads bpy data); the resulting
        # meshes/preview are plain numpy, safe to render off-thread.
        try:
            ride = _build_ride_from_scene(context)
        except scene_to_ride.SceneError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        except Exception as e:
            self.report({"ERROR"}, f"Invalid vehicle: {e}")
            return {"CANCELLED"}

        self._parkobj = bpy.path.abspath(self.filepath)
        self._work = tempfile.mkdtemp(prefix="vg_export_")
        self._error: str | None = None
        self._done = False

        def worker():
            try:
                ctx = Context.make(lights=_default_lights(), dither=True, upt=TILE_SIZE)
                export_ride_to(ride, ctx, self._parkobj, self._work)
            except Exception:
                self._error = traceback.format_exc()
            finally:
                self._done = True

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

        wm = context.window_manager
        wm.progress_begin(0, 1)
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "TIMER" and self._done:
            return self._finish(context)
        return {"PASS_THROUGH"}

    def _finish(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        wm.progress_end()
        self._thread.join()
        if self._error:
            print(self._error)
            self.report({"ERROR"}, "Export failed; see the system console for details.")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {os.path.basename(self._parkobj)}")
        return {"FINISHED"}


_CLASSES = (VG_OT_test_render, VG_OT_export_parkobj)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
