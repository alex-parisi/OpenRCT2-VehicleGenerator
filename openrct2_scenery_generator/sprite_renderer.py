"""
Scenery sprite rendering.

Unlike vehicles (16 sprite groups of pitch/roll/yaw track rotations), scenery
needs only the cardinal rotations: VIEWS[i] == rotate_y(i * pi/2), so rendering
the prepared scene under the first `num_rotations` views yields the rotation
sprites OpenRCT2 expects. Colour remap (primary/secondary) is baked per-pixel by
the palette region of remappable materials, exactly as for vehicles — it does
not add sprites here.
"""

import numpy as np
from openrct2_iso_core.constants import TILE_SIZE
from openrct2_iso_core.geometry import assign_faces_to_tiles, subset_mesh
from openrct2_iso_core.mesh import Mesh
from openrct2_iso_core.ray_trace import VIEWS, Context, render_view
from openrct2_iso_core.types import IndexedImage

_IDENTITY3 = np.eye(3, dtype=np.float64)

# OpenRCT2 anchors large-scenery sprites at the tile's reference CORNER (paint
# offset {0,0}), not its centre like small scenery ({15,15}). Empirically, the
# anchor corner the engine expects ROTATES with the sprite direction: rendering
# direction d with the world origin at tile-centre + corner[d] reproduces the
# vanilla per-sprite offsets (x_off=-32, base aligned to the tile) for all four
# directions. Derived by matching SDN3's sprite offsets direction-by-direction.
_HALF_TILE = TILE_SIZE / 2.0
_H = _HALF_TILE
_CORNER_BY_DIR = [(_H, _H), (-_H, _H), (-_H, -_H), (_H, -_H)]

# Reserved preview/menu image slots that precede the per-tile sprites; OpenRCT2
# indexes per-tile sprites as `base + 4 + sequence*4 + direction`.
LARGE_SCENERY_PREVIEW_SLOTS = 4


def count_small_scenery_sprites(num_rotations: int) -> int:
    return num_rotations


def render_small_scenery(context: Context, num_rotations: int = 4) -> list[IndexedImage]:
    """Render the prepared scene under the first `num_rotations` cardinal views."""
    return [render_view(context, VIEWS[i]) for i in range(num_rotations)]


def count_large_scenery_sprites(num_tiles: int) -> int:
    """4 reserved preview images + one sprite per (tile, rotation)."""
    return LARGE_SCENERY_PREVIEW_SLOTS + 4 * num_tiles


# Walls: a wall sprite is the panel along one diagonal, anchored at ONE END (a
# tile corner) -- the engine places it on the correct edge via its paint offset,
# so the sprite itself need not be on an edge. The two flat sprites are mirrored
# (origin at opposite ends) and a half-tile-tall vertical drop below origin.
# Calibrated to vanilla wall offsets (x_off -31/-1, base ~half-tile below): the
# panel is shifted to its -Z end and rendered under VIEWS[1] (sprite 0) and
# VIEWS[0] (sprite 1). The author models the panel running along OBJ +Z.
_WALL_FLAT_VIEWS = (1, 0)
_WALL_END_SHIFT = (0.0, 0.0, -_HALF_TILE)


def render_wall_flat(context: Context, combined: Mesh) -> list[IndexedImage]:
    """Render the 2 flat wall sprites (offsets 0 and 1), end-anchored."""
    if combined.faces.shape[0] == 0:
        return [IndexedImage.blank(1, 1) for _ in _WALL_FLAT_VIEWS]
    translation = np.array(_WALL_END_SHIFT, dtype=np.float64)
    context.begin_render()
    context.add_model(combined, _IDENTITY3, translation, 0)
    context.finalize_render()
    out = [render_view(context, VIEWS[v]) for v in _WALL_FLAT_VIEWS]
    context.end_render()
    return out


def _render_4_rotations(context: Context, mesh: Mesh, cx: float, cz: float) -> list[IndexedImage]:
    """Render the 4 cardinal rotations of `mesh`, anchoring each direction's
    world origin at the tile's per-direction corner (centre + corner offset).
    Returns 4 blank sprites if the mesh has no faces."""
    if mesh.faces.shape[0] == 0:
        return [IndexedImage.blank(1, 1) for _ in range(4)]
    out: list[IndexedImage] = []
    for d in range(4):
        ox, oz = _CORNER_BY_DIR[d]
        translation = np.array([-(cx + ox), 0.0, -(cz + oz)], dtype=np.float64)
        context.begin_render()
        context.add_model(mesh, _IDENTITY3, translation, 0)
        context.finalize_render()
        out.append(render_view(context, VIEWS[d]))
        context.end_render()
    return out


def render_large_scenery(
    context: Context, combined: Mesh, tile_centers_xz: np.ndarray
) -> list[IndexedImage]:
    """Render a large-scenery sprite set in OpenRCT2 image order:
    4 preview sprites (whole structure, centred), then per tile (in `tiles`
    order) its 4 rotations. Each tile's geometry is the faces nearest that
    tile's centre, re-anchored so the tile origin maps to the sprite origin.
    """
    images: list[IndexedImage] = []

    # Preview slots 0-3: the whole structure, anchored at the footprint centre.
    anchor = (
        tile_centers_xz.mean(axis=0) if tile_centers_xz.shape[0] else np.zeros(2, dtype=np.float64)
    )
    images.extend(_render_4_rotations(context, combined, float(anchor[0]), float(anchor[1])))

    # Per-tile sprites, anchored at each tile's per-direction corner.
    assign = assign_faces_to_tiles(combined, tile_centers_xz)
    for seq in range(tile_centers_xz.shape[0]):
        sub = subset_mesh(combined, assign == seq)
        cx, cz = tile_centers_xz[seq]
        images.extend(_render_4_rotations(context, sub, float(cx), float(cz)))
    return images
