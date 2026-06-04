"""
Build object.json and assemble the .parkobj ZIP.
"""

import json
import logging
import math
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
from openrct2_x7_renderer.image import write_png
from openrct2_x7_renderer.images_dat import write_images_dat
from openrct2_x7_renderer.ray_trace import Context, render_view, rotate_x, rotate_y, rotate_z

from .constants import (
    CATEGORY_NAMES,
    COLOR_NAMES,
    FRICTION_SOUND_IDS,
    CarIndex,
    RideFlag,
    SpriteFlag,
    VehicleFlag,
)
from .sprite_renderer import render_vehicle_frame
from .types import Model, Ride

log = logging.getLogger(__name__)


def _emit_sprite_groups(sf: int, vf: int) -> dict[str, int]:
    out: dict[str, int] = {}
    if sf & SpriteFlag.FLAT_SLOPE:
        out["slopeFlat"] = 32
    if sf & SpriteFlag.GENTLE_SLOPE:
        out["slopes12"] = 4
        out["slopes25"] = 32
    if sf & SpriteFlag.STEEP_SLOPE:
        out["slopes42"] = 8
        out["slopes60"] = 32
    if sf & SpriteFlag.VERTICAL_SLOPE:
        out["slopes75"] = 4
        out["slopes90"] = 32
        out["slopesLoop"] = 4
        out["slopeInverted"] = 4
    if sf & SpriteFlag.DIAGONAL_SLOPE:
        out["slopes8"] = 4
        out["slopes16"] = 4
        out["slopes50"] = 4
    if sf & SpriteFlag.BANKING:
        out["flatBanked22"] = 8
        out["flatBanked45"] = 32
    if sf & SpriteFlag.INLINE_TWIST:
        out["flatBanked67"] = 4
        out["flatBanked90"] = 4
        out["inlineTwists"] = 4
    if sf & SpriteFlag.SLOPE_BANK_TRANSITION:
        out["slopes12Banked22"] = 32
    if sf & SpriteFlag.DIAGONAL_BANK_TRANSITION:
        out["slopes8Banked22"] = 4
    if sf & SpriteFlag.SLOPED_BANK_TRANSITION:
        out["slopes25Banked22"] = 4
    if sf & SpriteFlag.DIAGONAL_SLOPED_BANK_TRANSITION:
        out["slopes8Banked45"] = 4
        out["slopes16Banked22"] = 4
        out["slopes16Banked45"] = 4
    if sf & SpriteFlag.SLOPED_BANKED_TURN:
        out["slopes25Banked45"] = 32
    if sf & SpriteFlag.BANKED_SLOPE_TRANSITION:
        out["slopes12Banked45"] = 4
    if sf & SpriteFlag.ZERO_G_ROLL:
        out["slopes25Banked67"] = 4
        out["slopes25Banked90"] = 4
        out["slopes25InlineTwists"] = 4
        out["slopes42Banked22"] = 4
        out["slopes42Banked45"] = 4
        out["slopes42Banked67"] = 4
        out["slopes42Banked90"] = 4
        out["slopes60Banked22"] = 8 if (sf & SpriteFlag.DIVE_LOOP) else 4
    if sf & SpriteFlag.DIVE_LOOP:
        out["slopes50Banked45"] = 8
        out["slopes50Banked67"] = 8
        out["slopes50Banked90"] = 8
    if sf & SpriteFlag.CORKSCREW:
        out["corkscrews"] = 4
    if vf & VehicleFlag.RESTRAINT_ANIMATION:
        out["restraintAnimation"] = 4
    return out


def build_ride_json(ride: Ride) -> dict[str, Any]:
    out: dict[str, Any] = {"id": ride.id}
    if ride.original_id:
        out["originalId"] = ride.original_id
    out["version"] = ride.version

    out["authors"] = list(ride.authors)
    out["objectType"] = "ride"

    properties: dict[str, Any] = {
        "type": [ride.ride_type],
        "category": CATEGORY_NAMES[ride.category],
        "minCarsPerTrain": ride.min_cars_per_train,
        "maxCarsPerTrain": ride.max_cars_per_train,
        "numEmptyCars": ride.zero_cars,
        "tabCar": ride.tab_car,
        "defaultCar": ride.configuration[CarIndex.DEFAULT],
    }
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
        car: dict[str, Any] = {
            "rotationFrameMask": 31,
            "spacing": int((vehicle.spacing * 278912) / ride.units_per_tile),
            "mass": vehicle.mass,
            "numSeats": vehicle.num_riders,
            "numSeatRows": len(vehicle.riders),
        }

        friction = (
            FRICTION_SOUND_IDS[ride.running_sound]
            if ride.running_sound < len(FRICTION_SOUND_IDS)
            else 0
        )
        car["frictionSoundId"] = friction
        car["soundRange"] = ride.secondary_sound
        car["effectVisual"] = vehicle.effect_visual
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
            position = int(round(32.0 * pos_x / ride.units_per_tile))
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


def _add_model_to_context(
    ride: Ride, context: Context, model: Model, frame: int, mask: int
) -> None:
    for mesh_frames in model.meshes:
        mf = mesh_frames[frame]
        if mf.mesh_index == -1:
            continue
        rx, ry, rz = mf.orientation * math.pi / 180.0
        matrix = rotate_y(rx) @ rotate_z(ry) @ rotate_x(rz)
        translation = mf.position.astype(np.float64)
        context.add_model(ride.meshes[mf.mesh_index], matrix, translation, mask)


def _render_sprites(ride: Ride, context: Context, object_dir: Path) -> list:
    """
    Render every sprite for the ride and write a single `images.dat`.
    """
    all_images: list = []

    # Three preview entries
    all_images.extend([ride.preview] * 3)

    for i, vehicle in enumerate(ride.vehicles):
        sf = ride.sprite_flags
        vf = vehicle.flags
        num_frames = 4 if (vf & VehicleFlag.RESTRAINT_ANIMATION) else 1
        # Set by the loader via count_sprites; reused here so the declared count
        # and the rendered set come from a single computation.
        num_car_images = vehicle.num_sprites
        num_total = num_car_images * (1 + len(vehicle.riders))

        car_images: list = [None] * num_total

        log.info("Rendering vehicle %d car sprites", i)
        base = 0
        for frame in range(num_frames):
            context.begin_render()
            _add_model_to_context(ride, context, vehicle.model, frame, 0)
            context.finalize_render()
            frame_imgs = render_vehicle_frame(context, sf, frame)
            for k, img in enumerate(frame_imgs):
                car_images[base + k] = img
            base += len(frame_imgs)
            context.end_render()

        for j, rider in enumerate(vehicle.riders):
            log.info("Rendering vehicle %d peep sprites %d", i, j)
            base = 0
            for frame in range(num_frames):
                context.begin_render()
                _add_model_to_context(ride, context, vehicle.model, frame, 1)
                for k in range(j):
                    _add_model_to_context(ride, context, vehicle.riders[k], frame, 1)
                _add_model_to_context(ride, context, rider, frame, 0)
                context.finalize_render()
                frame_imgs = render_vehicle_frame(context, sf, frame)
                offset = (j + 1) * num_car_images + base
                for k, img in enumerate(frame_imgs):
                    car_images[offset + k] = img
                base += len(frame_imgs)
                context.end_render()

        all_images.extend(car_images)

    out_path = object_dir / "images.dat"
    write_images_dat(all_images, out_path)
    log.info(
        "wrote %s (%d sprites, %.1f KB)",
        out_path,
        len(all_images),
        out_path.stat().st_size / 1024,
    )
    return [f"$LGX:images.dat[0..{len(all_images) - 1}]"]


def _make_parkobj(object_dir: Path, output_path: Path) -> None:
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(object_dir / "object.json", "object.json")
        zf.write(object_dir / "images.dat", "images.dat")


def _clean_working_dir(object_dir: Path) -> None:
    for p in (object_dir / "object.json", object_dir / "images.dat"):
        p.unlink(missing_ok=True)
    # Also sweep any leftover per-PNG output from older runs.
    images_dir = object_dir / "images"
    if images_dir.exists():
        for p in images_dir.glob("*.png"):
            p.unlink()


def export_ride_to(
    ride: Ride,
    context: Context,
    parkobj_path: Path | str,
    work_dir: Path | str,
    skip_render: bool = False,
) -> None:
    """
    Render and assemble a .parkobj using explicit, caller-chosen paths.
    """
    parkobj_path = Path(parkobj_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    ride_json = build_ride_json(ride)

    if skip_render:
        # Re-use the images array from a previous run.
        prev = json.loads((work_dir / "object.json").read_text())
        images_json = prev.get("images")
        if not isinstance(images_json, list):
            raise RuntimeError('Property "images" is not an array')
    else:
        _clean_working_dir(work_dir)
        images_json = _render_sprites(ride, context, work_dir)

    ride_json["images"] = images_json

    (work_dir / "object.json").write_text(json.dumps(ride_json, indent=4))

    parkobj_path.parent.mkdir(parents=True, exist_ok=True)
    _make_parkobj(work_dir, parkobj_path)


def export_ride(
    ride: Ride, context: Context, output_directory: Path | str, skip_render: bool = False
) -> None:
    output_directory = Path(output_directory)
    export_ride_to(
        ride,
        context,
        output_directory / f"{ride.id}.parkobj",
        Path("object"),
        skip_render=skip_render,
    )


def export_ride_test(ride: Ride, context: Context, test_dir: Path | str = "test") -> None:
    """Single-viewpoint render for fast iteration."""
    test_dir = Path(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    for i, vehicle in enumerate(ride.vehicles):
        vf = vehicle.flags
        num_frames = 4 if (vf & VehicleFlag.RESTRAINT_ANIMATION) else 1
        for j in range(num_frames):
            log.info("Rendering vehicle %d frame %d", i, j)
            context.begin_render()
            _add_model_to_context(ride, context, vehicle.model, j, 0)
            for rider in vehicle.riders:
                _add_model_to_context(ride, context, rider, j, 0)
            context.finalize_render()
            img = render_view(context, rotate_y(math.pi))
            context.end_render()
            write_png(img, test_dir / f"car_{i}_{j}.png")
