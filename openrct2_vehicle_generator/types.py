"""
Vehicle-specific dataclasses. Shared rendering primitives (MeshFrame, Model,
IndexedImage, Light, MAX_FRAMES) live in openrct2_x7_renderer.types.
"""

from dataclasses import dataclass, field
from typing import Any

from openrct2_x7_renderer.types import (
    MAX_FRAMES,
    IndexedImage,
    Light,
    MeshFrame,
    Model,
)

from .constants import TILE_SIZE

__all__ = [
    "MAX_FRAMES",
    "IndexedImage",
    "Light",
    "MeshFrame",
    "Model",
    "Vehicle",
    "Ride",
]


@dataclass
class Vehicle:
    model: Model = field(default_factory=Model)
    flags: int = 0
    mass: int = 0
    num_sprites: int = 0
    draw_order: int = 0
    num_riders: int = 0
    spacing: float = 0.0
    effect_visual: int = 1
    riders: list[Model] = field(default_factory=list)


@dataclass
class Ride:
    id: str = ""
    original_id: str = ""
    name: str = ""
    description: str = ""
    capacity: str = ""
    authors: list[str] = field(default_factory=list)
    version: str = "1.0"
    ride_type: str = ""

    # default, front, second, rear, third  (0xFF means absent).
    configuration: list[int] = field(default_factory=lambda: [0xFF] * 5)

    # Model units per tile: the scale that maps OBJ-space units onto one
    # OpenRCT2 tile. Drives both the render projection (sprite size) and the
    # exporter's model->game-unit conversions (spacing, rider positions), so
    # they always agree. Default matches the realistic 3.3 m tile.
    units_per_tile: float = TILE_SIZE

    flags: int = 0
    zero_cars: int = 0
    min_cars_per_train: int = 0
    max_cars_per_train: int = 0
    category: int = 0
    build_menu_priority: int = 0
    tab_car: int = 0
    running_sound: int = 0
    secondary_sound: int = 0
    sprite_flags: int = 0
    num_sprites: int = 0

    colors: list[list[int]] = field(default_factory=list)
    meshes: list[Any] = field(default_factory=list)  # list[Mesh]
    vehicles: list[Vehicle] = field(default_factory=list)

    preview: IndexedImage | None = None
