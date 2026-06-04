"""
Sprite-group rotation tables, count_sprites, and per-frame dispatch.
Ported from X7's rendering engine
https://github.com/X123M3-256/RCTGen
"""

import logging
import math
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
from openrct2_x7_renderer.geometry import rotate_x, rotate_y, rotate_z
from openrct2_x7_renderer.ray_trace import FinalizedScene
from openrct2_x7_renderer.types import IndexedImage

from .constants import SpriteFlag, VehicleFlag

log = logging.getLogger(__name__)


def _render_workers() -> int:
    """Thread count for parallel sprite rendering.

    The native renderer already parallelizes each `render_view` across pixels,
    but small vehicle sprites don't fill every core; issuing several
    `render_view` calls concurrently against the same finalized scene overlaps
    those tails. Each call releases the GIL and only reads the shared scene, so
    this is safe and the output is byte-identical to serial rendering. Speedup
    plateaus around 8 workers, so cap there to avoid oversubscribing the native
    threads. Set OPENRCT2VG_RENDER_THREADS=1 to force serial rendering.
    """
    env = os.environ.get("OPENRCT2VG_RENDER_THREADS")
    if env is not None:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    return min(8, os.cpu_count() or 1)

_TILE_SLOPE = 1.0 / math.sqrt(6.0)

_FLAT = 0.0
_GENTLE = math.atan(_TILE_SLOPE)
_STEEP = math.atan(4.0 * _TILE_SLOPE)
_VERTICAL = math.pi / 2
_FLAT_GENTLE_T = (_FLAT + _GENTLE) / 2.0
_GENTLE_STEEP_T = (_GENTLE + _STEEP) / 2.0
_STEEP_VERTICAL_T = (_STEEP + _VERTICAL) / 2.0

_GENTLE_DIAG = math.atan(_TILE_SLOPE / math.sqrt(2))
_STEEP_DIAG = math.atan(4.0 * _TILE_SLOPE / math.sqrt(2))
_FLAT_GENTLE_T_DIAG = (_FLAT + _GENTLE_DIAG) / 2.0

_BANK = math.pi / 4
_BANK_T = _BANK / 2.0


def _ck_right_yaw(a: float) -> float:
    return math.atan2(0.5 * (1.0 - math.cos(a)), 1.0 - 0.5 * (1.0 - math.cos(a)))


def _ck_right_pitch(a: float) -> float:
    return -math.asin(-math.sin(a) / math.sqrt(2.0))


def _ck_right_roll(a: float) -> float:
    return -math.atan2(math.sin(a) / math.sqrt(2.0), math.cos(a))


@dataclass
class _Rot:
    num_frames: int
    pitch: float
    roll: float
    yaw: float


_FLAT_SLOPE_ROT = [_Rot(32, _FLAT, 0, 0)]

_GENTLE_SLOPE_ROT = [
    _Rot(4, _FLAT_GENTLE_T, 0, 0),
    _Rot(4, -_FLAT_GENTLE_T, 0, 0),
    _Rot(32, _GENTLE, 0, 0),
    _Rot(32, -_GENTLE, 0, 0),
]

_STEEP_SLOPE_ROT = [
    _Rot(8, _GENTLE_STEEP_T, 0, 0),
    _Rot(8, -_GENTLE_STEEP_T, 0, 0),
    _Rot(32, _STEEP, 0, 0),
    _Rot(32, -_STEEP, 0, 0),
]

_VERTICAL_SLOPE_ROT = [
    _Rot(4, _STEEP_VERTICAL_T, 0, 0),
    _Rot(4, -_STEEP_VERTICAL_T, 0, 0),
    _Rot(32, _VERTICAL, 0, 0),
    _Rot(32, -_VERTICAL, 0, 0),
    _Rot(4, _VERTICAL + 1 * math.pi / 12, 0, 0),
    _Rot(4, -_VERTICAL - 1 * math.pi / 12, 0, 0),
    _Rot(4, _VERTICAL + 2 * math.pi / 12, 0, 0),
    _Rot(4, -_VERTICAL - 2 * math.pi / 12, 0, 0),
    _Rot(4, _VERTICAL + 3 * math.pi / 12, 0, 0),
    _Rot(4, -_VERTICAL - 3 * math.pi / 12, 0, 0),
    _Rot(4, _VERTICAL + 4 * math.pi / 12, 0, 0),
    _Rot(4, -_VERTICAL - 4 * math.pi / 12, 0, 0),
    _Rot(4, _VERTICAL + 5 * math.pi / 12, 0, 0),
    _Rot(4, -_VERTICAL - 5 * math.pi / 12, 0, 0),
    _Rot(4, math.pi, 0, 0),
]

_DIAGONAL_SLOPE_ROT = [
    _Rot(4, _FLAT_GENTLE_T_DIAG, 0, math.pi / 4),
    _Rot(4, -_FLAT_GENTLE_T_DIAG, 0, math.pi / 4),
    _Rot(4, _GENTLE_DIAG, 0, math.pi / 4),
    _Rot(4, -_GENTLE_DIAG, 0, math.pi / 4),
    _Rot(4, _STEEP_DIAG, 0, math.pi / 4),
    _Rot(4, -_STEEP_DIAG, 0, math.pi / 4),
]

_BANKING_ROT = [
    _Rot(8, _FLAT, _BANK_T, 0),
    _Rot(8, _FLAT, -_BANK_T, 0),
    _Rot(32, _FLAT, _BANK, 0),
    _Rot(32, _FLAT, -_BANK, 0),
]

_INLINE_TWIST_ROT = [
    _Rot(4, _FLAT, 3 * math.pi / 8, 0),
    _Rot(4, _FLAT, -3 * math.pi / 8, 0),
    _Rot(4, _FLAT, math.pi / 2, 0),
    _Rot(4, _FLAT, -math.pi / 2, 0),
    _Rot(4, _FLAT, 5 * math.pi / 8, 0),
    _Rot(4, _FLAT, -5 * math.pi / 8, 0),
    _Rot(4, _FLAT, 3 * math.pi / 4, 0),
    _Rot(4, _FLAT, -3 * math.pi / 4, 0),
    _Rot(4, _FLAT, 7 * math.pi / 8, 0),
    _Rot(4, _FLAT, -7 * math.pi / 8, 0),
]

_SLOPE_BANK_T_ROT = [
    _Rot(32, _FLAT_GENTLE_T, _BANK_T, 0),
    _Rot(32, _FLAT_GENTLE_T, -_BANK_T, 0),
    _Rot(32, -_FLAT_GENTLE_T, _BANK_T, 0),
    _Rot(32, -_FLAT_GENTLE_T, -_BANK_T, 0),
]

_DIAG_BANK_T_ROT = [
    _Rot(4, _FLAT_GENTLE_T_DIAG, _BANK_T, math.pi / 4),
    _Rot(4, _FLAT_GENTLE_T_DIAG, -_BANK_T, math.pi / 4),
    _Rot(4, -_FLAT_GENTLE_T_DIAG, _BANK_T, math.pi / 4),
    _Rot(4, -_FLAT_GENTLE_T_DIAG, -_BANK_T, math.pi / 4),
]

_SLOPED_BANK_T_ROT = [
    _Rot(4, _GENTLE, _BANK_T, 0),
    _Rot(4, _GENTLE, -_BANK_T, 0),
    _Rot(4, -_GENTLE, _BANK_T, 0),
    _Rot(4, -_GENTLE, -_BANK_T, 0),
]

_DIAG_SLOPED_BANK_T_ROT = [
    _Rot(4, _FLAT_GENTLE_T_DIAG, _BANK, math.pi / 4),
    _Rot(4, _FLAT_GENTLE_T_DIAG, -_BANK, math.pi / 4),
    _Rot(4, -_FLAT_GENTLE_T_DIAG, _BANK, math.pi / 4),
    _Rot(4, -_FLAT_GENTLE_T_DIAG, -_BANK, math.pi / 4),
    _Rot(4, _GENTLE_DIAG, _BANK_T, math.pi / 4),
    _Rot(4, _GENTLE_DIAG, -_BANK_T, math.pi / 4),
    _Rot(4, -_GENTLE_DIAG, _BANK_T, math.pi / 4),
    _Rot(4, -_GENTLE_DIAG, -_BANK_T, math.pi / 4),
    _Rot(4, _GENTLE_DIAG, _BANK, math.pi / 4),
    _Rot(4, _GENTLE_DIAG, -_BANK, math.pi / 4),
    _Rot(4, -_GENTLE_DIAG, _BANK, math.pi / 4),
    _Rot(4, -_GENTLE_DIAG, -_BANK, math.pi / 4),
]

_SLOPED_BANKED_TURN_ROT = [
    _Rot(32, _GENTLE, _BANK, 0),
    _Rot(32, _GENTLE, -_BANK, 0),
    _Rot(32, -_GENTLE, _BANK, 0),
    _Rot(32, -_GENTLE, -_BANK, 0),
]

_BANKED_SLOPE_T_ROT = [
    _Rot(4, _FLAT_GENTLE_T, _BANK, 0),
    _Rot(4, _FLAT_GENTLE_T, -_BANK, 0),
    _Rot(4, -_FLAT_GENTLE_T, _BANK, 0),
    _Rot(4, -_FLAT_GENTLE_T, -_BANK, 0),
]

_ZERO_G_BASE_ROT = [
    _Rot(4, _GENTLE, 3 * math.pi / 8, 0),
    _Rot(4, _GENTLE, -3 * math.pi / 8, 0),
    _Rot(4, -_GENTLE, 3 * math.pi / 8, 0),
    _Rot(4, -_GENTLE, -3 * math.pi / 8, 0),
    _Rot(4, _GENTLE, math.pi / 2, 0),
    _Rot(4, _GENTLE, -math.pi / 2, 0),
    _Rot(4, -_GENTLE, math.pi / 2, 0),
    _Rot(4, -_GENTLE, -math.pi / 2, 0),
    _Rot(4, _GENTLE, 5 * math.pi / 8, 0),
    _Rot(4, _GENTLE, -5 * math.pi / 8, 0),
    _Rot(4, -_GENTLE, 5 * math.pi / 8, 0),
    _Rot(4, -_GENTLE, -5 * math.pi / 8, 0),
    _Rot(4, _GENTLE, 3 * math.pi / 4, 0),
    _Rot(4, _GENTLE, -3 * math.pi / 4, 0),
    _Rot(4, -_GENTLE, 3 * math.pi / 4, 0),
    _Rot(4, -_GENTLE, -3 * math.pi / 4, 0),
    _Rot(4, _GENTLE, 7 * math.pi / 8, 0),
    _Rot(4, _GENTLE, -7 * math.pi / 8, 0),
    _Rot(4, -_GENTLE, 7 * math.pi / 8, 0),
    _Rot(4, -_GENTLE, -7 * math.pi / 8, 0),
    _Rot(4, _GENTLE_STEEP_T, math.pi / 8, 0),
    _Rot(4, _GENTLE_STEEP_T, -math.pi / 8, 0),
    _Rot(4, -_GENTLE_STEEP_T, math.pi / 8, 0),
    _Rot(4, -_GENTLE_STEEP_T, -math.pi / 8, 0),
    _Rot(4, _GENTLE_STEEP_T, 2 * math.pi / 8, 0),
    _Rot(4, _GENTLE_STEEP_T, -2 * math.pi / 8, 0),
    _Rot(4, -_GENTLE_STEEP_T, 2 * math.pi / 8, 0),
    _Rot(4, -_GENTLE_STEEP_T, -2 * math.pi / 8, 0),
    _Rot(4, _GENTLE_STEEP_T, 3 * math.pi / 8, 0),
    _Rot(4, _GENTLE_STEEP_T, -3 * math.pi / 8, 0),
    _Rot(4, -_GENTLE_STEEP_T, 3 * math.pi / 8, 0),
    _Rot(4, -_GENTLE_STEEP_T, -3 * math.pi / 8, 0),
    _Rot(4, _GENTLE_STEEP_T, math.pi / 2, 0),
    _Rot(4, _GENTLE_STEEP_T, -math.pi / 2, 0),
    _Rot(4, -_GENTLE_STEEP_T, math.pi / 2, 0),
    _Rot(4, -_GENTLE_STEEP_T, -math.pi / 2, 0),
]

_ZERO_G_SB22_4 = [
    _Rot(4, _STEEP, math.pi / 8, 0),
    _Rot(4, _STEEP, -math.pi / 8, 0),
    _Rot(4, -_STEEP, math.pi / 8, 0),
    _Rot(4, -_STEEP, -math.pi / 8, 0),
]
_ZERO_G_SB22_8 = [
    _Rot(8, _STEEP, math.pi / 8, 0),
    _Rot(8, _STEEP, -math.pi / 8, 0),
    _Rot(8, -_STEEP, math.pi / 8, 0),
    _Rot(8, -_STEEP, -math.pi / 8, 0),
]

_DIVE_LOOP_ROT = [
    _Rot(8, _STEEP_DIAG, math.pi / 4, math.pi / 8),
    _Rot(8, _STEEP_DIAG, -math.pi / 4, math.pi / 8),
    _Rot(8, -_STEEP_DIAG, math.pi / 4, math.pi / 8),
    _Rot(8, -_STEEP_DIAG, -math.pi / 4, math.pi / 8),
    _Rot(8, _STEEP_DIAG, 3 * math.pi / 8, math.pi / 8),
    _Rot(8, _STEEP_DIAG, -3 * math.pi / 8, math.pi / 8),
    _Rot(8, -_STEEP_DIAG, 3 * math.pi / 8, math.pi / 8),
    _Rot(8, -_STEEP_DIAG, -3 * math.pi / 8, math.pi / 8),
    _Rot(8, _STEEP_DIAG, math.pi / 2, math.pi / 8),
    _Rot(8, _STEEP_DIAG, -math.pi / 2, math.pi / 8),
    _Rot(8, -_STEEP_DIAG, math.pi / 2, math.pi / 8),
    _Rot(8, -_STEEP_DIAG, -math.pi / 2, math.pi / 8),
]

_CORKSCREW_ANGLES = [
    2 * math.pi / 12,
    4 * math.pi / 12,
    math.pi / 2,
    8 * math.pi / 12,
    10 * math.pi / 12,
]


def _build_corkscrew_rotations() -> list[_Rot]:
    v = []
    # Right
    for a in _CORKSCREW_ANGLES:
        v.append(_Rot(4, _ck_right_pitch(a), _ck_right_roll(a), _ck_right_yaw(a)))
    for a in _CORKSCREW_ANGLES:
        v.append(_Rot(4, _ck_right_pitch(-a), _ck_right_roll(-a), _ck_right_yaw(-a)))
    # Left mirrors right
    for a in _CORKSCREW_ANGLES:
        v.append(_Rot(4, -_ck_right_pitch(-a), -_ck_right_roll(a), -_ck_right_yaw(a)))
    for a in _CORKSCREW_ANGLES:
        v.append(_Rot(4, -_ck_right_pitch(a), -_ck_right_roll(-a), -_ck_right_yaw(-a)))
    return v


_CORKSCREW_ROT = _build_corkscrew_rotations()


_RESTRAINT_FRAMES = 12
_RESTRAINT_PER_FRAME = 4


# Sprite groups that map one flag -> one rotation table, in the exact order
# they're emitted into images.dat. Order is significant: it fixes the sprite
# image indices. ZERO_G_ROLL / DIVE_LOOP / CORKSCREW are resolved separately by
# _base_render_plan because zero-g and dive loops share the sb22 rotations.
_BASE_GROUPS: list[tuple[SpriteFlag, str, list[_Rot]]] = [
    (SpriteFlag.FLAT_SLOPE, "Rendering flat sprites", _FLAT_SLOPE_ROT),
    (SpriteFlag.GENTLE_SLOPE, "Rendering gentle sprites", _GENTLE_SLOPE_ROT),
    (SpriteFlag.STEEP_SLOPE, "Rendering steep sprites", _STEEP_SLOPE_ROT),
    (SpriteFlag.VERTICAL_SLOPE, "Rendering vertical sprites", _VERTICAL_SLOPE_ROT),
    (SpriteFlag.DIAGONAL_SLOPE, "Rendering diagonal sprites", _DIAGONAL_SLOPE_ROT),
    (SpriteFlag.BANKING, "Rendering banked sprites", _BANKING_ROT),
    (SpriteFlag.INLINE_TWIST, "Rendering inline twist sprites", _INLINE_TWIST_ROT),
    (
        SpriteFlag.SLOPE_BANK_TRANSITION,
        "Rendering slope-bank transition sprites",
        _SLOPE_BANK_T_ROT,
    ),
    (
        SpriteFlag.DIAGONAL_BANK_TRANSITION,
        "Rendering diagonal slope-bank transition sprites",
        _DIAG_BANK_T_ROT,
    ),
    (
        SpriteFlag.SLOPED_BANK_TRANSITION,
        "Rendering sloped bank transition sprites",
        _SLOPED_BANK_T_ROT,
    ),
    (
        SpriteFlag.DIAGONAL_SLOPED_BANK_TRANSITION,
        "Rendering diagonal sloped bank transition sprites",
        _DIAG_SLOPED_BANK_T_ROT,
    ),
    (SpriteFlag.SLOPED_BANKED_TURN, "Rendering sloped banked sprites", _SLOPED_BANKED_TURN_ROT),
    (
        SpriteFlag.BANKED_SLOPE_TRANSITION,
        "Rendering banked slope transition sprites",
        _BANKED_SLOPE_T_ROT,
    ),
]


def _frames(rots: list[_Rot]) -> int:
    """Total rendered sprites a rotation table produces (sum of yaw steps)."""
    return sum(r.num_frames for r in rots)


def _base_render_plan(sprite_flags: int) -> list[tuple[str, list[_Rot]]]:
    """The ordered (log message, rotation table) groups rendered for frame 0.

    Single source of truth for both rendering and counting: `render_vehicle_frame`
    renders each table and `count_sprites` sums their frames, so the declared
    sprite count can't drift from the rendered set.
    """
    sf = sprite_flags
    plan: list[tuple[str, list[_Rot]]] = []
    for flag, msg, rots in _BASE_GROUPS:
        if sf & flag:
            plan.append((msg, rots))
    if sf & SpriteFlag.ZERO_G_ROLL:
        # Dive loops upgrade the shared sb22 rotations from 4 to 8 frames.
        sb22 = _ZERO_G_SB22_8 if (sf & SpriteFlag.DIVE_LOOP) else _ZERO_G_SB22_4
        plan.append(("Rendering zero G roll sprites", _ZERO_G_BASE_ROT))
        plan.append(("Rendering zero G roll sb22 sprites", sb22))
    if sf & SpriteFlag.DIVE_LOOP:
        plan.append(("Rendering dive loop sprites", _DIVE_LOOP_ROT))
    if sf & SpriteFlag.CORKSCREW:
        plan.append(("Rendering corkscrew sprites", _CORKSCREW_ROT))
    return plan


def count_sprites(sprite_flags: int, vehicle_flags: int) -> int:
    n = sum(_frames(rots) for _msg, rots in _base_render_plan(sprite_flags))
    # A dive loop's declared count includes the sb22 8-frame upgrade even when
    # ZERO_G_ROLL is absent (the engine reserves those slots). The loader always
    # implies ZERO_G_ROLL for DIVE_LOOP, so this only affects the documented
    # dive-loop-alone desync case -- see tests/test_sprite_counts.py.
    if (sprite_flags & SpriteFlag.DIVE_LOOP) and not (sprite_flags & SpriteFlag.ZERO_G_ROLL):
        n += _frames(_ZERO_G_SB22_8) - _frames(_ZERO_G_SB22_4)
    if vehicle_flags & VehicleFlag.RESTRAINT_ANIMATION:
        n += _RESTRAINT_FRAMES
    return n


def _rotation_views(rot: _Rot) -> list[np.ndarray]:
    """
    The `rot.num_frames` yaw-stepped view matrices for a (pitch, roll, yaw)
    orientation, in sprite-index order.
    """
    # Mirror the float round-trip in renderRotation().
    pitch = float(np.float32(rot.pitch))
    roll = float(np.float32(rot.roll))
    yaw_base = float(np.float32(rot.yaw))
    out: list[np.ndarray] = []
    for i in range(rot.num_frames):
        yaw = yaw_base + (2.0 * i * math.pi) / rot.num_frames
        out.append(rotate_y(yaw) @ rotate_z(pitch) @ rotate_x(roll))
    return out


def _frame_views(sprite_flags: int, frame: int) -> list[np.ndarray]:
    """Every view matrix for this vehicle frame, in sprite-index order."""
    if frame > 0:
        log.info("Rendering restraint animation frame %d", frame)
        return _rotation_views(_Rot(_RESTRAINT_PER_FRAME, 0, 0, 0))

    views: list[np.ndarray] = []
    for msg, rots in _base_render_plan(sprite_flags):
        log.info(msg)
        for r in rots:
            views.extend(_rotation_views(r))
    return views


def _render_views(scene: FinalizedScene, views: list[np.ndarray]) -> list[IndexedImage]:
    """Render `views` against the finalized scene, in order.

    Each `render_view` is independent and only reads the shared scene, so they
    are issued concurrently to overlap the native renderer's per-image tails
    (see `_render_workers`). `ThreadPoolExecutor.map` preserves input order, so
    sprite indices are unchanged.
    """
    workers = min(_render_workers(), len(views))
    if workers <= 1:
        return [scene.render_view(v) for v in views]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(scene.render_view, views))


def render_vehicle_frame(
    scene: FinalizedScene, sprite_flags: int, frame: int
) -> list[IndexedImage]:
    """
    Render every sprite for this vehicle frame.
    """
    return _render_views(scene, _frame_views(sprite_flags, frame))
