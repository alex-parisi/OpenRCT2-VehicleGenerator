"""
Build object.json and assemble the .parkobj ZIP.
"""


import json
import math
import struct
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from .constants import (
    CATEGORY_NAMES,
    COLOR_NAMES,
    FRICTION_SOUND_IDS,
    TILE_SIZE,
    CarIndex,
    RideFlag,
    SpriteFlag,
    VehicleFlag,
)
from .image import write_png
from .ray_trace import Context, render_view, rotate_x, rotate_y, rotate_z
from .sprite_renderer import count_sprites, render_vehicle_frame
from .types import Model, Ride

# ---------------------------------------------------------------------------
# object.json construction
# ---------------------------------------------------------------------------

def _emit_sprite_groups(sf: int, vf: int) -> dict[str, int]:
    out: dict[str, int] = {}

    def add(key: str, n: int) -> None:
        out[key] = n

    if sf & SpriteFlag.FLAT_SLOPE:
        add("slopeFlat", 32)
    if sf & SpriteFlag.GENTLE_SLOPE:
        add("slopes12", 4)
        add("slopes25", 32)
    if sf & SpriteFlag.STEEP_SLOPE:
        add("slopes42", 8)
        add("slopes60", 32)
    if sf & SpriteFlag.VERTICAL_SLOPE:
        add("slopes75", 4)
        add("slopes90", 32)
        add("slopesLoop", 4)
        add("slopeInverted", 4)
    if sf & SpriteFlag.DIAGONAL_SLOPE:
        add("slopes8", 4)
        add("slopes16", 4)
        add("slopes50", 4)
    if sf & SpriteFlag.BANKING:
        add("flatBanked22", 8)
        add("flatBanked45", 32)
    if sf & SpriteFlag.INLINE_TWIST:
        add("flatBanked67", 4)
        add("flatBanked90", 4)
        add("inlineTwists", 4)
    if sf & SpriteFlag.SLOPE_BANK_TRANSITION:
        add("slopes12Banked22", 32)
    if sf & SpriteFlag.DIAGONAL_BANK_TRANSITION:
        add("slopes8Banked22", 4)
    if sf & SpriteFlag.SLOPED_BANK_TRANSITION:
        add("slopes25Banked22", 4)
    if sf & SpriteFlag.DIAGONAL_SLOPED_BANK_TRANSITION:
        add("slopes8Banked45", 4)
        add("slopes16Banked22", 4)
        add("slopes16Banked45", 4)
    if sf & SpriteFlag.SLOPED_BANKED_TURN:
        add("slopes25Banked45", 32)
    if sf & SpriteFlag.BANKED_SLOPE_TRANSITION:
        add("slopes12Banked45", 4)
    if sf & SpriteFlag.ZERO_G_ROLL:
        add("slopes25Banked67", 4)
        add("slopes25Banked90", 4)
        add("slopes25InlineTwists", 4)
        add("slopes42Banked22", 4)
        add("slopes42Banked45", 4)
        add("slopes42Banked67", 4)
        add("slopes42Banked90", 4)
        add("slopes60Banked22", 8 if (sf & SpriteFlag.DIVE_LOOP) else 4)
    if sf & SpriteFlag.DIVE_LOOP:
        add("slopes50Banked45", 8)
        add("slopes50Banked67", 8)
        add("slopes50Banked90", 8)
    if sf & SpriteFlag.CORKSCREW:
        add("corkscrews", 4)
    if vf & VehicleFlag.RESTRAINT_ANIMATION:
        add("restraintAnimation", 4)
    return out


# OpenRCT2 G1 image flag bits. We only ever emit BMP (raw indexed pixel
# data, no compression). RLE (0x0008) would be more compact but requires
# encoding transparent runs / visible runs per scanline; not implemented.
_G1_FLAG_BMP = 0x0001


def _write_images_dat(images: list, out_path: Path) -> None:
    """Write a sequence of IndexedImages as an OpenRCT2 `images.dat` (G1) blob.

    Format (matches the vanilla parkobj's `images.dat`):
      - Header (8 bytes): u32 num_entries, u32 total_pixel_data_size.
      - num_entries * 16-byte G1 elements:
          u32 offset (into the pixel data section),
          i16 width, i16 height, i16 x_offset, i16 y_offset,
          u16 flags, u16 zoom (we always write 0).
      - Concatenated pixel data: each image is width*height bytes of
        palette indices, with index 0 acting as transparent.

    The matching `object.json` `images` entry is the single string
    `"$LGX:images.dat[0..N-1]"`.
    """
    num = len(images)
    offsets: list[int] = []
    chunks: list[bytes] = []
    cur = 0
    for img in images:
        pixels = img.pixels.tobytes()  # uint8 (H, W) row-major
        assert len(pixels) == img.width * img.height, (
            f"sprite pixel buffer size mismatch: "
            f"got {len(pixels)}, expected {img.width}*{img.height}")
        offsets.append(cur)
        chunks.append(pixels)
        cur += len(pixels)
    total_pixel_size = cur

    elements = bytearray()
    for img, offset in zip(images, offsets, strict=False):
        elements += struct.pack(
            "<IhhhhHH",
            offset,
            int(img.width),
            int(img.height),
            int(img.x_offset),
            int(img.y_offset),
            _G1_FLAG_BMP,
            0,
        )

    with open(out_path, "wb") as f:
        f.write(struct.pack("<II", num, total_pixel_size))
        f.write(bytes(elements))
        f.writelines(chunks)


def build_ride_json(ride: Ride) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["id"] = ride.id
    if ride.original_id:
        out["originalId"] = ride.original_id
    out["version"] = ride.version

    out["authors"] = list(ride.authors)
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
        matrix = rotate_y(rx) @ rotate_z(ry) @ rotate_x(rz)
        translation = mf.position.astype(np.float64)
        context.add_model(ride.meshes[mf.mesh_index], matrix, translation, mask)



def _render_sprites(ride: Ride, context: Context, object_dir: Path) -> list:
    """Render every sprite for the ride and write a single `images.dat`.

    Returns the `images` JSON value to embed in object.json — a one-element
    list containing the `$LGX:images.dat[0..N-1]` reference. Matches the
    vanilla parkobj format and loads ~50x faster than per-PNG output in
    OpenRCT2's object picker.
    """
    all_images: list = []

    # Three preview entries (same image, three copies in the blob — that's
    # how vanilla parkobjs are laid out; OpenRCT2 references them at
    # specific indices for the build-menu icon stack).
    all_images.extend([ride.preview] * 3)

    for i, vehicle in enumerate(ride.vehicles):
        sf = ride.sprite_flags
        vf = vehicle.flags
        num_frames = 4 if (vf & VehicleFlag.RESTRAINT_ANIMATION) else 1
        num_car_images = count_sprites(sf, vf)
        num_total = num_car_images * (1 + len(vehicle.riders))

        car_images: list = [None] * num_total

        print(f"Rendering vehicle {i} car sprites")
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
            print(f"Rendering vehicle {i} peep sprites {j}")
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
    _write_images_dat(all_images, out_path)
    print(f"wrote {out_path} ({len(all_images)} sprites, "
          f"{out_path.stat().st_size / 1024:.1f} KB)")
    return [f"$LGX:images.dat[0..{len(all_images) - 1}]"]


# ---------------------------------------------------------------------------
# .parkobj assembly
# ---------------------------------------------------------------------------

def _make_parkobj(ride: Ride, object_dir: Path, output_path: Path) -> None:
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(object_dir / "object.json", "object.json")
        zf.write(object_dir / "images.dat", "images.dat")


def _clean_working_dir(ride: Ride, object_dir: Path) -> None:
    for p in (object_dir / "object.json", object_dir / "images.dat"):
        p.unlink(missing_ok=True)
    # Also sweep any leftover per-PNG output from older runs.
    images_dir = object_dir / "images"
    if images_dir.exists():
        for p in images_dir.glob("*.png"):
            p.unlink()


def export_ride(ride: Ride, context: Context, output_directory: Path | str,
                skip_render: bool = False) -> None:
    output_directory = Path(output_directory)
    object_dir = Path("object")
    object_dir.mkdir(exist_ok=True)

    ride_json = build_ride_json(ride)

    if skip_render:
        # Re-use the images array from a previous run.
        prev = json.loads((object_dir / "object.json").read_text())
        images_json = prev.get("images")
        if not isinstance(images_json, list):
            raise RuntimeError("Property \"images\" is not an array")
    else:
        _clean_working_dir(ride, object_dir)
        images_json = _render_sprites(ride, context, object_dir)

    ride_json["images"] = images_json

    (object_dir / "object.json").write_text(json.dumps(ride_json, indent=4))

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
