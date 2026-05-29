"""Dataclasses mirroring the C++ structs in Project.hpp / Vehicle.hpp /
Model.hpp / Renderer.hpp.
"""


from dataclasses import dataclass, field
from typing import Any

import numpy as np


MAX_FRAMES = 4


@dataclass
class MeshFrame:
    mesh_index: int = -1
    position: np.ndarray = field(
        default_factory=lambda: np.zeros(3, dtype=np.float64))
    orientation: np.ndarray = field(
        default_factory=lambda: np.zeros(3, dtype=np.float64))


@dataclass
class Model:
    # Outer list: one entry per submesh. Each inner list always has
    # MAX_FRAMES MeshFrames (broadcast from a single one when the JSON
    # specifies a non-animated model).
    meshes: list[list[MeshFrame]] = field(default_factory=list)


@dataclass
class Vehicle:
    model: Model = field(default_factory=Model)
    flags: int = 0
    mass: int = 0
    num_sprites: int = 0
    draw_order: int = 0
    num_riders: int = 0
    spacing: float = 0.0
    riders: list[Model] = field(default_factory=list)


@dataclass
class IndexedImage:
    """8-bit palette image. Pixel value 0 is transparent."""

    width: int
    height: int
    x_offset: int
    y_offset: int
    pixels: np.ndarray  # uint8 (height, width)

    @classmethod
    def blank(cls, width: int, height: int, x_offset: int = 0, y_offset: int = 0) -> "IndexedImage":
        return cls(
            width=width,
            height=height,
            x_offset=x_offset,
            y_offset=y_offset,
            pixels=np.zeros((height, width), dtype=np.uint8),
        )


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


@dataclass
class Light:
    type: int  # LIGHT_HEMI / LIGHT_DIFFUSE / LIGHT_SPECULAR
    shadow: int
    direction: np.ndarray
    intensity: float
