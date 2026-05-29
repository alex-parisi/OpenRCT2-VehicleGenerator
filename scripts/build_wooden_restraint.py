#!/usr/bin/env python3
"""Generate a wooden coaster lap bar as restraint.obj.

A U-shaped tubular lap bar with its origin at the pivot end (forward end
when closed): two side arms run back from the pivot over the riders'
laps, joined by a cylindrical crossbar at the free end. The same mesh
is instantiated twice in classic_wooden.yaml (once per row of riders),
with restraint_animation rotating it around the Z axis from horizontal
(closed) to vertical (open).

Run headless:
    blender --background --python scripts/build_wooden_restraint.py

Output: examples/wooden/restraint.obj
"""

import math
import os

import bpy

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH  = os.path.join(REPO_ROOT, "examples", "wooden", "restraint.obj")

# Dimensions (OBJ coords; pivot is at the bar's front-bottom corner)
BAR_LEN    = 0.42         # reach back from pivot (along -X when closed)
BAR_WIDTH  = 1.25         # crossbar length (along Z, across the car)
BAR_RADIUS = 0.045        # tube radius (shared by crossbar and side arms)

POST_THICK = 0.06         # side-post cross-section
POST_DROP  = 0.08         # how far the side posts hang below the bar (Y)

def loc(x, y, z):  return (x, -z, y)
def scl(dx, dy, dz): return (dx, dz, dy)

def clear_scene():
    if bpy.context.scene.objects:
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.curves):
        for item in list(coll):
            coll.remove(item)

def material(name):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
    return m

def add_box(name, center, size, material_name):
    cx, cy, cz = center
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc(cx, cy, cz))
    o = bpy.context.active_object
    o.name = name
    sx, sy, sz = scl(*size)
    o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(material(material_name))
    return o

def add_cylinder(name, center, axis, length, radius, material_name, segs=16):
    """Centered at OBJ-space `center`; `axis` is 'x', 'y', or 'z' in OBJ space."""
    cx, cy, cz = center
    # Cylinder's default axis is Blender Z (= OBJ Y); rotate to point along
    # OBJ X (90° about Blender Y) or OBJ Z (90° about Blender X).
    rot = {
        "x": (0.0, math.radians(90), 0.0),
        "y": (0.0, 0.0, 0.0),
        "z": (math.radians(90), 0.0, 0.0),
    }[axis]
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=segs, radius=radius, depth=length,
        location=loc(cx, cy, cz),
        rotation=rot,
    )
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(material(material_name))
    return o

def build_bar():
    # Pivot is at the bar's FORWARD-bottom edge (+X side, since +X = direction
    # of travel). When closed, the U-shape extends backward (-X) over the
    # laps. Rotation around Z swings the free end up to vertical.

    # Crossbar tube: spans the car width at the bar's free end (-X side),
    # sitting over the riders' laps when closed.
    add_cylinder(
        "Lap_Bar_Crossbar",
        center=(-BAR_LEN, BAR_RADIUS, 0.0),
        axis="z",
        length=BAR_WIDTH,
        radius=BAR_RADIUS,
        material_name="ShinyMetal_Edge",
    )
    # Two side arms from pivot back to the crossbar ends.
    for z_sign in (-1, +1):
        add_cylinder(
            f"Lap_Bar_Arm_{'L' if z_sign < 0 else 'R'}",
            center=(-BAR_LEN / 2,
                    BAR_RADIUS,
                    z_sign * (BAR_WIDTH / 2 - BAR_RADIUS)),
            axis="x",
            length=BAR_LEN,
            radius=BAR_RADIUS,
            material_name="ShinyMetal_Edge",
        )
    # Two short side posts hanging just inside the pivot end.
    for z_sign in (-1, +1):
        add_box(
            f"Lap_Bar_Post_{'L' if z_sign < 0 else 'R'}",
            center=(-POST_THICK / 2,
                    -POST_DROP / 2,
                    z_sign * (BAR_WIDTH / 2 - POST_THICK / 2)),
            size=(POST_THICK, POST_DROP, POST_THICK),
            material_name="ShinyMetal_Edge",
        )

def export_obj():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.wm.obj_export(
        filepath=OUT_PATH,
        export_selected_objects=True,
        export_materials=True,
        export_triangulated_mesh=True,
        export_normals=True,
        export_uv=False,
        path_mode="RELATIVE",
    )

def post_process_obj():
    with open(OUT_PATH) as f:
        lines = f.readlines()
    saw_mtllib = False
    fixed = []
    for line in lines:
        if line.startswith("mtllib "):
            fixed.append("mtllib materials.mtl\n")
            saw_mtllib = True
        else:
            fixed.append(line)
    if not saw_mtllib:
        fixed.insert(0, "mtllib materials.mtl\n")
    with open(OUT_PATH, "w") as f:
        f.writelines(fixed)
    sidecar = OUT_PATH[:-4] + ".mtl"
    if os.path.exists(sidecar):
        os.remove(sidecar)

def main():
    clear_scene()
    build_bar()
    export_obj()
    post_process_obj()
    print(f"[build_wooden_restraint] wrote {OUT_PATH}")

if __name__ == "__main__":
    main()
