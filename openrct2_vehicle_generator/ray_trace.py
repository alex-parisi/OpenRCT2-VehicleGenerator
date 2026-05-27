"""NumPy ray tracer + rendering pipeline.

Replaces both src/iso-render/RayTrace.cpp (Embree) and
src/iso-render/Renderer.cpp. Functionally equivalent (not byte-exact):

  - Vectorized Moller-Trumbore intersection across the whole triangle
    set (no BVH yet -- can be added if performance is unworkable).
  - 4x4 AA subsamples per pixel; 8x4 AO hemisphere samples.
  - Background-AA edge detection / weighted blending logic mirrors
    Renderer.cpp `render_row`.
  - Floyd-Steinberg dithering to the RCT2 palette.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .constants import (
    AA_NUM_SAMPLES_U,
    AA_NUM_SAMPLES_V,
    AO_NUM_SAMPLES_U,
    AO_NUM_SAMPLES_V,
    FRAGMENT_UNUSED,
    LIGHT_DIFFUSE,
    LIGHT_HEMI,
    MATERIAL_BACKGROUND_AA,
    MATERIAL_BACKGROUND_AA_DARK,
    MATERIAL_HAS_TEXTURE,
    MATERIAL_IS_FLAT_SHADED,
    MATERIAL_IS_MASK,
    MATERIAL_IS_REMAPPABLE,
    MATERIAL_IS_VISIBLE_MASK,
    MATERIAL_NO_AO,
    MATERIAL_NO_BLEED,
    MESH_GHOST,
    MESH_MASK,
    REGION_MASK,
    TILE_SIZE,
)
from .mesh import Mesh, Texture, texture_sample
from .palette import PALETTE_LINEAR, color_from_vector, palette_get_nearest, vector_from_color
from .types import IndexedImage, Light


SQRT_2 = 1.4142135623731
SQRT_3 = 1.73205080757
SQRT_6 = 2.44948974278


# Four-corner views (90-degree rotations around Y) -- matches
# Renderer.cpp `views`.
VIEWS = [
    np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64),
    np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], dtype=np.float64),
    np.array([[-1, 0, 0], [0, 1, 0], [0, 0, -1]], dtype=np.float64),
    np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]], dtype=np.float64),
]


def rotate_x(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float64)


def rotate_y(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float64)


def rotate_z(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

@dataclass
class _AddedMesh:
    mesh: Mesh
    # Transformed per-vertex positions and normals (N,3) used for that
    # instance.
    vertices: np.ndarray
    normals: np.ndarray
    flat_shaded: bool
    is_mask: bool
    is_ghost: bool


@dataclass
class Scene:
    meshes: list[_AddedMesh] = field(default_factory=list)
    # Flattened triangle arrays, built lazily by finalize().
    _v0: np.ndarray | None = None
    _edge1: np.ndarray | None = None
    _edge2: np.ndarray | None = None
    _tri_mesh: np.ndarray | None = None  # per-triangle: mesh index
    _tri_face: np.ndarray | None = None  # per-triangle: face index in mesh.faces
    _aabb_min: np.ndarray = field(
        default_factory=lambda: np.array([np.inf, np.inf, np.inf], dtype=np.float64))
    _aabb_max: np.ndarray = field(
        default_factory=lambda: np.array(
            [-np.inf, -np.inf, -np.inf], dtype=np.float64))

    def add_model(self, mesh: Mesh, matrix: np.ndarray, translation: np.ndarray,
                  flags: int = 0) -> None:
        flat_shaded = any(
            (m.flags & MATERIAL_IS_FLAT_SHADED) for m in mesh.materials)
        verts = (mesh.vertices @ matrix.T) + translation
        normals = mesh.normals @ matrix.T
        norms = np.linalg.norm(normals, axis=1)
        norms[norms == 0] = 1.0
        normals = normals / norms[:, None]
        if verts.size:
            self._aabb_min = np.minimum(self._aabb_min, verts.min(axis=0))
            self._aabb_max = np.maximum(self._aabb_max, verts.max(axis=0))
        self.meshes.append(_AddedMesh(
            mesh=mesh,
            vertices=verts,
            normals=normals,
            flat_shaded=flat_shaded,
            is_mask=bool(flags & MESH_MASK),
            is_ghost=bool(flags & MESH_GHOST),
        ))

    def finalize(self) -> None:
        v0_list, e1_list, e2_list, tm_list, tf_list = [], [], [], [], []
        for mi, am in enumerate(self.meshes):
            if am.mesh.faces.shape[0] == 0:
                continue
            faces = am.mesh.faces
            v0 = am.vertices[faces[:, 0]]
            v1 = am.vertices[faces[:, 1]]
            v2 = am.vertices[faces[:, 2]]
            v0_list.append(v0)
            e1_list.append(v1 - v0)
            e2_list.append(v2 - v0)
            tm_list.append(np.full(faces.shape[0], mi, dtype=np.int32))
            tf_list.append(np.arange(faces.shape[0], dtype=np.int32))
        if v0_list:
            self._v0 = np.concatenate(v0_list, axis=0)
            self._edge1 = np.concatenate(e1_list, axis=0)
            self._edge2 = np.concatenate(e2_list, axis=0)
            self._tri_mesh = np.concatenate(tm_list, axis=0)
            self._tri_face = np.concatenate(tf_list, axis=0)
        else:
            self._v0 = np.zeros((0, 3), dtype=np.float64)
            self._edge1 = np.zeros((0, 3), dtype=np.float64)
            self._edge2 = np.zeros((0, 3), dtype=np.float64)
            self._tri_mesh = np.zeros((0,), dtype=np.int32)
            self._tri_face = np.zeros((0,), dtype=np.int32)


# ---------------------------------------------------------------------------
# Ray intersection (batched Moller-Trumbore)
# ---------------------------------------------------------------------------

_EPS = 1e-9


def _intersect_single_closest(scene: Scene, origin: np.ndarray, direction: np.ndarray,
                              t_near: float = 0.0):
    """Single-ray version. Returns (hit, t, u, v, tri_idx)."""
    if scene._v0.shape[0] == 0:
        return False, np.inf, 0.0, 0.0, -1
    e1 = scene._edge1
    e2 = scene._edge2
    h = np.cross(direction, e2)
    a = np.einsum("tk,tk->t", e1, h)
    parallel = np.abs(a) < _EPS
    a_safe = np.where(parallel, 1.0, a)
    f = 1.0 / a_safe
    s = origin - scene._v0
    u = f * np.einsum("tk,tk->t", s, h)
    valid = (~parallel) & (u >= 0.0) & (u <= 1.0)
    q = np.cross(s, e1)
    v = f * np.einsum("k,tk->t", direction, q)
    valid &= (v >= 0.0) & (u + v <= 1.0)
    t = f * np.einsum("tk,tk->t", e2, q)
    valid &= (t > t_near)
    t_masked = np.where(valid, t, np.inf)
    tri = int(np.argmin(t_masked))
    if np.isinf(t_masked[tri]):
        return False, np.inf, 0.0, 0.0, -1
    return True, float(t_masked[tri]), float(u[tri]), float(v[tri]), tri


def _trace_first_visible(scene: Scene, origin: np.ndarray, direction: np.ndarray):
    """Return RayHit-like info, traversing through ghost meshes.

    Returns (hit, dist, ghost_dist, mesh_idx, face_idx, u, v, position,
    normal). hit==False -> only ghost_dist is meaningful.
    """
    t_near = 0.0
    ghost_dist = np.inf
    first_dist = np.inf
    for _ in range(8):  # safety: bounded ghost traversal
        ok, t, u, v, tri = _intersect_single_closest(scene, origin, direction, t_near)
        if not ok:
            return False, np.inf, ghost_dist, -1, -1, 0.0, 0.0, None, None
        if first_dist == np.inf:
            first_dist = t
            ghost_dist = t
        mesh_idx = int(scene._tri_mesh[tri])
        face_idx = int(scene._tri_face[tri])
        if scene.meshes[mesh_idx].is_ghost:
            t_near = t + 1e-4
            continue
        # Interpolate position and normal.
        am = scene.meshes[mesh_idx]
        face = am.mesh.faces[face_idx]
        w0 = 1.0 - u - v
        pos = (am.vertices[face[0]] * w0
               + am.vertices[face[1]] * u
               + am.vertices[face[2]] * v)
        n = (am.normals[face[0]] * w0
             + am.normals[face[1]] * u
             + am.normals[face[2]] * v)
        nn = np.linalg.norm(n)
        if nn > 0:
            n = n / nn
        return True, t, ghost_dist, mesh_idx, face_idx, u, v, pos, n
    return False, np.inf, ghost_dist, -1, -1, 0.0, 0.0, None, None


def _trace_occlusion(scene: Scene, origin: np.ndarray, direction: np.ndarray) -> bool:
    """True if `direction` from `origin` hits anything (ignoring ghost).

    Skips back-facing hits to mirror occlusionFilter in RayTrace.cpp: if
    the geometric normal dotted with the ray direction is positive, the
    ray is exiting through the back of a face — not a real occluder.
    """
    t_near = 1e-5
    for _ in range(8):
        ok, t, u, v, tri = _intersect_single_closest(scene, origin, direction, t_near)
        if not ok:
            return False
        # Back-face cull: geometric normal = edge1 × edge2.
        ng = np.cross(scene._edge1[tri], scene._edge2[tri])
        if float(ng @ direction) > 0:
            t_near = t + 1e-4
            continue
        mesh_idx = int(scene._tri_mesh[tri])
        if scene.meshes[mesh_idx].is_ghost:
            t_near = t + 1e-4
            continue
        return True
    return False


# ---------------------------------------------------------------------------
# Shading
# ---------------------------------------------------------------------------

def _shade_fragment(scene: Scene, pos: np.ndarray, normal: np.ndarray,
                    view: np.ndarray, color: np.ndarray,
                    specular_color: np.ndarray, specular_exponent: float,
                    ambient_color: np.ndarray,
                    lights: list[Light]) -> np.ndarray:
    out = np.zeros(3, dtype=np.float64)
    for light in lights:
        if light.shadow and _trace_occlusion(scene, pos, light.direction):
            continue
        if light.type == LIGHT_HEMI:
            diff = 0.5 * light.intensity * (1.0 + float(normal @ light.direction))
            out += color * diff
        elif light.type == LIGHT_DIFFUSE:
            diff = light.intensity * max(0.0, float(normal @ light.direction))
            out += color * diff
        else:  # LIGHT_SPECULAR
            reflected = normal * (2.0 * float(light.direction @ normal)) - light.direction
            cos_term = max(0.0, float(reflected @ view))
            spec = light.intensity * (cos_term ** specular_exponent)
            out += specular_color * spec
    return out + ambient_color


# ---------------------------------------------------------------------------
# Context (the rendering setup) and view rendering
# ---------------------------------------------------------------------------

@dataclass
class Context:
    lights: list[Light]
    dither: bool
    upt: float
    projection: np.ndarray
    scene: Scene | None = None

    @classmethod
    def make(cls, lights: list[Light], dither: bool = True,
             upt: float = TILE_SIZE) -> "Context":
        projection = np.array([
            [32.0 / upt, 0.0, -32.0 / upt],
            [-16.0 / upt, -16.0 * SQRT_6 / upt, -16.0 / upt],
            [16.0 * SQRT_3 / upt, -16.0 * SQRT_2 / upt, 16.0 * SQRT_3 / upt],
        ], dtype=np.float64)
        return cls(lights=lights, dither=dither, upt=upt, projection=projection)

    def begin_render(self) -> None:
        self.scene = Scene()

    def add_model(self, mesh: Mesh, matrix: np.ndarray, translation: np.ndarray,
                  mask: int = 0) -> None:
        assert self.scene is not None
        self.scene.add_model(mesh, matrix, translation, mask)

    def finalize_render(self) -> None:
        assert self.scene is not None
        self.scene.finalize()

    def end_render(self) -> None:
        self.scene = None


# ---------------------------------------------------------------------------
# Per-pixel sample (the Python equivalent of scene_sample_point)
# ---------------------------------------------------------------------------

@dataclass
class _Fragment:
    color: np.ndarray
    depth: float
    ghost_depth: float
    flags: int
    region: int


def _sample_point(scene: Scene, point_x: float, point_y: float,
                  camera: np.ndarray, camera_inverse: np.ndarray,
                  lights: list[Light], rng: np.random.Generator) -> _Fragment | None:
    view_vector = camera @ np.array([0.0, 0.0, -1.0])
    origin = camera @ np.array([point_x, point_y, -512.0])
    direction = -view_vector
    hit, dist, ghost_dist, mesh_idx, face_idx, u, v, pos, normal = (
        _trace_first_visible(scene, origin, direction))
    if not hit:
        f = _Fragment(color=np.zeros(3), depth=np.inf, ghost_depth=ghost_dist,
                      flags=0, region=FRAGMENT_UNUSED)
        return f

    am = scene.meshes[mesh_idx]
    face = am.mesh.faces[face_idx]
    mat = am.mesh.materials[am.mesh.face_materials[face_idx]]

    if am.is_mask or (mat.flags & MATERIAL_IS_MASK):
        return _Fragment(color=np.array([0.0, 1.0, 0.0]),
                         depth=dist, ghost_depth=ghost_dist,
                         flags=mat.flags | MATERIAL_IS_MASK,
                         region=FRAGMENT_UNUSED)

    # Surface color.
    if mat.flags & MATERIAL_HAS_TEXTURE and mat.texture is not None:
        w0 = 1.0 - u - v
        uv = (am.mesh.uvs[face[0]] * w0
              + am.mesh.uvs[face[1]] * u
              + am.mesh.uvs[face[2]] * v)
        color = texture_sample(mat.texture, uv[0], uv[1]).copy()
    else:
        color = mat.color.copy()

    if mat.flags & MATERIAL_IS_REMAPPABLE:
        intensity = float(np.max(color))
        color = np.array([intensity, intensity, intensity])

    view_vec_n = view_vector / np.linalg.norm(view_vector)
    shaded = _shade_fragment(scene, pos, normal, view_vec_n, color,
                             mat.specular_color, mat.specular_exponent,
                             mat.ambient_color, lights)

    # Ambient occlusion: 8x4 hemisphere samples.
    ao = 1.0
    if not (mat.flags & MATERIAL_NO_AO):
        if abs(normal[0]) > abs(normal[1]):
            tangent = np.array([normal[2], 0.0, -normal[0]])
        else:
            tangent = np.array([0.0, -normal[2], normal[1]])
        tn = np.linalg.norm(tangent)
        if tn > 0:
            tangent = tangent / tn
        bitangent = np.cross(normal, tangent)
        not_occluded = 0
        for i in range(AO_NUM_SAMPLES_U):
            for j in range(AO_NUM_SAMPLES_V):
                r1 = rng.random()
                r2 = rng.random()
                theta = 2 * math.pi * ((i + r1) / AO_NUM_SAMPLES_U)
                phi = math.asin(1 - ((j + r2) / AO_NUM_SAMPLES_V))
                local = np.array([math.cos(phi) * math.sin(theta),
                                  math.cos(phi) * math.cos(theta),
                                  math.sin(phi)])
                sample_dir = (normal * local[2]
                              + tangent * local[0]
                              + bitangent * local[1])
                if not _trace_occlusion(scene, pos, sample_dir):
                    not_occluded += 1
        ao = not_occluded / (AO_NUM_SAMPLES_U * AO_NUM_SAMPLES_V)

    return _Fragment(color=shaded * ao, depth=dist, ghost_depth=ghost_dist,
                     flags=mat.flags, region=mat.region)


def _sample_material(scene: Scene, point_x: float, point_y: float,
                     camera: np.ndarray):
    """Like scene_sample_material: returns (hit, material, depth, ghost_depth,
    is_mask) without shading.
    """
    view_vector = camera @ np.array([0.0, 0.0, -1.0])
    origin = camera @ np.array([point_x, point_y, -512.0])
    direction = -view_vector
    hit, dist, ghost_dist, mesh_idx, face_idx, u, v, pos, normal = (
        _trace_first_visible(scene, origin, direction))
    if not hit:
        return False, None, np.inf, ghost_dist, False
    am = scene.meshes[mesh_idx]
    mat = am.mesh.materials[am.mesh.face_materials[face_idx]]
    is_mask = am.is_mask or bool(mat.flags & MATERIAL_IS_MASK)
    return True, mat, dist, ghost_dist, is_mask


# ---------------------------------------------------------------------------
# scene_get_bounds
# ---------------------------------------------------------------------------

def _scene_bounds(scene: Scene, camera: np.ndarray) -> tuple[int, int, int, int]:
    pts = np.array([
        [scene._aabb_min[0], scene._aabb_min[1], scene._aabb_min[2]],
        [scene._aabb_max[0], scene._aabb_min[1], scene._aabb_min[2]],
        [scene._aabb_min[0], scene._aabb_max[1], scene._aabb_min[2]],
        [scene._aabb_max[0], scene._aabb_max[1], scene._aabb_min[2]],
        [scene._aabb_min[0], scene._aabb_min[1], scene._aabb_max[2]],
        [scene._aabb_max[0], scene._aabb_min[1], scene._aabb_max[2]],
        [scene._aabb_min[0], scene._aabb_max[1], scene._aabb_max[2]],
        [scene._aabb_max[0], scene._aabb_max[1], scene._aabb_max[2]],
    ])
    proj = pts @ camera.T
    xs = proj[:, 0]
    ys = proj[:, 1]
    x_lower = int(math.floor(xs.min())) - 1
    x_upper = int(math.ceil(xs.max())) + 1
    y_lower = int(math.floor(ys.min())) - 1
    y_upper = int(math.ceil(ys.max())) + 1
    return x_lower, x_upper, y_lower, y_upper


# ---------------------------------------------------------------------------
# Framebuffer + image_from_framebuffer (Floyd-Steinberg dither + bounds crop)
# ---------------------------------------------------------------------------

def _framebuffer_to_image(fb_color: np.ndarray, fb_depth: np.ndarray,
                          fb_flags: np.ndarray, fb_region: np.ndarray,
                          width: int, height: int,
                          offset_x: float, offset_y: float,
                          dither: bool) -> IndexedImage:
    used = fb_region != FRAGMENT_UNUSED
    if not used.any():
        return IndexedImage(width=1, height=1, x_offset=0, y_offset=0,
                            pixels=np.zeros((1, 1), dtype=np.uint8))
    ys, xs = np.where(used)
    x_min, x_max = int(xs.min()), int(xs.max())
    y_min, y_max = int(ys.min()), int(ys.max())

    out_w = x_max - x_min + 1
    out_h = y_max - y_min + 1
    out_x_off = x_min + int(math.floor(offset_x))
    out_y_off = y_min + int(math.floor(offset_y)) - 1
    pixels = np.zeros((out_h, out_w), dtype=np.uint8)

    # Working copy of color for Floyd-Steinberg.
    color = fb_color.copy()

    for y in range(y_min, y_max + 1):
        # The C++ code uses a serpentine-ish iteration controlled by
        # `(1 & 1) ? upper : lower` — that's a static `true` so it always
        # walks left to right (step=+1). We match.
        for x in range(x_min, x_max + 1):
            region = fb_region[y, x]
            if region == FRAGMENT_UNUSED:
                continue
            # Round-trip the color through sRGB quantization first to
            # match the C++ "fragment.color = vector_from_color(
            # color_from_vector(fragment.color))" line.
            rgb = color_from_vector(color[y, x])
            quant_linear = vector_from_color(rgb)
            color[y, x] = quant_linear
            idx, error = palette_get_nearest(int(region) & REGION_MASK,
                                             quant_linear)
            pixels[y - y_min, x - x_min] = idx
            if dither:
                # Distribute error to neighbors (always step=+1 here).
                step = 1
                points = [(x + step, y), (x - step, y + 1), (x, y + 1), (x + step, y + 1)]
                weights = [7.0 / 16.0, 3.0 / 16.0, 5.0 / 16.0, 1.0 / 16.0]
                flags_here = int(fb_flags[y, x])
                for (px, py), w in zip(points, weights):
                    if (0 <= px < width - 1 and 0 <= py < height - 1
                            and (not (flags_here & MATERIAL_NO_BLEED)
                                 or (int(fb_flags[py, px]) & MATERIAL_NO_BLEED))):
                        color[py, px] = color[py, px] + error * (0.3 * w)
    return IndexedImage(width=out_w, height=out_h,
                        x_offset=out_x_off, y_offset=out_y_off,
                        pixels=pixels)


# ---------------------------------------------------------------------------
# context_render_view
# ---------------------------------------------------------------------------

def render_view(context: Context, view: np.ndarray, silhouette: bool = False,
                rng_seed: int = 0) -> IndexedImage:
    """Render the current scene under `view` (3x3 view-matrix)."""
    assert context.scene is not None
    scene = context.scene
    camera = context.projection @ view
    camera_inverse = np.linalg.inv(camera)
    view_inverse = np.linalg.inv(view)

    x_lower, x_upper, y_lower, y_upper = _scene_bounds(scene, camera)
    width = x_upper - x_lower + 1
    height = y_upper - y_lower
    if width <= 0 or height <= 0:
        return IndexedImage(width=1, height=1, x_offset=0, y_offset=0,
                            pixels=np.zeros((1, 1), dtype=np.uint8))
    offset_x = x_lower - 0.5
    offset_y = float(y_lower)

    # Transform lights into view space.
    transformed_lights: list[Light] = []
    for L in context.lights:
        transformed_lights.append(Light(
            type=L.type,
            shadow=L.shadow,
            direction=view_inverse @ L.direction,
            intensity=L.intensity,
        ))

    fb_color = np.zeros((height, width, 3), dtype=np.float64)
    fb_depth = np.full((height, width), np.inf)
    fb_flags = np.zeros((height, width), dtype=np.int32)
    fb_region = np.full((height, width), FRAGMENT_UNUSED, dtype=np.uint8)

    rng = np.random.default_rng(rng_seed)

    for y in range(height):
        for x in range(width):
            sx = x + offset_x
            sy = y + offset_y

            # Center sample (material only).
            hit_center, mat_center, depth_center, ghost_center, mask_center = (
                _sample_material(scene, sx, sy, camera_inverse))
            if hit_center and mat_center is not None:
                if mask_center:
                    region = FRAGMENT_UNUSED
                else:
                    region = mat_center.region
                flags = mat_center.flags
                if mat_center.flags & MATERIAL_IS_VISIBLE_MASK:
                    mask_center = True
            else:
                region = FRAGMENT_UNUSED
                flags = 0
                depth_center = np.inf
                ghost_center = ghost_center if hit_center else np.inf

            # 4x4 AA subsamples.
            sub_colors = np.zeros((AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V, 3))
            sub_regions = np.full(AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V,
                                  FRAGMENT_UNUSED, dtype=np.uint8)
            sub_flags = np.zeros(AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V, dtype=np.int32)
            sub_depths = np.full(AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V, np.inf)
            sub_ghost_depths = np.full(AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V, np.inf)

            for i in range(AA_NUM_SAMPLES_U):
                for j in range(AA_NUM_SAMPLES_V):
                    ssx = sx + (i + 0.5) / AA_NUM_SAMPLES_U - 0.5
                    ssy = sy + (j + 0.5) / AA_NUM_SAMPLES_V - 0.5
                    idx = i + j * AA_NUM_SAMPLES_U
                    if not silhouette:
                        frag = _sample_point(scene, ssx, ssy, camera, camera_inverse,
                                              transformed_lights, rng)
                        if frag is None:
                            continue
                        sub_colors[idx] = frag.color
                        sub_regions[idx] = frag.region
                        sub_flags[idx] = frag.flags
                        sub_depths[idx] = frag.depth
                        sub_ghost_depths[idx] = frag.ghost_depth
                    else:
                        sh, sm, sd, sgd, s_is_mask = _sample_material(
                            scene, ssx, ssy, camera_inverse)
                        if sh and sm is not None:
                            sub_colors[idx] = np.array([0.5, 0.5, 0.5])
                            sub_regions[idx] = (FRAGMENT_UNUSED if s_is_mask
                                                else sm.region)
                            sub_flags[idx] = sm.flags
                            sub_depths[idx] = sd
                            sub_ghost_depths[idx] = sgd

            # Background-AA frontmost subsample.
            front_idx = -1
            min_depth = np.inf
            for k in range(AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V):
                if (sub_depths[k] < min_depth and
                        (sub_flags[k] &
                         (MATERIAL_BACKGROUND_AA | MATERIAL_BACKGROUND_AA_DARK))):
                    front_idx = k
                    min_depth = sub_depths[k]
            if front_idx != -1 and (min_depth < ghost_center - 4 or mask_center):
                inside = 0
                for k in range(AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V):
                    if not (sub_depths[k] > min_depth + 4
                            or (sub_regions[k] == FRAGMENT_UNUSED
                                and not (sub_flags[k] & MATERIAL_IS_MASK))
                            or (sub_flags[k] & MATERIAL_IS_VISIBLE_MASK)):
                        inside += 1
                if inside > 3:
                    region = sub_regions[front_idx]
                    depth_center = min_depth
                    flags = sub_flags[front_idx]

            fb_region[y, x] = region
            fb_flags[y, x] = flags
            if region == FRAGMENT_UNUSED:
                continue

            aa_weight = 1.0 / (AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V)
            if flags & (MATERIAL_BACKGROUND_AA | MATERIAL_BACKGROUND_AA_DARK):
                color_acc = np.zeros(3)
                weight = 0.0
                total_weight = 0.0
                for k in range(AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V):
                    if ((not (sub_flags[k] & MATERIAL_NO_BLEED)
                         or (flags & MATERIAL_NO_BLEED))
                            and not (sub_ghost_depths[k] <= depth_center + 4
                                     and sub_depths[k] > depth_center + 4)):
                        if not (sub_depths[k] > depth_center + 4
                                or (sub_regions[k] == FRAGMENT_UNUSED
                                    and not (sub_flags[k] & MATERIAL_IS_MASK))
                                or (sub_flags[k] & MATERIAL_IS_VISIBLE_MASK)):
                            color_acc += sub_colors[k] * aa_weight
                            weight += aa_weight
                        total_weight += aa_weight
                if total_weight > 0:
                    color_acc = color_acc / total_weight
                if flags & MATERIAL_BACKGROUND_AA_DARK:
                    fb_color[y, x] = color_acc * (
                        0.5 + 0.5 * (weight / total_weight if total_weight > 0 else 0))
                else:
                    fb_color[y, x] = color_acc
            else:
                color_acc = np.zeros(3)
                weight = 0.0
                for k in range(AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V):
                    if (sub_regions[k] != FRAGMENT_UNUSED
                            and (not (sub_flags[k] & MATERIAL_NO_BLEED)
                                 or (flags & MATERIAL_NO_BLEED))):
                        color_acc += sub_colors[k] * aa_weight
                        weight += aa_weight
                if weight > 0:
                    fb_color[y, x] = color_acc / weight

    return _framebuffer_to_image(fb_color, fb_depth, fb_flags, fb_region,
                                 width, height, offset_x, offset_y,
                                 context.dither)


def render_silhouette(context: Context, view: np.ndarray) -> IndexedImage:
    return render_view(context, view, silhouette=True)
