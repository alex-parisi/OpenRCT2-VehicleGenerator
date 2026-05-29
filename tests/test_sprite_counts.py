"""count_sprites must agree with what render_vehicle_frame actually emits.

These are the same number in two places (the object.json declared sprite
count and the rendered image list); if they ever drift the parkobj is
silently corrupt. We stub the native render so this runs without Embree.
"""

import pytest
from openrct2_vehicle_generator import sprite_renderer
from openrct2_vehicle_generator.constants import SpriteFlag, VehicleFlag
from openrct2_vehicle_generator.sprite_renderer import (
    count_sprites,
    render_vehicle_frame,
)
from openrct2_vehicle_generator.types import IndexedImage

ALL_SPRITE_FLAGS = (1 << len(SpriteFlag)) - 1


@pytest.fixture
def stub_render(monkeypatch):
    """Replace the native render with a 1x1 dummy so we can count outputs."""
    calls = {"n": 0}

    def fake_render_view(_context, _view, **_kw):
        calls["n"] += 1
        return IndexedImage.blank(1, 1)

    monkeypatch.setattr(sprite_renderer, "render_view", fake_render_view)
    return calls


# Each single flag (except bare DIVE_LOOP, which the loader never emits without
# ZERO_G_ROLL -- see test_dive_loop_alone_would_desync), plus the combination
# that exercises the shared sb22 accounting, plus the everything-on case.
_FLAG_CASES = [
    pytest.param(int(f), id=f.name)
    for f in SpriteFlag
    if f is not SpriteFlag.DIVE_LOOP
] + [
    pytest.param(int(SpriteFlag.ZERO_G_ROLL | SpriteFlag.DIVE_LOOP), id="zerog+dive"),
    pytest.param(ALL_SPRITE_FLAGS, id="all"),
]


@pytest.mark.parametrize("sf", _FLAG_CASES)
def test_frame0_render_count_matches_count_sprites(stub_render, sf):
    frame0 = render_vehicle_frame(None, sf, frame=0)
    assert len(frame0) == count_sprites(sf, vehicle_flags=0)


def test_restraint_frames_add_twelve(stub_render):
    sf = int(SpriteFlag.FLAT_SLOPE)
    base = count_sprites(sf, vehicle_flags=0)
    with_restraint = count_sprites(sf, int(VehicleFlag.RESTRAINT_ANIMATION))
    assert with_restraint - base == 12
    # Restraint frames 1..3 each render 4 flat rotations -> 12 total.
    rendered = sum(
        len(render_vehicle_frame(None, sf, frame=f)) for f in (1, 2, 3)
    )
    assert rendered == 12


def test_dive_loop_alone_would_desync_without_implied_zero_g(stub_render):
    # Documents why loader implies ZERO_G_ROLL for DIVE_LOOP: bare dive loops
    # over-declare by the 16-sprite sb22 upgrade that only renders alongside
    # zero-g. The loader never lets this combination reach the renderer (see
    # test_loader.test_dive_loop_implies_zero_g), but the raw mismatch is real.
    dive_only = int(SpriteFlag.DIVE_LOOP)
    rendered = len(render_vehicle_frame(None, dive_only, frame=0))
    assert count_sprites(dive_only, 0) == 112
    assert rendered == 96
    # Adding zero-g restores consistency.
    both = int(SpriteFlag.DIVE_LOOP | SpriteFlag.ZERO_G_ROLL)
    assert len(render_vehicle_frame(None, both, frame=0)) == count_sprites(both, 0)
