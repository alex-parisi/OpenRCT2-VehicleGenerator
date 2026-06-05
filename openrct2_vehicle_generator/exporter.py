"""
Build object.json and assemble the .parkobj ZIP.
"""

import logging
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from openrct2_object_common.objectjson import object_json_header
from openrct2_object_common.parkobj import assemble_parkobj, write_images_dat_lgx
from openrct2_object_common.placement import add_model_to_scene
from openrct2_x7_renderer.geometry import rotate_y
from openrct2_x7_renderer.image import write_png
from openrct2_x7_renderer.ray_trace import Context
from openrct2_x7_renderer.remap import REMAP_COLOR_RAMPS, REMAP_WINDOWS
from openrct2_x7_renderer.types import IndexedImage

from .constants import (
    CAR_SLOT_ABSENT,
    CATEGORY_NAMES,
    COLOR_NAMES,
    FRICTION_SOUND_IDS,
    CarIndex,
    RideFlag,
    VehicleFlag,
    frames_for,
)
from .sprite_renderer import render_vehicle_frame, sprite_group_counts
from .types import Ride

log = logging.getLogger(__name__)


def build_ride_json(ride: Ride) -> dict[str, Any]:
    out = object_json_header(
        ride.id,
        object_type="ride",
        original_id=ride.original_id,
        version=ride.version,
        authors=ride.authors,
    )

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
    if front != CAR_SLOT_ABSENT:
        properties["headCars"] = front
    rear = ride.configuration[CarIndex.REAR]
    if rear != CAR_SLOT_ABSENT:
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

        car["spriteGroups"] = sprite_group_counts(ride.sprite_flags, vehicle.flags)

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
            # A 2-across row emits a left/right pair; a single-seat row emits one
            # entry. Key off this row's own width, not the car's total seat count,
            # so a car with several single-seat rows doesn't double its positions.
            if len(rider.meshes) > 1:
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


def _render_sprites(
    ride: Ride,
    context: Context,
    object_dir: Path,
    progress: Callable[[int, int], None] | None = None,
) -> list:
    """
    Render every sprite for the ride and write a single `images.dat`.

    If ``progress`` is given it is called as ``progress(done, total)`` after each
    rendered frame, where the unit of work is one ``render_vehicle_frame`` call.
    """
    all_images: list = []

    # Three preview entries
    all_images.extend([ride.preview] * 3)

    # One unit of work per rendered frame (car frames plus a full frame set per
    # rider), so the caller can drive a determinate progress bar.
    total_steps = sum(
        frames_for(v.flags) * (1 + len(v.riders)) for v in ride.vehicles
    )
    step = 0

    def _tick() -> None:
        nonlocal step
        step += 1
        if progress is not None:
            progress(step, total_steps)

    for i, vehicle in enumerate(ride.vehicles):
        sf = ride.sprite_flags
        vf = vehicle.flags
        num_frames = frames_for(vf)
        # Set by the loader via count_sprites; reused here so the declared count
        # and the rendered set come from a single computation.
        num_car_images = vehicle.num_sprites
        num_total = num_car_images * (1 + len(vehicle.riders))

        car_images: list = [None] * num_total

        log.info("Rendering vehicle %d car sprites", i)
        base = 0
        for frame in range(num_frames):
            builder = context.begin_render()
            add_model_to_scene(builder, ride.meshes, vehicle.model, frame=frame, mask=0)
            scene = builder.finalize()
            frame_imgs = render_vehicle_frame(scene, sf, frame)
            for k, img in enumerate(frame_imgs):
                car_images[base + k] = img
            base += len(frame_imgs)
            scene.end_render()
            _tick()

        for j, rider in enumerate(vehicle.riders):
            log.info("Rendering vehicle %d peep sprites %d", i, j)
            base = 0
            for frame in range(num_frames):
                builder = context.begin_render()
                add_model_to_scene(builder, ride.meshes, vehicle.model, frame=frame, mask=1)
                for k in range(j):
                    add_model_to_scene(builder, ride.meshes, vehicle.riders[k], frame=frame, mask=1)
                add_model_to_scene(builder, ride.meshes, rider, frame=frame, mask=0)
                scene = builder.finalize()
                frame_imgs = render_vehicle_frame(scene, sf, frame)
                offset = (j + 1) * num_car_images + base
                for k, img in enumerate(frame_imgs):
                    car_images[offset + k] = img
                base += len(frame_imgs)
                scene.end_render()
                _tick()

        all_images.extend(car_images)

    return write_images_dat_lgx(all_images, object_dir)


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
    progress: Callable[[int, int], None] | None = None,
) -> None:
    """
    Render and assemble a .parkobj using explicit, caller-chosen paths.

    ``progress``, if given, is forwarded to :func:`_render_sprites` and called
    as ``progress(done, total)`` as rendering advances.
    """
    def _render(wd: Path) -> list[str]:
        # Sweep stale per-PNG output from older runs (assemble_parkobj has
        # already removed object.json / images.dat before calling this).
        _clean_working_dir(wd)
        return _render_sprites(ride, context, wd, progress)

    assemble_parkobj(
        build_ride_json(ride),
        Path(parkobj_path),
        Path(work_dir),
        _render,
        skip_render=skip_render,
    )


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


def _preview_remap_overrides(ride: Ride) -> dict[int, tuple[int, ...]]:
    """Map the ride's first colour preset onto the renderer's remap regions.

    A preview render normally shows the raw remap windows — the greyscale
    "company colour" ramps OpenRCT2 repaints at draw time. Substituting the
    first preset's colours (region 1 = main, 2 = additional 1, 3 = additional 2)
    lets the preview show the vehicle in its default repaint colours. Returns an
    empty dict when the ride defines no presets, leaving the windows untouched.
    """
    if not ride.colors:
        return {}
    preset = ride.colors[0]
    return {
        region: REMAP_COLOR_RAMPS[COLOR_NAMES[color_index]]
        for region, color_index in zip(sorted(REMAP_WINDOWS), preset, strict=False)
    }


def combine_indexed_images(images: list[IndexedImage], columns: int = 2) -> IndexedImage:
    """Tile IndexedImages into a single grid image, aligned by draw offset.

    Each cell spans the union of every image's draw-offset bounding box, so a
    shared sprite anchor lands at the same spot in every cell and the rotated
    views line up. Cells fill left-to-right, top-to-bottom over a transparent
    (palette index 0) background; ``columns`` is capped at the image count so a
    single image doesn't leave a blank cell. Used to show all four rotated
    preview directions in one image.
    """
    if not images:
        return IndexedImage.blank(1, 1)
    columns = max(1, min(columns, len(images)))
    left = min(im.x_offset for im in images)
    top = min(im.y_offset for im in images)
    cell_w = max(im.x_offset + im.width for im in images) - left
    cell_h = max(im.y_offset + im.height for im in images) - top
    rows = math.ceil(len(images) / columns)
    canvas = np.zeros((rows * cell_h, columns * cell_w), dtype=np.uint8)
    for idx, im in enumerate(images):
        row, col = divmod(idx, columns)
        x = col * cell_w + (im.x_offset - left)
        y = row * cell_h + (im.y_offset - top)
        canvas[y : y + im.height, x : x + im.width] = im.pixels
    return IndexedImage(
        width=canvas.shape[1],
        height=canvas.shape[0],
        x_offset=0,
        y_offset=0,
        pixels=canvas,
    )


def export_ride_test(ride: Ride, context: Context, test_dir: Path | str = "test") -> None:
    """Four-direction render for fast iteration.

    Renders each vehicle frame at the four park-view rotations and tiles them
    into one 2x2 preview per frame, so the test sprite shows every direction the
    car is displayed at. Recolours the preview using the ride's first colour
    preset so the remap windows show their repaint colours; with no presets the
    windows are left raw.
    """
    context.remap_overrides = _preview_remap_overrides(ride)
    test_dir = Path(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    # The first view (yaw = pi) matches the old single-direction preview; the
    # other three step a quarter turn each — the four rotations OpenRCT2 cycles
    # through as the park view is rotated.
    yaws = [math.pi + d * math.pi / 2 for d in range(4)]
    for i, vehicle in enumerate(ride.vehicles):
        num_frames = frames_for(vehicle.flags)
        for j in range(num_frames):
            log.info("Rendering vehicle %d frame %d", i, j)
            builder = context.begin_render()
            add_model_to_scene(builder, ride.meshes, vehicle.model, frame=j, mask=0)
            for rider in vehicle.riders:
                add_model_to_scene(builder, ride.meshes, rider, frame=j, mask=0)
            scene = builder.finalize()
            views = [scene.render_view(rotate_y(yaw)) for yaw in yaws]
            scene.end_render()
            write_png(combine_indexed_images(views, columns=2), test_dir / f"car_{i}_{j}.png")
