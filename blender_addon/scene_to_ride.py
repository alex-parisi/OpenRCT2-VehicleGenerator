"""Read the Blender scene into the core renderer's data model.

This is the `bpy -> Mesh` adapter the plan calls for: instead of exporting OBJ
files, we pull geometry straight from scene objects and hand the core
`build_ride(config, meshes, preview)` an in-memory config dict + `Mesh` list.

Coordinate convention
----------------------
The renderer works in OBJ space (+X forward, +Y up, +Z passenger's right). The
repo's Blender build scripts place OBJ-space coords into Blender via
``loc(x, y, z) -> (x, -z, y)``. Inverting that, a Blender vertex ``(bx, by, bz)``
maps to OBJ ``(bx, bz, -by)``. As a basis matrix that is a proper rotation
(det = +1), so triangle winding is preserved.

Each contributing object bakes its world rotation+scale into the emitted mesh
and reports its world translation as the model entry's ``position`` — so a
static part sits where you placed it (orientation ``[0,0,0]``), and a restraint
pivots about the object's ORIGIN via per-frame orientation.
"""

from __future__ import annotations

import os

import bpy
import numpy as np
from mathutils import Matrix, Vector
from openrct2_vehicle_generator.constants import (
    MATERIAL_BACKGROUND_AA,
    MATERIAL_BACKGROUND_AA_DARK,
    MATERIAL_HAS_TEXTURE,
    MATERIAL_IS_FLAT_SHADED,
    MATERIAL_IS_MASK,
    MATERIAL_IS_REMAPPABLE,
    MATERIAL_IS_VISIBLE_MASK,
    MATERIAL_NO_AO,
    MATERIAL_NO_BLEED,
)
from openrct2_vehicle_generator.image import read_png
from openrct2_vehicle_generator.mesh import Material, Mesh, load_texture
from openrct2_vehicle_generator.types import IndexedImage

from . import props

# Blender (x, y, z) -> OBJ (x, z, -y).
_BASIS = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)))

_REGION_MAP = {
    "NONE": (0, 0),
    "REMAP1": (MATERIAL_IS_REMAPPABLE, 1),
    "REMAP2": (MATERIAL_IS_REMAPPABLE, 2),
    "REMAP3": (MATERIAL_IS_REMAPPABLE, 3),
    "GREYSCALE": (0, 4),
    "PEEP": (0, 5),
    "CHAIN": (0, 6),
}

_RESTRAINT_FRAMES = 4


class SceneError(Exception):
    """Raised when the scene can't be turned into a valid ride."""


def _material_from_bpy(bmat) -> Material:
    m = Material()
    if bmat is None:
        return m
    col = bmat.diffuse_color
    m.color = np.array([col[0], col[1], col[2]], dtype=np.float64)

    s = getattr(bmat, "vg_material", None)
    if s is None:
        return m

    flag, region = _REGION_MAP.get(s.region, (0, 0))
    m.flags |= flag
    m.region = region
    m.specular_exponent = float(s.specular_exponent)
    if s.is_visible_mask:
        m.flags |= MATERIAL_IS_VISIBLE_MASK
    elif s.is_mask:
        m.flags |= MATERIAL_IS_MASK
    if s.no_ao:
        m.flags |= MATERIAL_NO_AO
    if s.edge:
        m.flags |= MATERIAL_BACKGROUND_AA
    if s.dark_edge:
        m.flags |= MATERIAL_BACKGROUND_AA_DARK
    if s.no_bleed:
        m.flags |= MATERIAL_NO_BLEED
    if s.flat_shaded:
        m.flags |= MATERIAL_IS_FLAT_SHADED

    if s.texture is not None:
        path = bpy.path.abspath(s.texture.filepath_from_user() or s.texture.filepath)
        if path and os.path.exists(path):
            m.texture = load_texture(path)
            m.flags |= MATERIAL_HAS_TEXTURE
    return m


def _extract_mesh(obj, depsgraph) -> Mesh | None:
    """Evaluate `obj`, bake its world rotation+scale + basis change, -> Mesh."""
    eval_obj = obj.evaluated_get(depsgraph)
    me = eval_obj.to_mesh()
    try:
        me.calc_loop_triangles()
        tris = me.loop_triangles
        if len(tris) == 0:
            return None

        slots = [s.material for s in obj.material_slots]
        materials = [_material_from_bpy(bm) for bm in slots] or [Material()]
        n_mats = len(materials)

        linear = _BASIS @ obj.matrix_world.to_3x3()
        normal_mat = linear.inverted_safe().transposed()

        uv_layer = me.uv_layers.active
        verts: list[tuple[float, float, float]] = []
        norms: list[tuple[float, float, float]] = []
        uvs: list[tuple[float, float]] = []
        faces: list[tuple[int, int, int]] = []
        face_mats: list[int] = []

        for lt in tris:
            corner = []
            split_n = lt.split_normals
            for k in range(3):
                vidx = lt.vertices[k]
                loop_idx = lt.loops[k]
                co = linear @ me.vertices[vidx].co
                n = (normal_mat @ Vector(split_n[k])).normalized()
                uv = uv_layer.data[loop_idx].uv if uv_layer else (0.0, 0.0)
                verts.append((co.x, co.y, co.z))
                norms.append((n.x, n.y, n.z))
                uvs.append((uv[0], uv[1]))
                corner.append(len(verts) - 1)
            faces.append((corner[0], corner[1], corner[2]))
            face_mats.append(min(lt.material_index, n_mats - 1))

        return Mesh(
            vertices=np.array(verts, dtype=np.float32),
            normals=np.array(norms, dtype=np.float32),
            uvs=np.array(uvs, dtype=np.float32),
            faces=np.array(faces, dtype=np.uint32),
            face_materials=np.array(face_mats, dtype=np.uint32),
            materials=materials,
        )
    finally:
        eval_obj.to_mesh_clear()


def _object_position(obj) -> list[float]:
    p = _BASIS @ obj.matrix_world.to_translation()
    return [float(p.x), float(p.y), float(p.z)]


def _load_preview(image) -> IndexedImage | None:
    if image is None:
        return None
    path = bpy.path.abspath(image.filepath_from_user() or image.filepath)
    if not path or not os.path.exists(path):
        return None
    try:
        return read_png(path)
    except Exception:
        return None


# Slot identifier -> the key the loader expects inside `configuration`.
_SLOT_CONFIG_KEY = {
    "DEFAULT": "default",
    "FRONT": "front",
    "REAR": "rear",
}


def _build_vehicle(
    objects,
    *,
    mass: int,
    spacing: float,
    draw_order: int,
    effect_visual: int,
    vf_flags: list[str],
    meshes: list[Mesh],
    depsgraph,
    label: str,
) -> dict:
    """Build one ``vehicles[]`` entry from the given Blender objects.

    Appends extracted ``Mesh`` entries to ``meshes`` and returns the vehicle
    dict. Raises ``SceneError`` if no body/restraint objects are found.
    """
    body_entries: list[dict] = []
    rider_rows: dict[int, list[dict]] = {}
    has_restraint = False

    for obj in objects:
        if obj.type != "MESH":
            continue
        role = obj.vg_object.role
        if role == "IGNORE":
            continue
        mesh = _extract_mesh(obj, depsgraph)
        if mesh is None:
            continue
        idx = len(meshes)
        meshes.append(mesh)
        pos = _object_position(obj)

        if role == "BODY":
            body_entries.append({"mesh_index": idx, "position": pos, "orientation": [0, 0, 0]})
        elif role == "RESTRAINT":
            has_restraint = True
            swing = float(obj.vg_object.restraint_swing_deg)
            orient = [
                [0.0, -swing * f / (_RESTRAINT_FRAMES - 1), 0.0] for f in range(_RESTRAINT_FRAMES)
            ]
            body_entries.append({"mesh_index": idx, "position": pos, "orientation": orient})
        elif role == "RIDER":
            row = int(obj.vg_object.rider_row)
            rider_rows.setdefault(row, []).append(
                {"mesh_index": idx, "position": pos, "orientation": [0, 0, 0]}
            )

    if not body_entries:
        raise SceneError(
            f"{label}: no Body/Restraint objects found. "
            "Set object roles in the OpenRCT2 Vehicle panel."
        )

    flags = list(vf_flags)
    if has_restraint and "restraint_animation" not in flags:
        flags.append("restraint_animation")

    riders = [rider_rows[k] for k in sorted(rider_rows)]
    vehicle: dict = {
        "flags": flags,
        "mass": mass,
        "spacing": spacing,
        "draw_order": draw_order,
        "effect_visual": effect_visual,
        "model": body_entries,
    }
    if riders:
        vehicle["riders"] = riders
    return vehicle


def build_config_and_meshes(context):
    """Return (config_dict, meshes, preview) read from the active scene.

    Raises SceneError with a user-facing message on invalid scenes.
    """
    scene = context.scene
    rs = scene.vg_ride
    depsgraph = context.evaluated_depsgraph_get()

    meshes: list[Mesh] = []
    vehicles: list[dict] = []
    configuration: dict[str, int] = {}

    assigned_types = [ct for ct in rs.car_types if ct.slot != "NONE"]
    if rs.car_types and not assigned_types:
        raise SceneError("No car type has a slot assigned. Set at least one to 'Default'.")

    if assigned_types:
        for ct in assigned_types:
            if ct.collection is None:
                raise SceneError(f"Car type '{ct.name}' has no Collection assigned.")
            vehicle = _build_vehicle(
                ct.collection.all_objects,
                mass=int(ct.mass),
                spacing=float(ct.spacing),
                draw_order=int(ct.draw_order),
                effect_visual=int(ct.effect_visual),
                vf_flags=[n for attr, n in props.flag_items("vf_") if getattr(ct, attr)],
                meshes=meshes,
                depsgraph=depsgraph,
                label=f"Car type '{ct.name}'",
            )
            configuration[_SLOT_CONFIG_KEY[ct.slot]] = len(vehicles)
            vehicles.append(vehicle)
        if "default" not in configuration:
            raise SceneError("Need a car type assigned to the 'Default' slot.")
    else:
        # Back-compat: no car types -> whole scene is the default car with built-in defaults.
        vehicle = _build_vehicle(
            scene.objects,
            mass=100,
            spacing=2.0,
            draw_order=1,
            effect_visual=1,
            vf_flags=[],
            meshes=meshes,
            depsgraph=depsgraph,
            label="Scene",
        )
        vehicles.append(vehicle)
        configuration["default"] = 0

    if rs.sprites_all:
        sprites: object = "all"
    else:
        chosen = [n for attr, n in props.flag_items("sg_") if getattr(rs, attr)]
        sprites = chosen if chosen else ["flat"]

    authors = [a.strip() for a in rs.authors.split(",") if a.strip()]

    config = {
        "id": rs.id,
        "name": rs.name,
        "description": rs.description,
        "capacity": rs.capacity,
        "authors": authors,
        "version": rs.version,
        "ride_type": rs.ride_type,
        "sprites": sprites,
        "flags": [n for attr, n in props.flag_items("rf_") if getattr(rs, attr)],
        "running_sound": rs.running_sound,
        "secondary_sound": rs.secondary_sound,
        "min_cars_per_train": int(rs.min_cars),
        "max_cars_per_train": int(rs.max_cars),
        "build_menu_priority": int(rs.build_menu_priority),
        "default_colors": [[p.main, p.secondary, p.tertiary] for p in rs.color_presets]
        or [["bright_red", "black", "grey"]],
        "configuration": configuration,
        "vehicles": vehicles,
    }

    return config, meshes, _load_preview(rs.preview)
