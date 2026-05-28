#!/usr/bin/env python3
"""Generate a wooden coaster chassis + wheel trucks as an OpenRCT2 OBJ.

Run headless:
    blender --background --python scripts/build_wooden_car.py

Or in Blender's Scripting workspace:
    exec(open("scripts/build_wooden_car.py").read())

Writes examples/wooden/car.obj. The .obj references the hand-authored
examples/wooden/materials.mtl by name (the Blender-generated companion
.mtl is discarded).

Coordinate convention (matches the existing examples/wooden/car.obj):
    +X = travel axis (front of car at -X, rear at +X)
    +Y = up
    +Z = passenger's right (looking forward)

Blender's default OBJ exporter (forward=-Z, up=Y) maps:
    Blender X -> OBJ  X
    Blender Y -> OBJ -Z
    Blender Z -> OBJ  Y
so we build in Blender at  (x_obj, -z_obj, y_obj).
"""

import math
import os
import sys

import bpy

# --- Output path -----------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH  = os.path.join(REPO_ROOT, "examples", "wooden", "car.obj")

# --- Dimensions (OBJ space, units ~= meters) -------------------------------

# Uniform scale applied to the whole car at export (about the origin).
SCALE = 0.80

# Chassis floor plate
CHASSIS_LEN   = 1.85                  # +X = direction of travel (front of car)
CHASSIS_WIDTH = 1.50
CHASSIS_THICK = 0.08
CHASSIS_Y     = 0.26                  # bottom-of-floor (raised to clear bigger wheels)

# Two longitudinal underframe rails
RAIL_W = 0.07
RAIL_H = 0.07
RAIL_Z = 0.60                         # ± offset from centerline

# Front + rear bumper plate
BUMPER_LEN   = 0.07
BUMPER_WIDTH = CHASSIS_WIDTH * 0.55
BUMPER_THICK = CHASSIS_THICK + 0.06

# Wheel trucks (two: front at +TRUCK_X (forward), rear at -TRUCK_X)
TRUCK_X        = 0.65
AXLE_SPACING   = 0.28                 # between front & rear axle of one truck
BOLSTER_HEIGHT = 0.08
BOLSTER_WIDTH  = CHASSIS_WIDTH - 0.04

WHEEL_R  = 0.12
WHEEL_W  = 0.07                       # thickness along Z
WHEEL_Z  = CHASSIS_WIDTH / 2 + WHEEL_W / 2    # just outside chassis edge

# Body (sides, end caps, bench seats)
CHASSIS_TOP      = CHASSIS_Y + CHASSIS_THICK   # y = 0.34, where the body sits

SIDE_THICK       = 0.06
SIDE_Z           = CHASSIS_WIDTH / 2 - SIDE_THICK / 2   # inset slightly from edge
SIDE_LEN         = 1.73                                  # leaves room for end caps
SIDE_HEIGHT      = 0.60                                  # 0.34 -> 0.94

END_THICK        = 0.07
END_HEIGHT       = SIDE_HEIGHT

# Bench cushions: 2 rows, 2-across each. +X is forward, so the front row
# of riders is at +FRONT_BENCH_X (the front of the car).
BENCH_DEPTH      = 0.50                # along X (per row)
BENCH_HEIGHT     = 0.20                # cushion thickness
BENCH_WIDTH      = CHASSIS_WIDTH - 2 * SIDE_THICK - 0.04   # fits between side walls
FRONT_BENCH_X    = +0.40               # center of front-row cushion (forward in +X)
BACK_BENCH_X     = -0.35               # center of back-row cushion (behind front row)

# Seat backs go BEHIND each row, i.e. at lower X than the row's cushion.
SEAT_BACK_THICK  = 0.07
SEAT_BACK_HEIGHT = 0.95                # rises this far above chassis top
FRONT_BACK_X     = FRONT_BENCH_X - BENCH_DEPTH / 2 - SEAT_BACK_THICK / 2   # divider between rows
REAR_BACK_X      = BACK_BENCH_X  - BENCH_DEPTH / 2 - SEAT_BACK_THICK / 2   # trailing seat back (rear of car)

# --- Coordinate helpers ----------------------------------------------------

def loc(x, y, z):
    """OBJ position -> Blender location."""
    return (x * SCALE, -z * SCALE, y * SCALE)

def scl(dx, dy, dz):
    """OBJ box dimensions -> Blender (x,y,z) extents."""
    return (dx * SCALE, dz * SCALE, dy * SCALE)

# --- Scene setup -----------------------------------------------------------

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

# --- Primitives ------------------------------------------------------------

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

def add_wheel(name, center, material_name, radius=WHEEL_R, width=WHEEL_W, segs=16):
    cx, cy, cz = center
    # Default cylinder axis is Blender Z; rotate 90° about X to align with Blender Y
    # (= OBJ Z). Cylinders are symmetric so direction is irrelevant.
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=segs, radius=radius * SCALE, depth=width * SCALE,
        location=loc(cx, cy, cz),
        rotation=(math.radians(90), 0, 0),
    )
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(material(material_name))
    return o

# --- Build pieces ----------------------------------------------------------

def build_chassis():
    # Floor plate (player-recolorable body color)
    add_box(
        "Chassis_Floor",
        center=(0.0, CHASSIS_Y + CHASSIS_THICK / 2, 0.0),
        size=(CHASSIS_LEN, CHASSIS_THICK, CHASSIS_WIDTH),
        material_name="Remap1",
    )

    # Two longitudinal frame rails beneath the floor
    for z_sign in (-1, +1):
        add_box(
            f"Chassis_Rail_{'L' if z_sign < 0 else 'R'}",
            center=(0.0, CHASSIS_Y - RAIL_H / 2, z_sign * RAIL_Z),
            size=(CHASSIS_LEN, RAIL_H, RAIL_W),
            material_name="Metal",
        )

    # Front + rear bumper plates
    for x_sign in (-1, +1):
        add_box(
            f"Bumper_{'F' if x_sign < 0 else 'R'}",
            center=(x_sign * (CHASSIS_LEN / 2 + BUMPER_LEN / 2),
                    CHASSIS_Y + CHASSIS_THICK / 2, 0.0),
            size=(BUMPER_LEN, BUMPER_THICK, BUMPER_WIDTH),
            material_name="Metal",
        )

def build_truck(name, center_x):
    # Bolster: structural cross-beam the chassis rests on
    add_box(
        f"Truck_{name}_Bolster",
        center=(center_x, WHEEL_R, 0.0),
        size=(AXLE_SPACING + 0.05, BOLSTER_HEIGHT, BOLSTER_WIDTH),
        material_name="Metal",
    )
    # Four road wheels: 2 axles x 2 sides
    for ai, dx in enumerate((-AXLE_SPACING / 2, +AXLE_SPACING / 2)):
        for sd, dz in (("L", -WHEEL_Z), ("R", +WHEEL_Z)):
            add_wheel(
                f"Wheel_{name}_{ai}_{sd}",
                center=(center_x + dx, WHEEL_R, dz),
                material_name="Wheel",
            )

def build_trucks():
    build_truck("F", -TRUCK_X)
    build_truck("R", +TRUCK_X)

def build_body():
    # Side walls (plank-style, hip-height)
    for z_sign in (-1, +1):
        add_box(
            f"Body_Side_{'L' if z_sign < 0 else 'R'}",
            center=(0.0,
                    CHASSIS_TOP + SIDE_HEIGHT / 2,
                    z_sign * SIDE_Z),
            size=(SIDE_LEN, SIDE_HEIGHT, SIDE_THICK),
            material_name="Remap1",
        )

    # Front + rear end caps (close off the body box)
    for x_sign in (-1, +1):
        end_x = x_sign * (SIDE_LEN / 2 - END_THICK / 2)
        add_box(
            f"Body_End_{'F' if x_sign < 0 else 'R'}",
            center=(end_x,
                    CHASSIS_TOP + END_HEIGHT / 2,
                    0.0),
            size=(END_THICK, END_HEIGHT, CHASSIS_WIDTH - 2 * SIDE_THICK),
            material_name="Remap1",
        )

def build_seats():
    # Two bench cushions (front + back row)
    for label, cx in (("Front", FRONT_BENCH_X), ("Back", BACK_BENCH_X)):
        add_box(
            f"Bench_{label}_Cushion",
            center=(cx,
                    CHASSIS_TOP + BENCH_HEIGHT / 2,
                    0.0),
            size=(BENCH_DEPTH, BENCH_HEIGHT, BENCH_WIDTH),
            material_name="Seat",
        )

    # Two seat backs (divider between rows, and trailing back-row back)
    for label, bx in (("Front", FRONT_BACK_X), ("Rear", REAR_BACK_X)):
        add_box(
            f"Seat_Back_{label}",
            center=(bx,
                    CHASSIS_TOP + SEAT_BACK_HEIGHT / 2,
                    0.0),
            size=(SEAT_BACK_THICK, SEAT_BACK_HEIGHT, BENCH_WIDTH),
            material_name="Remap1",
        )

# --- Export ----------------------------------------------------------------

def export_obj():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.wm.obj_export(
        filepath=OUT_PATH,
        export_selected_objects=True,
        export_materials=True,            # generates a sidecar .mtl we then delete
        export_triangulated_mesh=True,
        export_normals=True,
        export_uv=False,
        path_mode="RELATIVE",
    )

def post_process_obj():
    """Force mtllib -> materials.mtl, drop the auto-generated sidecar."""
    with open(OUT_PATH, "r") as f:
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

# --- Main ------------------------------------------------------------------

def main():
    clear_scene()
    build_chassis()
    build_trucks()
    build_body()
    build_seats()
    export_obj()
    post_process_obj()
    print(f"[build_wooden_car] wrote {OUT_PATH}")

if __name__ == "__main__":
    main()
