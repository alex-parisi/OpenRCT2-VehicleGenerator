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
from openrct2_iso_core.geometry import assign_faces_to_tiles, combine_model_world, subset_mesh
from openrct2_iso_core.mesh import Mesh
from openrct2_iso_core.ray_trace import VIEWS, Context, render_view
from openrct2_iso_core.types import IndexedImage, Model

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


# Animated small scenery reserves a leading group of 4 "base" sprites (the
# static depiction shown in the scenery picker and when zoomed out). The engine
# only paints these when SMALL_SCENERY_FLAG_VISIBLE_WHEN_ZOOMED is set, which
# also shifts the in-world animation index by +4 (Paint.SmallScenery.cpp:294)
# and suppresses the always-on static base parent draw (line 193) that would
# otherwise overlay a frozen pose-0 ghost on the animation.
ANIMATED_BASE_SLOTS = 4


def count_small_scenery_sprites(num_rotations: int, num_pose_groups: int = 1) -> int:
    """Static scenery: `num_rotations` sprites. Animated scenery: a 4-sprite base
    group, then one group of 4 rotation sprites per pose (the engine's frame
    index hardcodes * 4 and adds +4 past the base), so
    `4 + num_pose_groups * 4` regardless of `num_rotations`."""
    if num_pose_groups > 1:
        return ANIMATED_BASE_SLOTS + num_pose_groups * 4
    return num_rotations


def render_small_scenery(context: Context, num_rotations: int = 4) -> list[IndexedImage]:
    """Render the prepared scene under the first `num_rotations` cardinal views."""
    return [render_view(context, VIEWS[i]) for i in range(num_rotations)]


def _render_pose_rotations(
    context: Context, meshes: list[Mesh], model: Model, frame: int
) -> list[IndexedImage]:
    """Bake pose `frame`'s placements and render all 4 cardinal rotations,
    anchored at the tile centre (model origin)."""
    combined = combine_model_world(meshes, model, frame=frame)
    context.begin_render()
    context.add_model(combined, _IDENTITY3, np.zeros(3, dtype=np.float64), 0)
    context.finalize_render()
    out = [render_view(context, VIEWS[d]) for d in range(4)]
    context.end_render()
    return out


def render_small_scenery_animated(
    context: Context, meshes: list[Mesh], model: Model, num_pose_groups: int
) -> list[IndexedImage]:
    """Render an animated small-scenery sprite set in the engine's image order:
    a leading 4-sprite base group (rendered from pose 0; the static depiction the
    engine paints in the picker / when zoomed out), then per pose group its 4
    cardinal rotations (group-major, direction-minor). Matches vanilla animated
    scenery, whose in-world animation index is `4 + frame_offsets[frame] * 4 +
    direction` (Paint.SmallScenery.cpp:293-296)."""
    images: list[IndexedImage] = _render_pose_rotations(context, meshes, model, 0)
    for g in range(num_pose_groups):
        images.extend(_render_pose_rotations(context, meshes, model, g))
    return images


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
# One land-height step as a vertical shear of the panel end, in OBJ Y. Calibrated
# to vanilla wall slope sprites (slope-up sprite ~+15px taller than flat); refine
# against real sloped terrain in-game.
_WALL_SLOPE_RISE = 1.26


def _shear_wall(combined: Mesh, sign: float, y_raise: float = 0.0) -> Mesh:
    """Ramp the panel's Y along its length (Z), raising the +Z end by
    `sign * _WALL_SLOPE_RISE` so it follows a sloped edge. `y_raise` lifts the
    whole panel (slope-down anchors at the raised corner)."""
    v = combined.vertices.astype(np.float64).copy()
    z = v[:, 2]
    zmin, zmax = float(z.min()), float(z.max())
    span = (zmax - zmin) or 1.0
    t = (z - zmin) / span  # 0 at -Z end, 1 at +Z end
    v[:, 1] += sign * _WALL_SLOPE_RISE * t + y_raise
    return Mesh(
        vertices=v.astype(np.float32),
        normals=combined.normals,
        uvs=combined.uvs,
        faces=combined.faces,
        face_materials=combined.face_materials,
        materials=combined.materials,
    )


def _render_wall_pair(context: Context, mesh: Mesh) -> list[IndexedImage]:
    """Render a wall mesh under the two diagonal views (end-anchored)."""
    translation = np.array(_WALL_END_SHIFT, dtype=np.float64)
    context.begin_render()
    context.add_model(mesh, _IDENTITY3, translation, 0)
    context.finalize_render()
    out = [render_view(context, VIEWS[v]) for v in _WALL_FLAT_VIEWS]
    context.end_render()
    return out


def render_wall(context: Context, combined: Mesh, allowed_on_slope: bool) -> list[IndexedImage]:
    """Render a wall sprite set: 2 flat sprites, plus (if slope-allowed) 4
    slope-sheared sprites -- offsets 2,3 = slope-up, 4,5 = slope-down, each in
    the two diagonal orientations."""
    if combined.faces.shape[0] == 0:
        n = 6 if allowed_on_slope else 2
        return [IndexedImage.blank(1, 1) for _ in range(n)]
    images = _render_wall_pair(context, combined)  # offsets 0,1 (flat)
    if allowed_on_slope:
        # slope-up: far end raised. slope-down: far end lowered AND the whole
        # panel lifted one step (it anchors at the raised/high corner).
        images += _render_wall_pair(context, _shear_wall(combined, +1.0))  # 2,3 up
        images += _render_wall_pair(
            context, _shear_wall(combined, -1.0, y_raise=_WALL_SLOPE_RISE)
        )  # 4,5 down
    return images


def render_wall_flat(context: Context, combined: Mesh) -> list[IndexedImage]:
    """Render only the 2 flat wall sprites (kept for callers/tests)."""
    if combined.faces.shape[0] == 0:
        return [IndexedImage.blank(1, 1) for _ in _WALL_FLAT_VIEWS]
    return _render_wall_pair(context, combined)


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
