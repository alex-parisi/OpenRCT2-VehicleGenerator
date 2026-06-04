"""Tests for object.json construction, images.dat emission, and .parkobj zipping.

The native ray tracer is stubbed out via a fake render context that mirrors the
renderer's begin_render -> SceneBuilder -> FinalizedScene flow: every view
renders a 1x1 dummy and the lifecycle (begin/add/finalize/end) is recorded.
Everything downstream of the pixels -- write_images_dat, write_png, the zip --
runs for real against tmp_path.
"""

import json
import zipfile

import pytest
from openrct2_vehicle_generator.constants import CarIndex, Category, RunningSound
from openrct2_vehicle_generator.exporter import (
    build_ride_json,
    export_ride,
    export_ride_test,
    export_ride_to,
)
from openrct2_vehicle_generator.loader import build_ride
from openrct2_vehicle_generator.types import IndexedImage, MeshFrame, Model, Ride, Vehicle
from openrct2_x7_renderer.mesh import load_mesh


class FakeScene:
    """Stands in for a FinalizedScene; every view renders a 1x1 dummy."""

    def __init__(self, events):
        self._events = events

    def render_view(self, _view):
        return IndexedImage.blank(1, 1)

    def end_render(self):
        self._events.append("end")


class FakeBuilder:
    """Stands in for a SceneBuilder, recording add_model/finalize calls."""

    def __init__(self, events):
        self._events = events

    def add_model(self, mesh, matrix, translation, mask):
        self._events.append(("add", mask))
        return self

    def finalize(self):
        self._events.append("finalize")
        return FakeScene(self._events)


class FakeContext:
    """Records the render lifecycle calls without touching Embree."""

    def __init__(self):
        self.events = []

    def begin_render(self):
        self.events.append("begin")
        return FakeBuilder(self.events)


_OBJ = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"


def _build(tmp_path, **overrides):
    """Build a Ride through the loader's in-memory seam with a real mesh."""
    (tmp_path / "m.obj").write_text(_OBJ)
    base = {
        "id": "test.ride.x",
        "name": "X",
        "description": "desc",
        "capacity": "1 passenger",
        "ride_type": "classic_wooden_rc",
        "sprites": ["flat"],
        "min_cars_per_train": 1,
        "max_cars_per_train": 4,
        "running_sound": "wooden",
        "secondary_sound": "scream1",
        "default_colors": [["bright_red", "black", "yellow"]],
        "meshes": [str(tmp_path / "m.obj")],
        "vehicles": [
            {"model": {"mesh_index": 0}, "mass": 100, "spacing": 2.0, "draw_order": 1}
        ],
    }
    base.update(overrides)
    meshes = [load_mesh(p) for p in base["meshes"]]
    return build_ride(base, meshes)


# --------------------------------------------------------------------------
# build_ride_json
# --------------------------------------------------------------------------


def test_build_ride_json_minimal_shape(tmp_path):
    ride = _build(tmp_path)
    out = build_ride_json(ride)
    assert out["id"] == "test.ride.x"
    assert out["objectType"] == "ride"
    assert "originalId" not in out
    props = out["properties"]
    assert props["type"] == ["classic_wooden_rc"]
    assert props["category"] == "rollercoaster"
    assert props["minCarsPerTrain"] == 1
    assert props["maxCarsPerTrain"] == 4
    assert props["defaultCar"] == 0
    # No front/rear configuration -> no headCars/tailCars.
    assert "headCars" not in props
    assert "tailCars" not in props
    assert props["carColours"] == [[["bright_red", "black", "yellow"]]]
    assert out["strings"]["name"]["en-GB"] == "X"
    car = props["cars"][0]
    assert car["rotationFrameMask"] == 31
    assert car["loadingPositions"] == []  # no riders


def test_build_ride_json_original_id_and_version(tmp_path):
    ride = _build(tmp_path, original_id="rct2.ride.x", version="2.0")
    out = build_ride_json(ride)
    assert out["originalId"] == "rct2.ride.x"
    assert out["version"] == "2.0"


def test_build_ride_json_head_and_tail_cars(tmp_path):
    ride = _build(tmp_path, configuration={"default": 0, "front": 1, "rear": 2})
    props = build_ride_json(ride)["properties"]
    assert props["headCars"] == 1
    assert props["tailCars"] == 2


def test_build_ride_json_ride_flags(tmp_path):
    ride = _build(tmp_path, flags=["no_collision_crashes", "rider_controls_speed"])
    props = build_ride_json(ride)["properties"]
    assert props["noCollisionCrashes"] is True
    assert props["riderControlsSpeed"] is True


def test_build_ride_json_vehicle_flags(tmp_path):
    vehicle = {
        "model": {"mesh_index": 0},
        "mass": 100,
        "spacing": 2.0,
        "draw_order": 1,
        "flags": ["secondary_remap", "tertiary_remap", "riders_scream"],
    }
    ride = _build(tmp_path, vehicles=[vehicle])
    car = build_ride_json(ride)["properties"]["cars"][0]
    assert car["hasAdditionalColour1"] is True
    assert car["hasAdditionalColour2"] is True
    assert car["hasScreamingRiders"] is True


def test_build_ride_json_loading_positions_multi_rider(tmp_path):
    # A 2-across row yields position-1 and position+1 entries.
    vehicle = {
        "model": {"mesh_index": 0},
        "mass": 100,
        "spacing": 2.0,
        "draw_order": 1,
        "riders": [
            [
                {"mesh_index": 0, "position": [0.5, 0, -0.4]},
                {"mesh_index": 0, "position": [0.5, 0, 0.4]},
            ]
        ],
    }
    ride = _build(tmp_path, vehicles=[vehicle])
    car = build_ride_json(ride)["properties"]["cars"][0]
    assert car["numSeats"] == 2
    assert car["numSeatRows"] == 1
    assert len(car["loadingPositions"]) == 2


def test_build_ride_json_loading_positions_single_rider(tmp_path):
    vehicle = {
        "model": {"mesh_index": 0},
        "mass": 100,
        "spacing": 2.0,
        "draw_order": 1,
        "riders": [[{"mesh_index": 0, "position": [0.5, 0, 0.0]}]],
    }
    ride = _build(tmp_path, vehicles=[vehicle])
    car = build_ride_json(ride)["properties"]["cars"][0]
    assert car["numSeats"] == 1
    assert len(car["loadingPositions"]) == 1


def test_build_ride_json_unknown_running_sound_friction_falls_back_to_zero():
    # The else branch in build_ride_json: a running_sound index past the
    # FRICTION_SOUND_IDS table maps to friction 0. The loader can't emit this
    # (its enum guard caps the index), so build a Ride directly.
    ride = Ride()
    ride.id = "x.ride.y"
    ride.ride_type = "classic_wooden_rc"
    ride.category = int(Category.ROLLERCOASTER)
    ride.configuration = [0, 0xFF, 0xFF, 0xFF, 0xFF]
    ride.running_sound = 999
    ride.vehicles = [Vehicle(mass=1, spacing=1.0, model=Model(meshes=[[MeshFrame()]]))]
    car = build_ride_json(ride)["properties"]["cars"][0]
    assert car["frictionSoundId"] == 0


def test_build_ride_json_friction_lookup_for_known_sound(tmp_path):
    ride = _build(tmp_path, running_sound="steel")
    car = build_ride_json(ride)["properties"]["cars"][0]
    assert car["frictionSoundId"] == RunningSound.STEEL.value


def test_build_ride_json_sprite_groups_all_flags(tmp_path):
    # sprites="all" walks every branch of _emit_sprite_groups; restraint
    # animation adds the restraintAnimation group. DIVE_LOOP is on, so the
    # sb22 upgrade picks the 8-frame slopes60Banked22.
    vehicle = {
        "model": {"mesh_index": 0},
        "mass": 100,
        "spacing": 2.0,
        "draw_order": 1,
        "flags": ["restraint_animation"],
    }
    ride = _build(tmp_path, sprites="all", vehicles=[vehicle])
    groups = build_ride_json(ride)["properties"]["cars"][0]["spriteGroups"]
    assert groups["slopeFlat"] == 32
    assert groups["slopes60Banked22"] == 8  # DIVE_LOOP upgrade
    assert groups["corkscrews"] == 4
    assert groups["restraintAnimation"] == 4
    # Every declared group present and positive.
    assert all(v > 0 for v in groups.values())


def test_build_ride_json_sprite_groups_zero_g_without_dive_loop(tmp_path):
    # zero_g_rolls without dive_loops keeps slopes60Banked22 at the 4-frame size.
    ride = _build(tmp_path, sprites=["zero_g_rolls"])
    groups = build_ride_json(ride)["properties"]["cars"][0]["spriteGroups"]
    assert groups["slopes60Banked22"] == 4


# --------------------------------------------------------------------------
# Full render + export path
# --------------------------------------------------------------------------


def test_export_ride_to_writes_parkobj(tmp_path):
    ride = _build(tmp_path)
    ctx = FakeContext()
    parkobj = tmp_path / "out" / "ride.parkobj"
    work = tmp_path / "work"

    export_ride_to(ride, ctx, parkobj, work)

    assert parkobj.exists()
    with zipfile.ZipFile(parkobj) as zf:
        names = set(zf.namelist())
        assert names == {"object.json", "images.dat"}
        obj = json.loads(zf.read("object.json"))
    # 3 preview + 32 flat sprites for the single car -> images[0..34].
    assert obj["images"] == ["$LGX:images.dat[0..34]"]
    # The fake context saw a full begin/finalize/end cycle.
    assert "begin" in ctx.events and "finalize" in ctx.events and "end" in ctx.events
    assert (work / "images.dat").exists()


def test_export_ride_to_renders_riders_with_masks(tmp_path):
    # Two rider rows exercise the peep-sprite loop, the prior-row background
    # pass (rows < j are added at mask=1), and the mask=0 subject pass.
    vehicle = {
        "model": {"mesh_index": 0},
        "mass": 100,
        "spacing": 2.0,
        "draw_order": 1,
        "riders": [
            [{"mesh_index": 0, "position": [0.5, 0, 0.0]}],
            [{"mesh_index": 0, "position": [-0.5, 0, 0.0]}],
        ],
    }
    ride = _build(tmp_path, vehicles=[vehicle])
    ctx = FakeContext()
    export_ride_to(ride, ctx, tmp_path / "r.parkobj", tmp_path / "w")

    with zipfile.ZipFile(tmp_path / "r.parkobj") as zf:
        obj = json.loads(zf.read("object.json"))
    # 3 preview + (1 body + 2 rider rows) * 32 flat = 99 -> images[0..98].
    assert obj["images"] == ["$LGX:images.dat[0..98]"]
    masks = {e[1] for e in ctx.events if isinstance(e, tuple)}
    assert masks == {0, 1}


def test_export_ride_to_skip_render_reuses_images(tmp_path):
    ride = _build(tmp_path)
    ctx = FakeContext()
    work = tmp_path / "work"

    # First a real render to populate work/object.json + images.dat.
    export_ride_to(ride, ctx, tmp_path / "first.parkobj", work)

    # Then skip_render: no new render, the prior images array is reused.
    ctx2 = FakeContext()
    export_ride_to(ride, ctx2, tmp_path / "second.parkobj", work, skip_render=True)
    assert ctx2.events == []  # nothing rendered

    with zipfile.ZipFile(tmp_path / "second.parkobj") as zf:
        obj = json.loads(zf.read("object.json"))
    assert obj["images"] == ["$LGX:images.dat[0..34]"]


def test_export_ride_to_skip_render_rejects_non_array_images(tmp_path):
    ride = _build(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    (work / "object.json").write_text(json.dumps({"images": "not-an-array"}))
    with pytest.raises(RuntimeError, match="images"):
        export_ride_to(ride, FakeContext(), tmp_path / "x.parkobj", work, skip_render=True)


def test_clean_working_dir_sweeps_stale_pngs(tmp_path):
    # An old per-PNG run left images/*.png + a stale object.json/images.dat;
    # a fresh (non-skip) export must remove them before writing.
    ride = _build(tmp_path)
    work = tmp_path / "work"
    (work / "images").mkdir(parents=True)
    stale_png = work / "images" / "old.png"
    stale_png.write_text("stale")
    (work / "object.json").write_text("stale")

    export_ride_to(ride, FakeContext(), tmp_path / "out.parkobj", work)
    assert not stale_png.exists()


def test_export_ride_wrapper_names_by_id(tmp_path, monkeypatch):
    # export_ride derives the parkobj filename from ride.id and writes into the
    # given output directory; it uses a relative "object" work dir, so run from
    # tmp_path to keep the repo clean.
    ride = _build(tmp_path)
    monkeypatch.chdir(tmp_path)
    out_dir = tmp_path / "dist"

    export_ride(ride, FakeContext(), out_dir)
    assert (out_dir / "test.ride.x.parkobj").exists()


def test_export_ride_test_single_view_pngs(tmp_path):
    # The fast-iteration path renders one PNG per vehicle frame into test_dir.
    vehicle = {
        "model": {"mesh_index": 0},
        "mass": 100,
        "spacing": 2.0,
        "draw_order": 1,
        "riders": [[{"mesh_index": 0, "position": [0.5, 0, 0.0]}]],
    }
    ride = _build(tmp_path, vehicles=[vehicle])
    test_dir = tmp_path / "test"

    export_ride_test(ride, FakeContext(), test_dir)
    assert (test_dir / "car_0_0.png").exists()


def test_export_ride_test_restraint_animation_emits_four_frames(tmp_path):
    vehicle = {
        "flags": ["restraint_animation"],
        "model": {
            "mesh_index": 0,
            "orientation": [[0, 0, 0], [0, -30, 0], [0, -60, 0], [0, -90, 0]],
        },
        "mass": 100,
        "spacing": 2.0,
        "draw_order": 1,
    }
    ride = _build(tmp_path, vehicles=[vehicle])
    test_dir = tmp_path / "test"

    export_ride_test(ride, FakeContext(), test_dir)
    for frame in range(4):
        assert (test_dir / f"car_0_{frame}.png").exists()


def test_add_model_skips_absent_mesh_index(tmp_path):
    # mesh_index -1 means "no mesh this frame" -> add_model is never called.
    ride = _build(tmp_path)
    ride.vehicles[0].model.meshes[0][0] = MeshFrame(mesh_index=-1)
    ctx = FakeContext()
    export_ride_test(ride, ctx, tmp_path / "test")
    assert all(not (isinstance(e, tuple) and e[0] == "add") for e in ctx.events)


def test_configuration_index_enum_alignment():
    # build_ride_json indexes ride.configuration by CarIndex; guard the mapping.
    assert CarIndex.DEFAULT == 0
    assert CarIndex.FRONT == 1
    assert CarIndex.REAR == 3
