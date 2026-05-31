"""Read the Blender scene into the scenery generator's config + meshes.

The `bpy -> Mesh` adapter for scenery: instead of OBJ files, pull geometry
straight from scene objects and hand the core `build_small_scenery` /
`build_large_scenery` an in-memory config dict + `Mesh` list (same shape the
YAML loader produces).

Coordinate convention matches the renderer / vehicle add-on: OBJ space is
+X forward, +Y up, +Z right; a Blender vertex (bx, by, bz) maps to OBJ
(bx, bz, -by). 1 tile = TILE_SIZE OBJ units.
"""

from __future__ import annotations

import os

import bpy
import numpy as np
from mathutils import Matrix, Vector
from openrct2_iso_core.constants import (
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
from openrct2_iso_core.image import quantize_to_indexed, read_png
from openrct2_iso_core.mesh import Material, Mesh, load_texture
from openrct2_iso_core.types import IndexedImage

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


class SceneError(Exception):
    """Raised when the scene can't be turned into a valid scenery object."""


def _material_from_bpy(bmat) -> Material:
    m = Material()
    if bmat is None:
        return m
    col = bmat.diffuse_color
    m.color = np.array([col[0], col[1], col[2]], dtype=np.float64)

    s = getattr(bmat, "vgs_material", None)
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


def _load_preview(filepath) -> IndexedImage | None:
    if not filepath:
        return None
    path = bpy.path.abspath(filepath)
    if not path or not os.path.exists(path):
        return None
    try:
        return read_png(path)
    except Exception:
        pass
    try:
        return quantize_to_indexed(path)
    except Exception:
        return None


def build_config_and_meshes(context):
    """Return (config_dict, meshes, preview) read from the active scene.

    Raises SceneError with a user-facing message on invalid scenes.
    """
    scene = context.scene
    ss = scene.vgs_scenery
    depsgraph = context.evaluated_depsgraph_get()

    meshes: list[Mesh] = []
    model: list[dict] = []
    for obj in scene.objects:
        if obj.type != "MESH":
            continue
        if obj.vgs_object.role == "IGNORE":
            continue
        mesh = _extract_mesh(obj, depsgraph)
        if mesh is None:
            continue
        idx = len(meshes)
        meshes.append(mesh)
        model.append({
            "mesh_index": idx,
            "position": _object_position(obj),
            "orientation": [0, 0, 0],
        })

    if not model:
        raise SceneError(
            "No geometry found. Add a mesh and set its role to 'Geometry' "
            "in the OpenRCT2 Scenery panel."
        )

    authors = [a.strip() for a in ss.authors.split(",") if a.strip()]

    config: dict = {
        "object_type": ss.object_type,
        "id": ss.id,
        "name": ss.name,
        "authors": authors,
        "version": ss.version,
        "price": ss.price,
        "removal_price": ss.removal_price,
        "cursor": ss.cursor,
        "scenery_group": ss.scenery_group,
        "has_primary_colour": ss.has_primary_colour,
        "has_secondary_colour": ss.has_secondary_colour,
        "model": model,
    }

    if ss.object_type == "scenery_small":
        config.update({
            "height": int(ss.height),
            "shape": ss.shape,
            "is_rotatable": ss.is_rotatable,
            "is_stackable": ss.is_stackable,
            "requires_flat_surface": ss.requires_flat_surface,
            "prohibit_walls": ss.prohibit_walls,
            "is_tree": ss.is_tree,
        })
    else:  # scenery_large
        if not ss.tiles:
            raise SceneError(
                "Large scenery needs at least one tile. Add one in the Tiles list."
            )
        config.update({
            "has_tertiary_colour": ss.has_tertiary_colour,
            "is_photogenic": ss.is_photogenic,
            "scrolling_mode": int(ss.scrolling_mode),
            "tiles": [
                {"x": int(t.x), "y": int(t.y), "z": int(t.z), "clearance": int(t.clearance)}
                for t in ss.tiles
            ],
        })

    return config, meshes, _load_preview(ss.preview)
