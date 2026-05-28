"""Thin Python wrapper around the native Embree-backed renderer.

Replaces the pure-NumPy implementation. Same public surface as before
(`Context.make`, `render_view`, `rotate_x/y/z`, `VIEWS`) so callers in
`sprite_renderer.py` and `exporter.py` don't change.

The heavy lifting (ray tracing, AA/AO, dithering, palette quantization)
all happens inside `openrct2_vehicle_generator._native` against Embree.
"""


import math
from dataclasses import dataclass, field

import numpy as np

from . import _native
from .constants import MATERIAL_HAS_TEXTURE, TILE_SIZE
from .mesh import Mesh
from .types import IndexedImage, Light


# ---------------------------------------------------------------------------
# Camera helpers — same identities as rotate_y/z/x in VectorMath.hpp.
# Kept in Python because callers pass np.ndarray matrices to both add_model
# (mesh transform) and render_view (view matrix).
# ---------------------------------------------------------------------------

def rotate_x(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float64)


def rotate_y(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float64)


def rotate_z(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)


# Four-corner views (mirrors Renderer.cpp `views`).
VIEWS = [
    np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64),
    np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], dtype=np.float64),
    np.array([[-1, 0, 0], [0, 1, 0], [0, 0, -1]], dtype=np.float64),
    np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]], dtype=np.float64),
]


# ---------------------------------------------------------------------------
# Mesh -> native marshalling
# ---------------------------------------------------------------------------

def _materials_to_dicts(mesh: Mesh) -> list[dict]:
    out: list[dict] = []
    for mat in mesh.materials:
        d: dict = {
            "flags": int(mat.flags),
            "region": int(mat.region),
            "specular_exponent": float(mat.specular_exponent),
            "specular_color": tuple(float(c) for c in mat.specular_color),
            "ambient_color": tuple(float(c) for c in mat.ambient_color),
        }
        if (mat.flags & MATERIAL_HAS_TEXTURE) and mat.texture is not None:
            d["texture"] = mat.texture.pixels.astype(np.float32, copy=False)
        else:
            d["color"] = tuple(float(c) for c in mat.color)
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Context wrapper
# ---------------------------------------------------------------------------

@dataclass
class Context:
    """Lifetime manager for the native renderer."""
    lights: list[Light]
    dither: bool
    upt: float
    _inner: _native.Context = field(repr=False)

    @classmethod
    def make(cls, lights: list[Light], dither: bool = True,
             upt: float = TILE_SIZE) -> "Context":
        inner = _native.Context(lights=lights, dither=dither, upt=upt)
        return cls(lights=lights, dither=dither, upt=upt, _inner=inner)

    def begin_render(self) -> None:
        self._inner.begin_render()

    def add_model(self, mesh: Mesh, matrix: np.ndarray, translation: np.ndarray,
                  mask: int = 0) -> None:
        if mesh.faces.shape[0] == 0:
            return
        # Mesh arrays are already float32/uint32 (see load_mesh), so astype
        # copy=False is a true no-op — no allocation on the hot path.
        self._inner.add_mesh(
            vertices=mesh.vertices.astype(np.float32, copy=False),
            normals=mesh.normals.astype(np.float32, copy=False),
            uvs=mesh.uvs.astype(np.float32, copy=False),
            faces=mesh.faces.astype(np.uint32, copy=False),
            face_materials=mesh.face_materials.astype(np.uint32, copy=False),
            materials=_materials_to_dicts(mesh),
            matrix=np.ascontiguousarray(matrix, dtype=np.float32),
            translation=np.ascontiguousarray(translation, dtype=np.float32),
            mask=int(mask),
        )

    def finalize_render(self) -> None:
        self._inner.finalize_render()

    def end_render(self) -> None:
        self._inner.end_render()


# ---------------------------------------------------------------------------
# Public render entry points
# ---------------------------------------------------------------------------

def _dict_to_image(d: dict) -> IndexedImage:
    return IndexedImage(
        width=int(d["width"]),
        height=int(d["height"]),
        x_offset=int(d["x_offset"]),
        y_offset=int(d["y_offset"]),
        pixels=d["pixels"],
    )


def render_view(context: Context, view: np.ndarray, **_ignored) -> IndexedImage:
    """Render the current scene under `view`.

    `_ignored` swallows legacy keyword args (e.g. `rng_seed`) — the native
    renderer manages its own random state.
    """
    return _dict_to_image(
        context._inner.render_view(view=np.ascontiguousarray(view, dtype=np.float32)))


def render_silhouette(context: Context, view: np.ndarray) -> IndexedImage:
    return _dict_to_image(
        context._inner.render_silhouette(view=np.ascontiguousarray(view, dtype=np.float32)))
