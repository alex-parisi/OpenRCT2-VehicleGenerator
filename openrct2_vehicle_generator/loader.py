"""
Load a ride config (JSON or YAML) into a Ride dataclass.
"""

from pathlib import Path
from typing import Any

from openrct2_x7_renderer.config import (
    LoadError,
    as_array_or_wrap,
    load_meshes,
    load_preview,
    optional_int,
    optional_number,
    optional_string,
    optional_string_list,
    parse_config,
    read_vector3,
    require_int,
    require_number,
    require_string,
)

from .constants import (
    COLOR_NAMES,
    RIDE_FLAG_NAMES,
    RUNNING_SOUND_NAMES,
    SECONDARY_SOUND_NAMES,
    SPRITE_GROUP_NAMES,
    TILE_SIZE,
    VEHICLE_FLAG_NAMES,
    CarIndex,
    Category,
    SpriteFlag,
    frames_for,
)
from .sprite_renderer import count_sprites
from .types import MAX_FRAMES, IndexedImage, MeshFrame, Model, Ride, Vehicle


def _enum_index(value: Any, names: list[str], prop: str, label: str) -> int:
    if not isinstance(value, str):
        raise LoadError(f'Property "{prop}" not found or is not a string')
    if value not in names:
        raise LoadError(f'Unrecognized {label} "{value}"')
    return names.index(value)


def _flag_bits(value: Any, names: list[str], prop: str, label: str) -> int:
    if not isinstance(value, list):
        raise LoadError(f'Property "{prop}" not found or is not an array')
    flags = 0
    for tag in value:
        if not isinstance(tag, str):
            raise LoadError(f'Array "{prop}" contains non-string value')
        if tag not in names:
            raise LoadError(f'Unrecognized {label} "{tag}"')
        flags |= 1 << names.index(tag)
    return flags


def _frame_count_error(key: str, count: int, num_frames: int) -> LoadError:
    return LoadError(
        f'Number of elements in "{key}" ({count}) does not match '
        f"number of frames ({num_frames})"
    )


def _frame_mesh_indices(raw: Any, num_frames: int, num_meshes: int) -> list[int]:
    """Resolve `mesh_index` to one int per frame: a single value is broadcast
    across all frames, otherwise the count must equal `num_frames`."""
    arr = as_array_or_wrap(raw)
    if len(arr) != 1 and len(arr) != num_frames:
        raise _frame_count_error("mesh_index", len(arr), num_frames)
    indices: list[int] = []
    for mi in arr:
        if not isinstance(mi, int) or isinstance(mi, bool):
            raise LoadError('Property "mesh_index" not found or is not an integer')
        if mi >= num_meshes or mi < -1:
            raise LoadError(f"Mesh index {mi} is out of bounds")
        indices.append(int(mi))
    return indices * num_frames if len(indices) == 1 else indices


def _frame_vectors(prop: Any, num_frames: int, key: str) -> list[Any]:
    """Resolve `position`/`orientation` to one vector per frame: a single
    `[x, y, z]` is broadcast across all frames, otherwise it must be a list of
    `num_frames` vectors."""
    if not isinstance(prop, list):
        raise LoadError(f'Property "{key}" is not an array')
    if len(prop) == 3:
        vec = read_vector3(prop)
        return [vec.copy() for _ in range(num_frames)]
    if len(prop) == num_frames:
        return [read_vector3(val) for val in prop]
    raise _frame_count_error(key, len(prop), num_frames)


def _load_model(value: Any, num_meshes: int, num_frames: int) -> Model:
    if value is None:
        raise LoadError('Property "model" not found')
    arr = as_array_or_wrap(value)
    meshes_out: list[list[MeshFrame]] = []
    for elem in arr:
        if not isinstance(elem, dict):
            raise LoadError('Property "model" is not an object')

        mesh_idx_raw = elem.get("mesh_index")
        if mesh_idx_raw is None:
            raise LoadError('Property "mesh_index" not found')
        mesh_indices = _frame_mesh_indices(mesh_idx_raw, num_frames, num_meshes)

        # None => omit the kwarg so MeshFrame falls back to its zero-vector default.
        vectors = {
            key: _frame_vectors(prop, num_frames, key) if (prop := elem.get(key)) is not None
            else None
            for key in ("position", "orientation")
        }

        # MeshFrame is immutable. Build the num_frames active frames, then pad the
        # unused slots (num_frames..MAX_FRAMES) with the MeshFrame default.
        frames: list[MeshFrame] = []
        for j in range(MAX_FRAMES):
            if j >= num_frames:
                frames.append(MeshFrame())
                continue
            kwargs: dict[str, Any] = {"mesh_index": mesh_indices[j]}
            if vectors["position"] is not None:
                kwargs["position"] = vectors["position"][j]
            if vectors["orientation"] is not None:
                kwargs["orientation"] = vectors["orientation"][j]
            frames.append(MeshFrame(**kwargs))
        meshes_out.append(frames)
    return Model(meshes=meshes_out)


def _load_vehicle(value: dict, ride: Ride) -> Vehicle:
    v = Vehicle()
    v.spacing = require_number(value, "spacing")
    v.mass = require_int(value, "mass")
    v.draw_order = require_int(value, "draw_order")
    v.effect_visual = optional_int(value, "effect_visual", 1)
    v.flags = _flag_bits(value.get("flags", []), VEHICLE_FLAG_NAMES, "flags", "flag")

    num_frames = frames_for(v.flags)
    num_meshes = len(ride.meshes)
    v.model = _load_model(value.get("model"), num_meshes, num_frames)

    riders = value.get("riders")
    if isinstance(riders, list):
        for rj in riders:
            v.riders.append(_load_model(rj, num_meshes, num_frames))
        # Seat count is the total number of peep meshes across all rows; each
        # rider row is a Model whose submeshes are the individual peeps.
        v.num_riders = sum(
            1 for row in v.riders for submesh in row.meshes if submesh[0].mesh_index >= 0
        )
    elif riders is not None:
        raise LoadError('Property "riders" is not an array')
    return v


def build_ride(config: dict, meshes: list, preview: IndexedImage | None = None) -> Ride:
    """
    Build a Ride from an already-parsed config dict + in-memory meshes.
    """
    root = config

    ride = Ride()
    ride.id = require_string(root, "id")
    ride.original_id = optional_string(root, "original_id")
    ride.name = require_string(root, "name")
    ride.description = require_string(root, "description")
    ride.capacity = require_string(root, "capacity")
    ride.authors = optional_string_list(root, "authors")
    v_str = optional_string(root, "version")
    if v_str:
        ride.version = v_str

    ride.preview = preview if preview is not None else IndexedImage.blank(1, 1)

    ride.ride_type = require_string(root, "ride_type")

    ride.units_per_tile = optional_number(root, "units_per_tile", TILE_SIZE)
    if ride.units_per_tile <= 0.0:
        raise LoadError('Property "units_per_tile" must be greater than 0')

    ride.flags = (
        _flag_bits(root.get("flags", []), RIDE_FLAG_NAMES, "flags", "flag")
        if "flags" in root
        else 0
    )

    sprites_raw = root.get("sprites")
    if sprites_raw == "all":
        ride.sprite_flags = (1 << len(SPRITE_GROUP_NAMES)) - 1  # all 16 bits
    else:
        ride.sprite_flags = _flag_bits(sprites_raw, SPRITE_GROUP_NAMES, "sprites", "sprite group")
        # Implied sprite flags.
        sf = ride.sprite_flags
        if sf & SpriteFlag.BANKING:
            sf |= SpriteFlag.DIAGONAL_BANK_TRANSITION
            if sf & SpriteFlag.GENTLE_SLOPE:
                sf |= SpriteFlag.SLOPE_BANK_TRANSITION
            if sf & SpriteFlag.SLOPED_BANKED_TURN:
                sf |= SpriteFlag.SLOPED_BANK_TRANSITION | SpriteFlag.BANKED_SLOPE_TRANSITION
        # Dive-loop sprites reuse the 8-frame zero-g sb22 rotations, so the
        # two groups must travel together
        if sf & SpriteFlag.DIVE_LOOP:
            sf |= SpriteFlag.ZERO_G_ROLL
        ride.sprite_flags = int(sf)

    ride.zero_cars = optional_int(root, "zero_cars", 0)
    ride.tab_car = optional_int(root, "preview_tab_car", 0)
    ride.build_menu_priority = optional_int(root, "build_menu_priority", 0)

    ride.running_sound = _enum_index(
        root.get("running_sound"), RUNNING_SOUND_NAMES, "running_sound", "running sound"
    )
    ride.secondary_sound = _enum_index(
        root.get("secondary_sound"), SECONDARY_SOUND_NAMES, "secondary_sound", "secondary sound"
    )

    ride.min_cars_per_train = require_int(root, "min_cars_per_train")
    ride.max_cars_per_train = require_int(root, "max_cars_per_train")

    # Configuration: optional object with `default` (defaults to 0), plus
    # optional front/rear. Single-car-type rides can omit it.
    car_config = root.get("configuration", {"default": 0})
    ride.configuration = [0xFF] * 5
    default = car_config.get("default")
    if not isinstance(default, int) or isinstance(default, bool):
        raise LoadError('Property "default" not found or is not an integer')
    ride.configuration[CarIndex.DEFAULT] = int(default)
    # `second`/`third` map to engine slots the exporter doesn't emit yet, so
    # reject them loudly rather than accepting and silently dropping them.
    for unsupported in ("second", "third"):
        if car_config.get(unsupported) is not None:
            raise LoadError(f'Property "{unsupported}" is not yet supported')
    for key, idx in [
        ("front", CarIndex.FRONT),
        ("rear", CarIndex.REAR),
    ]:
        slot = car_config.get(key)
        if slot is None:
            continue
        if not isinstance(slot, int) or isinstance(slot, bool):
            raise LoadError(f'Property "{key}" is not an integer')
        ride.configuration[idx] = int(slot)

    # Colors.
    raw_colors = root.get("default_colors")
    if not isinstance(raw_colors, list):
        raise LoadError('Property "default_colors" not found or is not an array')
    for entry in raw_colors:
        if not isinstance(entry, list):
            raise LoadError('Property "default_colors" contains an element which is not an array')
        triple = [0, 0, 0]
        for j, color in enumerate(entry[:3]):
            triple[j] = _enum_index(color, COLOR_NAMES, "default_colors", "color")
        ride.colors.append(triple)

    # Meshes are supplied by the caller (already loaded), not read from paths.
    ride.meshes = list(meshes)

    # Vehicles.
    vehicles = root.get("vehicles")
    if not isinstance(vehicles, list):
        raise LoadError('Property "vehicles" does not exist or is not an array')
    for vj in vehicles:
        veh = _load_vehicle(vj, ride)
        veh.num_sprites = count_sprites(ride.sprite_flags, veh.flags)
        ride.vehicles.append(veh)

    ride.category = int(Category.ROLLERCOASTER)
    return ride


def load_ride(json_path: Path | str) -> Ride:
    """Parse a config file, load its meshes + preview from disk, build a Ride."""
    root = parse_config(json_path)
    return build_ride(root, load_meshes(root), load_preview(root))
