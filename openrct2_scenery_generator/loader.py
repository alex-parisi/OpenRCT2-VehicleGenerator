"""
Load a scenery config (JSON or YAML) into a SmallScenery dataclass.
"""

from pathlib import Path
from typing import Any

from openrct2_iso_core.config import (
    LoadError,
    as_array_or_wrap,
    optional_bool,
    optional_int,
    optional_number,
    optional_string,
    optional_string_list,
    parse_config,
    read_vector3,
    require_string,
)
from openrct2_iso_core.image import read_png
from openrct2_iso_core.mesh import load_mesh
from openrct2_iso_core.types import IndexedImage, MeshFrame, Model

from .constants import (
    DEFAULT_CURSOR,
    DEFAULT_HEIGHT,
    SCROLLING_MODE_NONE,
    SMALL_SCENERY_SHAPES,
)
from .types import LargeScenery, LargeSceneryTile, SmallScenery


def _load_model(value: Any, num_meshes: int) -> Model:
    """Parse the single-frame `model` placement list into a Model."""
    if value is None:
        raise LoadError('Property "model" not found')
    arr = as_array_or_wrap(value)
    meshes_out: list[list[MeshFrame]] = []
    for elem in arr:
        if not isinstance(elem, dict):
            raise LoadError('Property "model" is not an object')
        frame = MeshFrame()

        mi = elem.get("mesh_index")
        if not isinstance(mi, int) or isinstance(mi, bool):
            raise LoadError('Property "mesh_index" not found or is not an integer')
        if mi >= num_meshes or mi < -1:
            raise LoadError(f"Mesh index {mi} is out of bounds")
        frame.mesh_index = int(mi)

        for key in ("position", "orientation"):
            prop = elem.get(key)
            if prop is None:
                continue  # MeshFrame defaults to a zero vector
            frame_val = read_vector3(prop)
            setattr(frame, key, frame_val)

        meshes_out.append([frame])
    return Model(meshes=meshes_out)


def build_small_scenery(
    config: dict, meshes: list, preview: IndexedImage | None = None
) -> SmallScenery:
    """Build a SmallScenery from a parsed config dict + in-memory meshes."""
    root = config
    obj = SmallScenery()

    obj.id = require_string(root, "id")
    obj.original_id = optional_string(root, "original_id")
    obj.name = require_string(root, "name")
    obj.authors = optional_string_list(root, "authors")
    v_str = optional_string(root, "version")
    if v_str:
        obj.version = v_str

    obj.preview = preview if preview is not None else IndexedImage.blank(1, 1)

    obj.price = optional_number(root, "price", 1.0)
    obj.removal_price = optional_number(root, "removal_price", obj.price)
    obj.cursor = optional_string(root, "cursor", DEFAULT_CURSOR)
    obj.height = optional_int(root, "height", DEFAULT_HEIGHT)

    obj.shape = optional_string(root, "shape", "4/4")
    if obj.shape not in SMALL_SCENERY_SHAPES:
        raise LoadError(
            f'Unrecognized shape "{obj.shape}" (expected one of {SMALL_SCENERY_SHAPES})'
        )
    obj.scenery_group = optional_string(root, "scenery_group")

    obj.is_rotatable = optional_bool(root, "is_rotatable", True)
    obj.is_stackable = optional_bool(root, "is_stackable", False)
    obj.requires_flat_surface = optional_bool(root, "requires_flat_surface", False)
    obj.prohibit_walls = optional_bool(root, "prohibit_walls", False)
    obj.is_tree = optional_bool(root, "is_tree", False)
    obj.has_primary_colour = optional_bool(root, "has_primary_colour", False)
    obj.has_secondary_colour = optional_bool(root, "has_secondary_colour", False)

    obj.meshes = list(meshes)
    obj.model = _load_model(root.get("model"), len(obj.meshes))
    return obj


def load_small_scenery(json_path: Path | str) -> SmallScenery:
    """Parse a config file, load its meshes + preview, build a SmallScenery."""
    root = parse_config(json_path)

    preview: IndexedImage | None = None
    preview_path = root.get("preview")
    if preview_path is not None:
        if not isinstance(preview_path, str):
            raise LoadError('Property "preview" is not a string')
        try:
            preview = read_png(preview_path)
        except Exception as e:
            raise LoadError(f"Unable to open image file {preview_path}: {e}") from e

    return build_small_scenery(root, _load_meshes(root), preview)


def _load_meshes(root: dict) -> list:
    mesh_paths = root.get("meshes")
    if not isinstance(mesh_paths, list):
        raise LoadError('Property "meshes" does not exist or is not an array')
    meshes = []
    for mp in mesh_paths:
        if not isinstance(mp, str):
            raise LoadError("Mesh path is not a string")
        meshes.append(load_mesh(mp))
    return meshes


def _load_preview(root: dict) -> IndexedImage | None:
    preview_path = root.get("preview")
    if preview_path is None:
        return None
    if not isinstance(preview_path, str):
        raise LoadError('Property "preview" is not a string')
    try:
        return read_png(preview_path)
    except Exception as e:
        raise LoadError(f"Unable to open image file {preview_path}: {e}") from e


def _load_tiles(value: Any) -> list[LargeSceneryTile]:
    if not isinstance(value, list) or len(value) == 0:
        raise LoadError('Property "tiles" not found or is not a non-empty array')
    tiles: list[LargeSceneryTile] = []
    for jt in value:
        if not isinstance(jt, dict):
            raise LoadError('Each "tiles" element must be an object')
        tiles.append(
            LargeSceneryTile(
                x=optional_int(jt, "x", 0),
                y=optional_int(jt, "y", 0),
                z=optional_int(jt, "z", 0),
                clearance=optional_int(jt, "clearance", 0),
                has_supports=optional_bool(jt, "has_supports", False),
                allow_supports_above=optional_bool(jt, "allow_supports_above", False),
                corners=optional_int(jt, "corners", 0xF),
                walls=optional_int(jt, "walls", 0),
            )
        )
    return tiles


def build_large_scenery(
    config: dict, meshes: list, preview: IndexedImage | None = None
) -> LargeScenery:
    """Build a LargeScenery from a parsed config dict + in-memory meshes."""
    root = config
    obj = LargeScenery()

    obj.id = require_string(root, "id")
    obj.original_id = optional_string(root, "original_id")
    obj.name = require_string(root, "name")
    obj.authors = optional_string_list(root, "authors")
    v_str = optional_string(root, "version")
    if v_str:
        obj.version = v_str
    obj.preview = preview if preview is not None else IndexedImage.blank(1, 1)

    obj.price = optional_number(root, "price", 1.0)
    obj.removal_price = optional_number(root, "removal_price", obj.price)
    obj.cursor = optional_string(root, "cursor", DEFAULT_CURSOR)
    obj.scrolling_mode = optional_int(root, "scrolling_mode", SCROLLING_MODE_NONE)
    obj.scenery_group = optional_string(root, "scenery_group")

    obj.has_primary_colour = optional_bool(root, "has_primary_colour", False)
    obj.has_secondary_colour = optional_bool(root, "has_secondary_colour", False)
    obj.has_tertiary_colour = optional_bool(root, "has_tertiary_colour", False)
    obj.is_tree = optional_bool(root, "is_tree", False)
    obj.is_photogenic = optional_bool(root, "is_photogenic", False)

    obj.tiles = _load_tiles(root.get("tiles"))

    obj.meshes = list(meshes)
    obj.model = _load_model(root.get("model"), len(obj.meshes))
    return obj


def load_large_scenery(json_path: Path | str) -> LargeScenery:
    root = parse_config(json_path)
    return build_large_scenery(root, _load_meshes(root), _load_preview(root))


def object_type_of(config: dict) -> str:
    """Read the scenery object type, defaulting to small scenery."""
    t = optional_string(config, "object_type", "scenery_small")
    if t not in ("scenery_small", "scenery_large"):
        raise LoadError(f'Unrecognized object_type "{t}"')
    return t
