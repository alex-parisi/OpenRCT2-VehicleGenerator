"""Regression tests for enum/name-table alignment."""

from openrct2_vehicle_generator.constants import (
    CATEGORY_NAMES,
    SPRITE_GROUP_NAMES,
    Category,
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
