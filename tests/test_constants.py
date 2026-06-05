"""Regression tests for enum/name-table alignment."""

from openrct2_vehicle_generator.constants import (
    CATEGORY_NAMES,
    FRICTION_SOUND_IDS,
    RUNNING_SOUND_NAMES,
    SECONDARY_SOUND_NAMES,
    SPRITE_GROUP_NAMES,
    Category,
    SecondarySound,
    SpriteFlag,
)


def test_category_names_cover_every_enum_value():
    # CATEGORY_NAMES is indexed directly by the Category enum value in
    # exporter.build_ride_json, so every enum member must have a slot.
    assert len(CATEGORY_NAMES) == len(Category)
    for member in Category:
        assert 0 <= member.value < len(CATEGORY_NAMES)


def test_category_names_are_the_expected_openrct2_strings():
    assert CATEGORY_NAMES[Category.TRANSPORT_RIDE] == "transport"
    assert CATEGORY_NAMES[Category.GENTLE_RIDE] == "gentle"
    assert CATEGORY_NAMES[Category.ROLLERCOASTER] == "rollercoaster"
    assert CATEGORY_NAMES[Category.THRILL_RIDE] == "thrill"
    assert CATEGORY_NAMES[Category.WATER_RIDE] == "water"
    assert CATEGORY_NAMES[Category.SHOP] == "shop"


def test_sprite_group_names_match_flag_count():
    # loader maps "all" to (1 << len(SPRITE_GROUP_NAMES)) - 1, so the name list
    # length must equal the number of SpriteFlag bits.
    assert len(SPRITE_GROUP_NAMES) == len(SpriteFlag)


def test_running_sound_names_align_with_friction_ids():
    # exporter does FRICTION_SOUND_IDS[ride.running_sound], where running_sound
    # is the RUNNING_SOUND_NAMES index, so the two tables must be the same length
    # (and stay in the same order). Dropping "waterslide" from the names list
    # silently shifted train/engine onto the wrong friction ids.
    assert len(RUNNING_SOUND_NAMES) == len(FRICTION_SOUND_IDS)


def test_secondary_sound_names_align_with_enum_values():
    # The SECONDARY_SOUND_NAMES index is written straight into object.json as
    # `soundRange`, so each name must sit at its SecondarySound enum value.
    expected = {
        "scream1": SecondarySound.SCREAMS1,
        "scream2": SecondarySound.SCREAMS2,
        "scream3": SecondarySound.SCREAMS3,
        "whistle": SecondarySound.WHISTLE,
        "bell": SecondarySound.BELL,
    }
    for name, member in expected.items():
        assert SECONDARY_SOUND_NAMES.index(name) == member.value
