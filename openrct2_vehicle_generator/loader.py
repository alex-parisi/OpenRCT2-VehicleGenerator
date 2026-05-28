"""Load a ride JSON config into a Ride dataclass.

Ports src/rct2-ride-gen/ProjectLoader.cpp. Mirrors validation behavior:
required fields, enum-name resolution, implied sprite flags, model
animation frame broadcasting.
"""


import json
from pathlib import Path
from typing import Any

import numpy as np

from .constants import (
    CarIndex,
    Category,
    COLOR_NAMES,
    LIGHT_DIFFUSE,
    LIGHT_SPECULAR,
    RIDE_FLAG_NAMES,
    RUNNING_SOUND_NAMES,
    SECONDARY_SOUND_NAMES,
    SPRITE_GROUP_NAMES,
    SpriteFlag,
    VEHICLE_FLAG_NAMES,
    VehicleFlag,
)
from .image import read_png
from .mesh import load_mesh
from .sprite_renderer import count_sprites
from .types import Light, MeshFrame, Model, Ride, Vehicle, MAX_FRAMES


class LoadError(Exception):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_string(obj: dict, key: str) -> str:
    v = obj.get(key)
    if not isinstance(v, str):
        raise LoadError(f"Property \"{key}\" not found or is not a string")
    return v


def _optional_string(obj: dict, key: str) -> str:
    v = obj.get(key)
    if v is None:
        return ""
    if not isinstance(v, str):
        raise LoadError(f"Property \"{key}\" is not a string")
    return v


def _require_int(obj: dict, key: str) -> int:
    v = obj.get(key)
    if not isinstance(v, int) or isinstance(v, bool):
        raise LoadError(f"Property \"{key}\" not found or is not an integer")
    return v


def _require_number(obj: dict, key: str) -> float:
    v = obj.get(key)
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise LoadError(f"Property \"{key}\" not found or is not a number")
    return float(v)


def _enum_index(value: Any, names: list[str], prop: str, label: str) -> int:
    if not isinstance(value, str):
        raise LoadError(f"Property \"{prop}\" not found or is not a string")
    if value not in names:
        raise LoadError(f"Unrecognized {label} \"{value}\"")
    return names.index(value)


def _flag_bits(value: Any, names: list[str], prop: str, label: str) -> int:
    if not isinstance(value, list):
        raise LoadError(f"Property \"{prop}\" not found or is not an array")
    flags = 0
    for tag in value:
        if not isinstance(tag, str):
            raise LoadError(f"Array \"{prop}\" contains non-string value")
        if tag not in names:
            raise LoadError(f"Unrecognized {label} \"{tag}\"")
        flags |= 1 << names.index(tag)
    return flags


def _read_vector3(arr: Any) -> np.ndarray:
    if not isinstance(arr, list) or len(arr) != 3:
        raise LoadError("Vector must be an array of 3 numbers")
    return np.array([float(x) for x in arr], dtype=np.float64)


def _as_array_or_wrap(value: Any) -> list:
    if value is None:
        raise LoadError("Missing value")
    if isinstance(value, list):
        if len(value) == 0:
            raise LoadError("Empty array")
        return value
    return [value]


# ---------------------------------------------------------------------------
# Lights
# ---------------------------------------------------------------------------

def load_lights(value: Any) -> list[Light]:
    if not isinstance(value, list):
        raise LoadError("\"lights\" is not an array")
    out: list[Light] = []
    for light in value:
        if not isinstance(light, dict):
            print("Warning: Light array contains a non-object element — ignoring")
            continue
        type_str = _require_string(light, "type")
        if type_str == "diffuse":
            type_val = LIGHT_DIFFUSE
        elif type_str == "specular":
            type_val = LIGHT_SPECULAR
        else:
            raise LoadError(f"Unrecognized light type \"{type_str}\"")
        shadow = light.get("shadow")
        if not isinstance(shadow, bool):
            raise LoadError("Property \"shadow\" not found or is not a boolean")
        direction = _read_vector3(light.get("direction"))
        n = np.linalg.norm(direction)
        if n > 0:
            direction = direction / n
        intensity = _require_number(light, "strength")
        out.append(Light(type=type_val, shadow=int(shadow),
                         direction=direction, intensity=intensity))
    return out


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def _load_model(value: Any, num_meshes: int, num_frames: int) -> Model:
    if value is None:
        raise LoadError("Property \"model\" not found")
    arr = _as_array_or_wrap(value)
    meshes_out: list[list[MeshFrame]] = []
    for elem in arr:
        if not isinstance(elem, dict):
            raise LoadError("Property \"model\" is not an object")
        # Build MAX_FRAMES entries (frames > num_frames are unused).
        frames = [MeshFrame() for _ in range(MAX_FRAMES)]

        mesh_idx_raw = elem.get("mesh_index")
        if mesh_idx_raw is None:
            raise LoadError("Property \"mesh_index\" not found")
        mesh_arr = _as_array_or_wrap(mesh_idx_raw)
        mesh_count = len(mesh_arr)
        if mesh_count != 1 and mesh_count != num_frames:
            raise LoadError(
                f"Number of elements in \"mesh_index\" ({mesh_count}) "
                f"does not match number of frames ({num_frames})")
        for j, mi in enumerate(mesh_arr):
            if not isinstance(mi, int) or isinstance(mi, bool):
                raise LoadError("Property \"mesh_index\" not found or is not an integer")
            if mi >= num_meshes or mi < -1:
                raise LoadError(f"Mesh index {mi} is out of bounds")
            frames[j].mesh_index = int(mi)
        if mesh_count < num_frames:
            for j in range(num_frames):
                frames[j].mesh_index = frames[0].mesh_index

        for key in ("position", "orientation"):
            prop = elem.get(key)
            if not isinstance(prop, list):
                raise LoadError(f'Property "{key}" not found or is not an array')
            if len(prop) == 3:
                vec = _read_vector3(prop)
                for frame in frames[:num_frames]:
                    setattr(frame, key, vec.copy())
            elif len(prop) == num_frames:
                for frame, val in zip(frames, prop):
                    setattr(frame, key, _read_vector3(val))
            else:
                raise LoadError(
                    f'Number of elements in "{key}" ({len(prop)}) does not match '
                    f'number of frames ({num_frames})')
        meshes_out.append(frames)
    return Model(meshes=meshes_out)


def _load_vehicle(value: dict, ride: Ride) -> Vehicle:
    if not isinstance(value, dict):
        raise LoadError("Vehicle array contains a non-object element")
    v = Vehicle()
    v.spacing = _require_number(value, "spacing")
    v.mass = _require_int(value, "mass")
    v.draw_order = _require_int(value, "draw_order")
    v.flags = _flag_bits(value.get("flags"), VEHICLE_FLAG_NAMES, "flags", "flag")

    num_frames = 4 if (v.flags & VehicleFlag.RESTRAINT_ANIMATION) else 1
    num_meshes = len(ride.meshes)
    v.model = _load_model(value.get("model"), num_meshes, num_frames)

    riders = value.get("riders")
    if isinstance(riders, list):
        v.num_riders = _require_int(value, "capacity")
        for rj in riders:
            v.riders.append(_load_model(rj, num_meshes, num_frames))
    elif riders is not None:
        raise LoadError("Property \"riders\" is not an array")
    return v


# ---------------------------------------------------------------------------
# Top-level load
# ---------------------------------------------------------------------------

def load_ride(json_path: Path | str) -> Ride:
    path = Path(json_path)
    root = json.loads(path.read_text())

    ride = Ride()
    ride.id = _require_string(root, "id")
    ride.original_id = _optional_string(root, "original_id")
    ride.name = _require_string(root, "name")
    ride.description = _require_string(root, "description")
    ride.capacity = _require_string(root, "capacity")
    ride.author = _optional_string(root, "author")
    v_str = _optional_string(root, "version")
    if v_str:
        ride.version = v_str

    # Preview image (optional).
    preview_path = root.get("preview")
    if preview_path is None:
        from .types import IndexedImage
        ride.preview = IndexedImage.blank(1, 1)
    else:
        if not isinstance(preview_path, str):
            raise LoadError("Property \"preview\" is not a string")
        try:
            ride.preview = read_png(preview_path)
        except Exception as e:
            raise LoadError(f"Unable to open image file {preview_path}: {e}")

    ride.ride_type = _require_string(root, "ride_type")

    ride.flags = _flag_bits(root.get("flags", []), RIDE_FLAG_NAMES, "flags", "flag") if "flags" in root else 0

    # "sprites" may be either an array of group names, or the string "all"
    # to render every group. "all" guarantees the vehicle has correct
    # sprites if someone swaps it onto a ride type with track pieces this
    # ride_type doesn't normally support (avoids glitchy fallbacks in-game).
    sprites_raw = root.get("sprites")
    if sprites_raw == "all":
        ride.sprite_flags = (1 << len(SPRITE_GROUP_NAMES)) - 1  # all 16 bits
    else:
        ride.sprite_flags = _flag_bits(sprites_raw, SPRITE_GROUP_NAMES,
                                       "sprites", "sprite group")
        # Implied sprite flags.
        sf = ride.sprite_flags
        if sf & SpriteFlag.BANKING:
            sf |= SpriteFlag.DIAGONAL_BANK_TRANSITION
            if sf & SpriteFlag.GENTLE_SLOPE:
                sf |= SpriteFlag.SLOPE_BANK_TRANSITION
            if sf & SpriteFlag.SLOPED_BANKED_TURN:
                sf |= SpriteFlag.SLOPED_BANK_TRANSITION | SpriteFlag.BANKED_SLOPE_TRANSITION
        # Dive-loop sprites reuse the 8-frame zero-g sb22 rotations, so the
        # two groups must travel together: count_sprites budgets dive loops as
        # 96 own sprites + the 16-sprite sb22 upgrade that only renders when
        # ZERO_G_ROLL is present. Every OpenRCT2 ride type pairs them already;
        # imply it here so a hand-written sprites list can't desync the
        # declared sprite count from what render_vehicle_frame emits.
        if sf & SpriteFlag.DIVE_LOOP:
            sf |= SpriteFlag.ZERO_G_ROLL
        ride.sprite_flags = int(sf)

    ride.zero_cars = _require_int(root, "zero_cars")
    ride.tab_car = _require_int(root, "preview_tab_car")
    ride.build_menu_priority = _require_int(root, "build_menu_priority")

    ride.running_sound = _enum_index(root.get("running_sound"),
                                     RUNNING_SOUND_NAMES,
                                     "running_sound", "running sound")
    ride.secondary_sound = _enum_index(root.get("secondary_sound"),
                                       SECONDARY_SOUND_NAMES,
                                       "secondary_sound", "secondary sound")

    ride.min_cars_per_train = _require_int(root, "min_cars_per_train")
    ride.max_cars_per_train = _require_int(root, "max_cars_per_train")

    # Configuration: required object with `default`, optional front/second/third/rear.
    config = root.get("configuration")
    if not isinstance(config, dict):
        raise LoadError("Property \"configuration\" not found or is not an object")
    ride.configuration = [0xFF] * 5
    default = config.get("default")
    if not isinstance(default, int) or isinstance(default, bool):
        raise LoadError("Property \"default\" not found or is not an integer")
    ride.configuration[CarIndex.DEFAULT] = int(default)
    for key, idx in [
        ("front", CarIndex.FRONT),
        ("second", CarIndex.SECOND),
        ("third", CarIndex.THIRD),
        ("rear", CarIndex.REAR),
    ]:
        v = config.get(key)
        if v is None:
            continue
        if not isinstance(v, int) or isinstance(v, bool):
            raise LoadError(f"Property \"{key}\" is not an integer")
        ride.configuration[idx] = int(v)

    # Colors.
    raw_colors = root.get("default_colors")
    if not isinstance(raw_colors, list):
        raise LoadError("Property \"default_colors\" not found or is not an array")
    for entry in raw_colors:
        if not isinstance(entry, list):
            raise LoadError(
                "Property \"default_colors\" contains an element which is not an array")
        triple = [0, 0, 0]
        for j, color in enumerate(entry[:3]):
            triple[j] = _enum_index(color, COLOR_NAMES, "default_colors", "color")
        ride.colors.append(triple)

    # Meshes.
    mesh_paths = root.get("meshes")
    if not isinstance(mesh_paths, list):
        raise LoadError("Property \"meshes\" does not exist or is not an array")
    ride.meshes = []
    for mp in mesh_paths:
        if not isinstance(mp, str):
            raise LoadError("Mesh path is not a string")
        ride.meshes.append(load_mesh(mp))

    # Vehicles.
    vehicles = root.get("vehicles")
    if not isinstance(vehicles, list):
        raise LoadError("Property \"vehicles\" does not exist or is not an array")
    ride.num_sprites = 3
    for vj in vehicles:
        veh = _load_vehicle(vj, ride)
        veh.num_sprites = count_sprites(ride.sprite_flags, veh.flags)
        ride.num_sprites += veh.num_sprites
        ride.vehicles.append(veh)

    ride.category = int(Category.ROLLERCOASTER)
    return ride
