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

import math
import os
import tempfile

import bpy
import numpy as np
from mathutils import Matrix, Vector
from openrct2_iso_core.image import quantize_to_indexed, read_png
from openrct2_iso_core.mesh import Material, Mesh, load_texture
from openrct2_iso_core.types import IndexedImage
from openrct2_vehicle_generator.constants import (
    MATERIAL_BACKGROUND_AA,
    MATERIAL_BACKGROUND_AA_DARK,
    MATERIAL_HAS_TEXTURE,
    MATERIAL_IS_MASK,
    MATERIAL_IS_REMAPPABLE,
    MATERIAL_NO_AO,
    MATERIAL_NO_BLEED,
)

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
}

_RESTRAINT_FRAMES = 4


class SceneError(Exception):
    """Raised when the scene can't be turned into a valid ride."""


def _base_color(bmat) -> tuple[float, float, float]:
    """The material's flat RGB colour.

    Prefer the Principled BSDF ``Base Color`` (what users actually set in the
    shader editor) and fall back to ``diffuse_color`` (the viewport display
    colour). ``diffuse_color`` alone is wrong for almost every authored
    material: it stays at Blender's default 0.8 grey unless explicitly touched,
    so reading it made every untextured material render the same grey. If the
    Base Color input is textured (linked), there's no flat value to read, so we
    fall back to the viewport colour as well.
    """
    if getattr(bmat, "use_nodes", False) and bmat.node_tree is not None:
        for node in bmat.node_tree.nodes:
            if node.type != "BSDF_PRINCIPLED":
                continue
            base = node.inputs.get("Base Color")
            if base is not None and not base.is_linked:
                c = base.default_value
                return (c[0], c[1], c[2])
    col = bmat.diffuse_color
    return (col[0], col[1], col[2])


def _base_color_image(bmat):
    """The image feeding the Principled BSDF ``Base Color``, if that input is
    directly linked to an Image Texture node; otherwise ``None``.

    Lets users paint a material with a texture node in the shader editor
    instead of having to also fill in the add-on's explicit Texture pointer.
    Only a direct ``Base Color <- Image Texture`` link is followed (no chains
    through colour-mix nodes) to keep the behaviour predictable.
    """
    if not (getattr(bmat, "use_nodes", False) and bmat.node_tree is not None):
        return None
    for node in bmat.node_tree.nodes:
        if node.type != "BSDF_PRINCIPLED":
            continue
        base = node.inputs.get("Base Color")
        if base is None or not base.is_linked:
            return None
        from_node = base.links[0].from_node
        if from_node.type == "TEX_IMAGE":
            return from_node.image
    return None


def _load_packed_image(img):
    """Materialise a packed or generated image (no usable file on disk) to a
    temp PNG and load it through the normal texture pipeline, so colour
    handling matches on-disk images. Returns `None` if it can't be saved."""
    tmp_dir = tempfile.mkdtemp(prefix="vg_tex_")
    tmp = os.path.join(tmp_dir, "packed.png")
    prev_format = img.file_format
    try:
        img.file_format = "PNG"
        img.save(filepath=tmp)
        return load_texture(tmp)
    except (RuntimeError, OSError):
        return None
    finally:
        img.file_format = prev_format
        try:
            os.remove(tmp)
            os.rmdir(tmp_dir)
        except OSError:
            pass


def _load_bpy_image(img):
    """Load a `bpy.types.Image` into a core `Texture`, or `None` if it has no
    usable pixels. On-disk files load directly; packed/generated images are
    materialised to a temp PNG first."""
    if img is None:
        return None
    path = bpy.path.abspath(img.filepath_from_user() or img.filepath)
    if path and os.path.exists(path):
        return load_texture(path)
    if img.packed_file is not None or img.source == "GENERATED" or img.has_data:
        return _load_packed_image(img)
    return None


def _material_from_bpy(bmat) -> Material:
    m = Material()
    if bmat is None:
        return m
    s = getattr(bmat, "vg_material", None)

    # Diffuse colour: the add-on's explicit picker wins; otherwise fall back to
    # the Principled BSDF Base Color
    # Specular is driven entirely by the add-on's controls
    if s is not None and s.use_color_override:
        m.color = np.array(tuple(s.diffuse_color), dtype=np.float64)
    else:
        m.color = np.array(_base_color(bmat), dtype=np.float64)

    intensity = float(s.specular_intensity) if s is not None else 0.5
    m.specular_exponent = float(s.specular_exponent) if s is not None else 50.0
    tint = tuple(s.specular_tint) if (s is not None and s.use_specular_tint) else (1.0, 1.0, 1.0)
    m.specular_color = np.array(tint, dtype=np.float64) * intensity

    if s is None:
        return m

    flag, region = _REGION_MAP.get(s.region, (0, 0))
    m.flags |= flag
    m.region = region
    if s.is_mask:
        m.flags |= MATERIAL_IS_MASK
    if s.no_ao:
        m.flags |= MATERIAL_NO_AO
    if s.edge:
        m.flags |= MATERIAL_BACKGROUND_AA
    if s.dark_edge:
        m.flags |= MATERIAL_BACKGROUND_AA_DARK
    if s.no_bleed:
        m.flags |= MATERIAL_NO_BLEED

    # The explicit Texture pointer wins; otherwise fall back to an image
    # texture wired into the Principled BSDF's Base Color.
    tex_image = s.texture if s.texture is not None else _base_color_image(bmat)
    texture = _load_bpy_image(tex_image)
    if texture is not None:
        m.texture = texture
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


def _apply_offset(position, offset):
    """Subtract an OBJ-space ``offset`` from a model entry's ``position``.

    ``position`` is either a single ``[x, y, z]`` (static parts, riders) or a
    per-frame list of them (animated restraints); both shapes are handled so a
    collection moved aside in the viewport renders as if it sat at the origin.
    """
    ox, oy, oz = offset
    if position and isinstance(position[0], (list, tuple)):
        return [[p[0] - ox, p[1] - oy, p[2] - oz] for p in position]
    return [position[0] - ox, position[1] - oy, position[2] - oz]


def _sample_keyframed_transform(
    obj, scene, num_frames: int
) -> tuple[Mesh | None, list[list[float]], list[list[float]]]:
    """Sample obj's transform across `num_frames` evenly-spaced scene frames.

    Returns ``(rest_mesh, positions, orientations)``. The mesh is re-extracted
    at the rest frame so its baked world rotation lines up with the
    orientation ``[0, 0, 0]`` emitted for frame 0; subsequent orientations are
    deltas from rest, mapped into the renderer's OBJ-space YZX convention.
    The scene frame is restored on exit so the user's Blender state is
    unchanged.

    Currently called only for restraint animation (4 frames), but the helper
    is intentionally generic — animated vehicle bodies, oars, and rigged
    peeps want the same per-frame sampling with a different frame count.
    """
    vg = obj.vg_object
    f_start = int(vg.anim_start_frame)
    f_end = int(vg.anim_end_frame)
    if f_end == f_start:
        frames = [f_start] * num_frames
    else:
        frames = [
            f_start + round(i * (f_end - f_start) / (num_frames - 1))
            for i in range(num_frames)
        ]

    orig_frame = scene.frame_current
    try:
        scene.frame_set(frames[0])
        dg = bpy.context.evaluated_depsgraph_get()
        rest_mesh = _extract_mesh(obj, dg)
        R_rest_inv = obj.evaluated_get(dg).matrix_world.to_3x3().inverted()

        positions: list[list[float]] = []
        orientations: list[list[float]] = []
        for f in frames:
            scene.frame_set(f)
            dg = bpy.context.evaluated_depsgraph_get()
            M_f = obj.evaluated_get(dg).matrix_world

            p = _BASIS @ M_f.to_translation()
            positions.append([float(p.x), float(p.y), float(p.z)])

            R_rel = M_f.to_3x3() @ R_rest_inv
            R_obj = _BASIS @ R_rel @ _BASIS.transposed()
            # Renderer applies rotate_y(a) @ rotate_z(b) @ rotate_x(c).
            # Blender's "YZX" Euler reconstructs as Ry(e.y) @ Rz(e.z) @ Rx(e.x),
            # so emit angles in that order.
            e = R_obj.to_euler("YZX")
            orientations.append([
                float(math.degrees(e.y)),
                float(math.degrees(e.z)),
                float(math.degrees(e.x)),
            ])
    finally:
        scene.frame_set(orig_frame)

    return rest_mesh, positions, orientations


def _load_preview(filepath) -> IndexedImage | None:
    if not filepath:
        return None
    path = bpy.path.abspath(filepath)
    if not path or not os.path.exists(path):
        return None
    # An already-paletted RCT2 PNG is used verbatim (indices are RCT2 indices);
    # anything else (RGB/JPEG/oversized) is resized and quantized to the palette.
    try:
        return read_png(path)
    except Exception:
        pass
    try:
        return quantize_to_indexed(path)
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
    scene,
    depsgraph,
    label: str,
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> dict:
    """Build one ``vehicles[]`` entry from the given Blender objects.

    Appends extracted ``Mesh`` entries to ``meshes`` and returns the vehicle
    dict. ``offset`` is an OBJ-space translation subtracted from every model
    position, compensating for a collection moved aside in the viewport so its
    car still renders centred. Raises ``SceneError`` if no body/restraint
    objects are found.
    """
    body_entries: list[dict] = []
    rider_entries: list[tuple[int, str, dict]] = []
    has_restraint = False

    for obj in objects:
        if obj.type != "MESH":
            continue
        role = obj.vg_object.role
        if role == "IGNORE":
            continue

        is_keyframed_restraint = (
            role == "RESTRAINT"
            and obj.animation_data is not None
            and obj.animation_data.action is not None
        )

        if is_keyframed_restraint:
            mesh, kf_positions, kf_orientations = _sample_keyframed_transform(
                obj, scene, _RESTRAINT_FRAMES
            )
        else:
            mesh = _extract_mesh(obj, depsgraph)
        if mesh is None:
            continue
        idx = len(meshes)
        meshes.append(mesh)

        if role == "BODY":
            pos = _object_position(obj)
            body_entries.append({"mesh_index": idx, "position": pos, "orientation": [0, 0, 0]})
        elif role == "RESTRAINT":
            has_restraint = True
            if is_keyframed_restraint:
                body_entries.append({
                    "mesh_index": idx,
                    "position": kf_positions,
                    "orientation": kf_orientations,
                })
            else:
                pos = _object_position(obj)
                swing = float(obj.vg_object.restraint_swing_deg)
                orient = [
                    [0.0, -swing * f / (_RESTRAINT_FRAMES - 1), 0.0]
                    for f in range(_RESTRAINT_FRAMES)
                ]
                body_entries.append({"mesh_index": idx, "position": pos, "orientation": orient})
        elif role == "RIDER":
            pos = _object_position(obj)
            rider_entries.append((
                int(obj.vg_object.rider_number),
                obj.name,
                {"mesh_index": idx, "position": pos, "orientation": [0, 0, 0]},
            ))

    if not body_entries:
        raise SceneError(
            f"{label}: no Body/Restraint objects found. "
            "Set object roles in the OpenRCT2 Vehicle panel."
        )

    if offset != (0.0, 0.0, 0.0):
        for entry in body_entries:
            entry["position"] = _apply_offset(entry["position"], offset)
        for _, _, entry in rider_entries:
            entry["position"] = _apply_offset(entry["position"], offset)

    flags = list(vf_flags)
    if has_restraint and "restraint_animation" not in flags:
        flags.append("restraint_animation")

    # Peeps are sorted by Rider Number, then chunked into consecutive pairs:
    # numbers 0+1 form the first row, 2+3 the second, etc. A trailing unpaired
    # peep becomes a 1-peep row. Object name is a stable tiebreaker if two
    # peeps share a number.
    rider_entries.sort(key=lambda e: (e[0], e[1]))
    riders = [
        [e[2] for e in rider_entries[i : i + 2]] for i in range(0, len(rider_entries), 2)
    ]

    # Auto-assign remap regions by the peep's position within its seat row:
    # the first peep (left) -> remap1, the second (right) -> remap2. This only
    # rewrites materials the user already marked remappable (skin/hair/shoes are
    # untouched), so authoring one generic remappable peep material is enough.
    for row in riders:
        for pos, entry in enumerate(row):
            region = 1 if pos == 0 else 2
            for mat in meshes[entry["mesh_index"]].materials:
                if mat.flags & MATERIAL_IS_REMAPPABLE and mat.region != 3:
                    mat.region = region
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

    preview_tab_car = 0
    if assigned_types:
        for ct in assigned_types:
            if ct.collection is None:
                raise SceneError(f"Car type '{ct.name}' has no Collection assigned.")
            off = _BASIS @ Vector(tuple(ct.offset))
            vehicle = _build_vehicle(
                ct.collection.all_objects,
                mass=int(ct.mass),
                spacing=float(ct.spacing),
                draw_order=int(ct.draw_order),
                effect_visual=int(ct.effect_visual),
                vf_flags=[n for attr, n in props.flag_items("vf_") if getattr(ct, attr)],
                meshes=meshes,
                scene=scene,
                depsgraph=depsgraph,
                label=f"Car type '{ct.name}'",
                offset=(float(off.x), float(off.y), float(off.z)),
            )
            idx = len(vehicles)
            configuration[_SLOT_CONFIG_KEY[ct.slot]] = idx
            if ct.preview_tab:
                preview_tab_car = idx
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
            scene=scene,
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
        "original_id": rs.original_id,
        "preview_tab_car": preview_tab_car,
        "name": rs.name,
        "description": rs.description,
        "capacity": rs.capacity,
        "authors": authors,
        "version": rs.version,
        "ride_type": rs.ride_type,
        "units_per_tile": float(rs.units_per_tile),
        "sprites": sprites,
        "flags": [n for attr, n in props.flag_items("rf_") if getattr(rs, attr)],
        "running_sound": rs.running_sound,
        "secondary_sound": rs.secondary_sound,
        "min_cars_per_train": int(rs.min_cars),
        "max_cars_per_train": int(rs.max_cars),
        "zero_cars": int(rs.zero_cars),
        "build_menu_priority": int(rs.build_menu_priority),
        "default_colors": [[p.main, p.secondary, p.tertiary] for p in rs.color_presets]
        or [["bright_red", "black", "grey"]],
        "configuration": configuration,
        "vehicles": vehicles,
    }

    return config, meshes, _load_preview(rs.preview)
