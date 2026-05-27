"""Build object.json and assemble the .parkobj ZIP.

Ports src/rct2-ride-gen/ProjectExporter.cpp.
"""

from __future__ import annotations

import json
import math
import os
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from .constants import (
    CATEGORY_NAMES,
    CarIndex,
    COLOR_NAMES,
    FRICTION_SOUND_IDS,
    RideFlag,
    SpriteFlag,
    TILE_SIZE,
    VehicleFlag,
)
from .image import create_atlas, write_png
from .ray_trace import Context, render_view, rotate_y
from .sprite_renderer import count_sprites, render_vehicle_frame
from .types import Model, Ride, Vehicle


# ---------------------------------------------------------------------------
# object.json construction
# ---------------------------------------------------------------------------

def _emit_sprite_groups(sf: int, vf: int) -> dict[str, int]:
    out: dict[str, int] = {}

    def add(key: str, n: int) -> None:
        out[key] = n

    if sf & SpriteFlag.FLAT_SLOPE: add("slopeFlat", 32)
    if sf & SpriteFlag.GENTLE_SLOPE:
        add("slopes12", 4); add("slopes25", 32)
    if sf & SpriteFlag.STEEP_SLOPE:
        add("slopes42", 8); add("slopes60", 32)
    if sf & SpriteFlag.VERTICAL_SLOPE:
        add("slopes75", 4); add("slopes90", 32)
        add("slopesLoop", 4); add("slopeInverted", 4)
    if sf & SpriteFlag.DIAGONAL_SLOPE:
        add("slopes8", 4); add("slopes16", 4); add("slopes50", 4)
    if sf & SpriteFlag.BANKING:
        add("flatBanked22", 8); add("flatBanked45", 32)
    if sf & SpriteFlag.INLINE_TWIST:
        add("flatBanked67", 4); add("flatBanked90", 4); add("inlineTwists", 4)
    if sf & SpriteFlag.SLOPE_BANK_TRANSITION:
        add("slopes12Banked22", 32)
    if sf & SpriteFlag.DIAGONAL_BANK_TRANSITION:
        add("slopes8Banked22", 4)
    if sf & SpriteFlag.SLOPED_BANK_TRANSITION:
        add("slopes25Banked22", 4)
    if sf & SpriteFlag.DIAGONAL_SLOPED_BANK_TRANSITION:
        add("slopes8Banked45", 4); add("slopes16Banked22", 4); add("slopes16Banked45", 4)
    if sf & SpriteFlag.SLOPED_BANKED_TURN:
        add("slopes25Banked45", 32)
    if sf & SpriteFlag.BANKED_SLOPE_TRANSITION:
        add("slopes12Banked45", 4)
    if sf & SpriteFlag.ZERO_G_ROLL:
        add("slopes25Banked67", 4); add("slopes25Banked90", 4)
        add("slopes25InlineTwists", 4)
        add("slopes42Banked22", 4); add("slopes42Banked45", 4)
        add("slopes42Banked67", 4); add("slopes42Banked90", 4)
        add("slopes60Banked22", 8 if (sf & SpriteFlag.DIVE_LOOP) else 4)
    if sf & SpriteFlag.DIVE_LOOP:
        add("slopes50Banked45", 8); add("slopes50Banked67", 8); add("slopes50Banked90", 8)
    if sf & SpriteFlag.CORKSCREW:
        add("corkscrews", 4)
    if vf & VehicleFlag.RESTRAINT_ANIMATION:
        add("restraintAnimation", 4)
    return out


def _make_image_object(path: str, x: int, y: int,
                       src_x: int, src_y: int,
                       src_w: int, src_h: int) -> dict[str, Any]:
    obj: dict[str, Any] = {"path": path, "x": x, "y": y}
    if src_x >= 0:
        obj["src_x"] = src_x
    if src_y >= 0:
        obj["src_y"] = src_y
    if src_w > 0:
        obj["src_width"] = src_w
    if src_h > 0:
        obj["src_height"] = src_h
    obj["palette"] = "keep"
    return obj


def build_ride_json(ride: Ride) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["id"] = ride.id
    if ride.original_id:
        out["originalId"] = ride.original_id
    out["version"] = ride.version

    out["authors"] = [ride.author] if ride.author else []
    out["objectType"] = "ride"

    properties: dict[str, Any] = {}
    properties["type"] = [ride.ride_type]
    properties["category"] = CATEGORY_NAMES[ride.category]
    properties["minCarsPerTrain"] = ride.min_cars_per_train
    properties["maxCarsPerTrain"] = ride.max_cars_per_train
    properties["numEmptyCars"] = ride.zero_cars
    properties["tabCar"] = ride.tab_car
    properties["defaultCar"] = ride.configuration[CarIndex.DEFAULT]
    front = ride.configuration[CarIndex.FRONT]
    if front != 0xFF:
        properties["headCars"] = front
    rear = ride.configuration[CarIndex.REAR]
    if rear != 0xFF:
        properties["tailCars"] = rear

    properties["buildMenuPriority"] = ride.build_menu_priority

    rf = ride.flags
    if rf & RideFlag.NO_COLLISION_CRASHES:
        properties["noCollisionCrashes"] = True
    if rf & RideFlag.RIDER_CONTROLS_SPEED:
        properties["riderControlsSpeed"] = True

    car_color_presets: list[list[list[str]]] = []
    for preset in ride.colors:
        car_color_presets.append([[COLOR_NAMES[idx] for idx in preset]])
    properties["carColours"] = car_color_presets

    cars = []
    for vehicle in ride.vehicles:
        car: dict[str, Any] = {}
        car["rotationFrameMask"] = 31
        car["spacing"] = int((vehicle.spacing * 278912) / TILE_SIZE)
        car["mass"] = vehicle.mass
        car["numSeats"] = vehicle.num_riders
        car["numSeatRows"] = len(vehicle.riders)

        friction = (FRICTION_SOUND_IDS[ride.running_sound]
                    if ride.running_sound < len(FRICTION_SOUND_IDS) else 0)
        car["frictionSoundId"] = friction
        car["soundRange"] = ride.secondary_sound
        car["drawOrder"] = vehicle.draw_order

        car["spriteGroups"] = _emit_sprite_groups(ride.sprite_flags, vehicle.flags)

        vf = vehicle.flags
        if vf & VehicleFlag.SECONDARY_REMAP:
            car["hasAdditionalColour1"] = True
        if vf & VehicleFlag.TERTIARY_REMAP:
            car["hasAdditionalColour2"] = True
        if vf & VehicleFlag.RIDERS_SCREAM:
            car["hasScreamingRiders"] = True

        loading: list[int] = []
        for rider in vehicle.riders:
            pos_x = float(rider.meshes[0][0].position[0])
            position = int(round(32.0 * pos_x / TILE_SIZE))
            if vehicle.num_riders > 1:
                loading.append(position - 1)
                loading.append(position + 1)
            else:
                loading.append(position)
        car["loadingPositions"] = loading
        cars.append(car)
    properties["cars"] = cars
    out["properties"] = properties

    strings = {
        "name": {"en-GB": ride.name},
        "description": {"en-GB": ride.description},
        "capacity": {"en-GB": ride.capacity},
    }
    out["strings"] = strings
    return out


# ---------------------------------------------------------------------------
# Sprite rendering orchestration
# ---------------------------------------------------------------------------

def _add_model_to_context(ride: Ride, context: Context, model: Model,
                          frame: int, mask: int) -> None:
    for mesh_frames in model.meshes:
        mf = mesh_frames[frame]
        if mf.mesh_index == -1:
            continue
        # Orientation order matches ProjectExporter.cpp:
        #   rotate_y(deg2rad(orientation.x))
        # * rotate_z(deg2rad(orientation.y))
        # * rotate_x(deg2rad(orientation.z))
        rx, ry, rz = (mf.orientation * math.pi / 180.0)
        matrix = (rotate_y_local(rx)
                  @ rotate_z_local(ry)
                  @ rotate_x_local(rz))
        translation = mf.position.astype(np.float64)
        context.add_model(ride.meshes[mf.mesh_index], matrix, translation, mask)


# Local copies to avoid importing the public names twice.
def rotate_x_local(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float64)


def rotate_y_local(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float64)


def rotate_z_local(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)


def _render_sprites(ride: Ride, context: Context,
                    object_dir: Path) -> list[dict[str, Any]]:
    images_json: list[dict[str, Any]] = []

    # Preview image.
    preview_dir = object_dir / "images"
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / "preview.png"
    write_png(ride.preview, preview_path)
    for _ in range(3):
        images_json.append(_make_image_object(
            "images/preview.png", 0, 0, -1, -1, -1, -1))

    for i, vehicle in enumerate(ride.vehicles):
        sf = ride.sprite_flags
        vf = vehicle.flags
        num_frames = 4 if (vf & VehicleFlag.RESTRAINT_ANIMATION) else 1
        num_car_images = count_sprites(sf, vf)
        num_total = num_car_images * (1 + len(vehicle.riders))

        all_images = [None] * num_total

        print("Rendering car sprites")
        base = 0
        for frame in range(num_frames):
            context.begin_render()
            _add_model_to_context(ride, context, vehicle.model, frame, 0)
            context.finalize_render()
            frame_imgs = render_vehicle_frame(context, sf, frame, base_seed=base)
            for k, img in enumerate(frame_imgs):
                all_images[base + k] = img
            base += len(frame_imgs)
            context.end_render()

        for j, rider in enumerate(vehicle.riders):
            print(f"Rendering peep sprites {j}")
            base = 0
            for frame in range(num_frames):
                context.begin_render()
                _add_model_to_context(ride, context, vehicle.model, frame, 1)
                for k in range(j):
                    _add_model_to_context(ride, context, vehicle.riders[k], frame, 1)
                _add_model_to_context(ride, context, rider, frame, 0)
                context.finalize_render()
                frame_imgs = render_vehicle_frame(context, sf, frame, base_seed=base + j * 100000)
                offset = (j + 1) * num_car_images + base
                for k, img in enumerate(frame_imgs):
                    all_images[offset + k] = img
                base += len(frame_imgs)
                context.end_render()

        atlas, x_coords, y_coords = create_atlas(all_images)
        image_path = f"images/car_{i}.png"
        for k, img in enumerate(all_images):
            images_json.append(_make_image_object(
                image_path,
                img.x_offset, img.y_offset,
                x_coords[k], y_coords[k],
                img.width, img.height))
        out_atlas = object_dir / image_path
        out_atlas.parent.mkdir(parents=True, exist_ok=True)
        write_png(atlas, out_atlas)
    return images_json


# ---------------------------------------------------------------------------
# .parkobj assembly
# ---------------------------------------------------------------------------

def _make_parkobj(ride: Ride, object_dir: Path, output_path: Path) -> None:
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(object_dir / "object.json", "object.json")
        zf.write(object_dir / "images/preview.png", "images/preview.png")
        for i in range(len(ride.vehicles)):
            arc = f"images/car_{i}.png"
            zf.write(object_dir / arc, arc)


def _clean_working_dir(ride: Ride, object_dir: Path) -> None:
    for p in [
        object_dir / "object.json",
        object_dir / "images/preview.png",
    ]:
        if p.exists():
            p.unlink()
    for i in range(len(ride.vehicles)):
        p = object_dir / f"images/car_{i}.png"
        if p.exists():
            p.unlink()


def export_ride(ride: Ride, context: Context, output_directory: Path | str,
                skip_render: bool = False) -> None:
    output_directory = Path(output_directory)
    object_dir = Path("object")
    object_dir.mkdir(exist_ok=True)
    (object_dir / "images").mkdir(exist_ok=True)

    ride_json = build_ride_json(ride)

    if skip_render:
        # Re-use the images array from a previous run.
        with open(object_dir / "object.json", "r") as f:
            prev = json.load(f)
        images_json = prev.get("images")
        if not isinstance(images_json, list):
            raise RuntimeError("Property \"images\" is not an array")
    else:
        _clean_working_dir(ride, object_dir)
        images_json = _render_sprites(ride, context, object_dir)

    ride_json["images"] = images_json

    with open(object_dir / "object.json", "w") as f:
        json.dump(ride_json, f, indent=4)

    output_directory.mkdir(parents=True, exist_ok=True)
    parkobj_path = output_directory / f"{ride.id}.parkobj"
    _make_parkobj(ride, object_dir, parkobj_path)


def export_ride_test(ride: Ride, context: Context, test_dir: Path | str = "test") -> None:
    """Single-viewpoint render for fast iteration."""
    test_dir = Path(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    for i, vehicle in enumerate(ride.vehicles):
        vf = vehicle.flags
        num_frames = 4 if (vf & VehicleFlag.RESTRAINT_ANIMATION) else 1
        for j in range(num_frames):
            print(f"Rendering vehicle {i} frame {j}")
            context.begin_render()
            _add_model_to_context(ride, context, vehicle.model, j, 0)
            for rider in vehicle.riders:
                _add_model_to_context(ride, context, rider, j, 0)
            context.finalize_render()
            img = render_view(context, rotate_y(math.pi))
            context.end_render()
            write_png(img, test_dir / f"car_{i}_{j}.png")
