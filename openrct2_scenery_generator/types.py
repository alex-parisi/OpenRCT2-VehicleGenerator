"""
Scenery dataclasses. Rendering primitives (Model, MeshFrame, IndexedImage,
Light) come from openrct2_iso_core.types.
"""

from dataclasses import dataclass, field
from typing import Any

from openrct2_iso_core.types import IndexedImage, Model

from .constants import DEFAULT_CURSOR, DEFAULT_HEIGHT, SCROLLING_MODE_NONE


@dataclass
class SmallScenery:
    id: str = ""
    original_id: str = ""
    name: str = ""
    authors: list[str] = field(default_factory=list)
    version: str = "1.0"

    # Gameplay / placement.
    price: float = 1.0
    removal_price: float = 1.0
    cursor: str = DEFAULT_CURSOR
    height: int = DEFAULT_HEIGHT
    shape: str = "4/4"
    scenery_group: str = ""

    # Behaviour flags (map to object.json booleans).
    is_rotatable: bool = True
    is_stackable: bool = False
    requires_flat_surface: bool = False
    prohibit_walls: bool = False
    is_tree: bool = False

    # Colour remap. hasPrimaryColour is implied by a remappable material;
    # secondary adds a second remap region / overlay set of sprites.
    has_primary_colour: bool = False
    has_secondary_colour: bool = False

    # Geometry: meshes + a single Model placing them on the tile.
    meshes: list[Any] = field(default_factory=list)  # list[Mesh]
    model: Model = field(default_factory=Model)

    preview: IndexedImage | None = None

    @property
    def num_rotations(self) -> int:
        return 4 if self.is_rotatable else 1


@dataclass
class LargeSceneryTile:
    # Offsets in OpenRCT2 tile coords (x, y horizontal; z height) and clearance.
    x: int = 0
    y: int = 0
    z: int = 0
    clearance: int = 0
    has_supports: bool = False
    allow_supports_above: bool = False
    corners: int = 0xF
    walls: int = 0


@dataclass
class LargeScenery:
    id: str = ""
    original_id: str = ""
    name: str = ""
    authors: list[str] = field(default_factory=list)
    version: str = "1.0"

    price: float = 1.0
    removal_price: float = 1.0
    cursor: str = DEFAULT_CURSOR
    scrolling_mode: int = SCROLLING_MODE_NONE
    scenery_group: str = ""

    has_primary_colour: bool = False
    has_secondary_colour: bool = False
    has_tertiary_colour: bool = False
    is_tree: bool = False
    is_photogenic: bool = False

    tiles: list[LargeSceneryTile] = field(default_factory=list)

    meshes: list[Any] = field(default_factory=list)  # list[Mesh]
    model: Model = field(default_factory=Model)

    preview: IndexedImage | None = None

    @property
    def num_tiles(self) -> int:
        return len(self.tiles)
