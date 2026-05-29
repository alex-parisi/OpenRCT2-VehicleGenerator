"""Tests for JSON -> Ride loading, validation, and implied sprite flags."""

import json

import numpy as np
import pytest
from openrct2_vehicle_generator.constants import Category, SpriteFlag
from openrct2_vehicle_generator.loader import LoadError, load_lights, load_ride

ALL_SPRITE_FLAGS = (1 << len(SpriteFlag)) - 1


def _make_ride(tmp_path, **overrides):
    (tmp_path / "m.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
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
        "vehicles": [{
            "model": {"mesh_index": 0},
            "mass": 100,
            "spacing": 2.0,
            "draw_order": 1,
        }],
    }
    base.update(overrides)
    path = tmp_path / "ride.json"
    path.write_text(json.dumps(base))
    return path


def test_load_yaml_config(tmp_path):
    # Same ride, authored as YAML with a comment and an anchor/alias shared
    # between two mesh entries. parse_config picks the parser by extension.
    (tmp_path / "m.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    yaml_text = f"""
# a comment, which JSON can't have
id: test.ride.yaml
name: Y
description: desc
capacity: 1 passenger
ride_type: classic_wooden_rc
sprites: [flat]
min_cars_per_train: 1
max_cars_per_train: 4
running_sound: wooden
secondary_sound: scream1
default_colors:
  - [bright_red, black, yellow]
meshes:
  - {tmp_path / "m.obj"}
_pos: &pos [1, 2, 3]
vehicles:
  - mass: 100
    spacing: 2.0
    draw_order: 1
    model:
      - {{ mesh_index: 0, position: *pos }}
"""
    path = tmp_path / "ride.yaml"
    path.write_text(yaml_text)
    ride = load_ride(path)
    assert ride.id == "test.ride.yaml"
    assert ride.ride_type == "classic_wooden_rc"
    assert np.allclose(ride.vehicles[0].model.meshes[0][0].position, [1, 2, 3])


def test_load_minimal_ride(tmp_path):
    ride = load_ride(_make_ride(tmp_path))
    assert ride.id == "test.ride.x"
    assert ride.ride_type == "classic_wooden_rc"
    assert len(ride.vehicles) == 1
    assert len(ride.meshes) == 1
    # Category is fixed to ROLLERCOASTER after the enum/name-table fix.
    assert ride.category == int(Category.ROLLERCOASTER)


def test_sprites_all_sets_every_bit(tmp_path):
    ride = load_ride(_make_ride(tmp_path, sprites="all"))
    assert ride.sprite_flags == ALL_SPRITE_FLAGS


def test_banking_implies_diagonal_bank_transition(tmp_path):
    ride = load_ride(_make_ride(tmp_path, sprites=["banked_turns"]))
    assert ride.sprite_flags & SpriteFlag.BANKING
    assert ride.sprite_flags & SpriteFlag.DIAGONAL_BANK_TRANSITION


def test_dive_loop_implies_zero_g(tmp_path):
    # Without zero-g, dive loops would over-declare the sprite count; the
    # loader must imply ZERO_G_ROLL.
    ride = load_ride(_make_ride(tmp_path, sprites=["dive_loops"]))
    assert ride.sprite_flags & SpriteFlag.DIVE_LOOP
    assert ride.sprite_flags & SpriteFlag.ZERO_G_ROLL


def test_missing_required_field_raises(tmp_path):
    path = _make_ride(tmp_path)
    data = json.loads(path.read_text())
    del data["name"]
    path.write_text(json.dumps(data))
    with pytest.raises(LoadError):
        load_ride(path)


def test_unknown_sprite_group_raises(tmp_path):
    with pytest.raises(LoadError):
        load_ride(_make_ride(tmp_path, sprites=["not_a_real_group"]))


def test_unknown_color_raises(tmp_path):
    with pytest.raises(LoadError):
        load_ride(_make_ride(tmp_path, default_colors=[["chartreuse", "black", "white"]]))


def test_restraint_animation_broadcasts_frames(tmp_path):
    vehicle = {
        "flags": ["restraint_animation"],
        "model": {
            "mesh_index": 0,
            "position": [1, 2, 3],
            "orientation": [[0, 0, 0], [0, -30, 0], [0, -60, 0], [0, -90, 0]],
        },
        "mass": 100,
        "spacing": 2.0,
        "draw_order": 1,
    }
    ride = load_ride(_make_ride(tmp_path, vehicles=[vehicle]))
    frames = ride.vehicles[0].model.meshes[0]
    # Single mesh_index / position broadcast across all 4 animation frames.
    assert [f.mesh_index for f in frames[:4]] == [0, 0, 0, 0]
    assert all(np.allclose(f.position, [1, 2, 3]) for f in frames[:4])
    # Per-frame orientation is preserved (last frame swings to -90).
    assert np.allclose(frames[3].orientation, [0, -90, 0])


def test_seat_count_derived_from_riders(tmp_path):
    # num_riders is the total peep meshes across all rows (2 rows x 2 = 4),
    # not a separately declared field.
    vehicle = {
        "model": {"mesh_index": 0},
        "mass": 100,
        "spacing": 2.0,
        "draw_order": 1,
        "riders": [
            [{"mesh_index": 0, "position": [0.5, 0, -0.4]},
             {"mesh_index": 0, "position": [0.5, 0, 0.4]}],
            [{"mesh_index": 0, "position": [-0.5, 0, -0.4]},
             {"mesh_index": 0, "position": [-0.5, 0, 0.4]}],
        ],
    }
    ride = load_ride(_make_ride(tmp_path, vehicles=[vehicle]))
    assert ride.vehicles[0].num_riders == 4
    assert len(ride.vehicles[0].riders) == 2  # numSeatRows


def test_optional_fields_default(tmp_path):
    # zero_cars / preview_tab_car / build_menu_priority / configuration all
    # omitted; vehicle has no flags; mesh frame has no position/orientation.
    ride = load_ride(_make_ride(tmp_path))
    assert ride.zero_cars == 0
    assert ride.tab_car == 0
    assert ride.build_menu_priority == 0
    assert ride.configuration[0] == 0  # default car type
    frame = ride.vehicles[0].model.meshes[0][0]
    assert np.allclose(frame.position, [0, 0, 0])
    assert np.allclose(frame.orientation, [0, 0, 0])


def test_load_lights_normalizes_direction():
    lights = load_lights([
        {"type": "diffuse", "shadow": False, "direction": [0, 3, 0], "strength": 0.5},
        {"type": "specular", "shadow": True, "direction": [2, 0, 0], "strength": 1.0},
    ])
    assert len(lights) == 2
    assert np.isclose(np.linalg.norm(lights[0].direction), 1.0)
    assert lights[1].shadow == 1


def test_load_lights_shadow_defaults_false():
    lights = load_lights([
        {"type": "diffuse", "direction": [0, 1, 0], "strength": 0.5},
    ])
    assert lights[0].shadow == 0


def test_load_lights_rejects_unknown_type():
    with pytest.raises(LoadError):
        load_lights([{"type": "glow", "shadow": False,
                      "direction": [0, 1, 0], "strength": 1.0}])
