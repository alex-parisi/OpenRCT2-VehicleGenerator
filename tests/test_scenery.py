"""Tests for the small-scenery generator: sprite counts, render dispatch, and
object.json shape. The native renderer is stubbed so this runs without Embree."""

import numpy as np
import pytest
from openrct2_iso_core.types import IndexedImage
from openrct2_scenery_generator import sprite_renderer
from openrct2_scenery_generator.exporter import build_small_scenery_json
from openrct2_scenery_generator.loader import LoadError, build_small_scenery
from openrct2_scenery_generator.sprite_renderer import (
    count_small_scenery_sprites,
    render_small_scenery,
)


@pytest.fixture
def stub_render(monkeypatch):
    def fake_render_view(_context, _view):
        return IndexedImage(1, 1, 0, 0, np.zeros((1, 1), dtype=np.uint8))

    monkeypatch.setattr(sprite_renderer, "render_view", fake_render_view)


@pytest.mark.parametrize("rotatable,expected", [(True, 4), (False, 1)])
def test_count_matches_render(stub_render, rotatable, expected):
    num = 4 if rotatable else 1
    assert count_small_scenery_sprites(num) == expected
    assert len(render_small_scenery(context=None, num_rotations=num)) == expected


def _make_scenery(tmp_path, **overrides):
    (tmp_path / "m.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    from openrct2_iso_core.mesh import load_mesh

    config = {
        "id": "openrct2vg.scenery_small.test",
        "name": "Test",
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
        "shape": "4/4",
        **overrides,
    }
    mesh = load_mesh(tmp_path / "m.obj")
    return build_small_scenery(config, [mesh])


def test_build_json_shape(tmp_path):
    obj = _make_scenery(tmp_path, price=3.0, has_primary_colour=True)
    j = build_small_scenery_json(obj)
    assert j["objectType"] == "scenery_small"
    assert j["id"] == "openrct2vg.scenery_small.test"
    props = j["properties"]
    assert props["shape"] == "4/4"
    assert props["price"] == 3.0
    assert props["isRotatable"] is True
    assert props["hasPrimaryColour"] is True
    assert j["strings"]["name"]["en-GB"] == "Test"


def test_rotatable_defaults_true(tmp_path):
    obj = _make_scenery(tmp_path)
    assert obj.num_rotations == 4
    obj2 = _make_scenery(tmp_path, is_rotatable=False)
    assert obj2.num_rotations == 1


def test_bad_shape_rejected(tmp_path):
    with pytest.raises(LoadError):
        _make_scenery(tmp_path, shape="5/4")


# --- large scenery ---

from openrct2_iso_core.geometry import combine_model_world  # noqa: E402
from openrct2_scenery_generator.exporter import build_large_scenery_json  # noqa: E402
from openrct2_scenery_generator.loader import build_large_scenery  # noqa: E402
from openrct2_scenery_generator.sprite_renderer import (  # noqa: E402
    count_large_scenery_sprites,
    render_large_scenery,
)


class _FakeContext:
    def begin_render(self):
        pass

    def add_model(self, *a, **k):
        pass

    def finalize_render(self):
        pass

    def end_render(self):
        pass


@pytest.mark.parametrize("tiles,expected", [(1, 8), (2, 12), (4, 20)])
def test_large_count(tiles, expected):
    # 4 preview + 4 per tile.
    assert count_large_scenery_sprites(tiles) == expected


def _make_large(tmp_path, ntiles=2, **overrides):
    from openrct2_iso_core.mesh import load_mesh

    # Two triangles, one near OBJ X=0, one near OBJ X=TILE_SIZE.
    (tmp_path / "m.obj").write_text(
        "v 0 0 0\nv 0.2 0 0\nv 0 1 0\n"
        "v 3.3 0 0\nv 3.5 0 0\nv 3.3 1 0\n"
        "f 1 2 3\nf 4 5 6\n"
    )
    tiles = [{"x": i, "y": 0, "z": 0, "clearance": 40} for i in range(ntiles)]
    config = {
        "id": "openrct2vg.scenery_large.test",
        "name": "Test Gate",
        "object_type": "scenery_large",
        "meshes": ["m.obj"],
        "model": [{"mesh_index": 0, "position": [0, 0, 0]}],
        "tiles": tiles,
        **overrides,
    }
    mesh = load_mesh(tmp_path / "m.obj")
    return build_large_scenery(config, [mesh])


def test_large_json_shape(tmp_path):
    obj = _make_large(tmp_path, ntiles=2, price=8.0, has_primary_colour=True)
    j = build_large_scenery_json(obj)
    assert j["objectType"] == "scenery_large"
    props = j["properties"]
    assert len(props["tiles"]) == 2
    # Config tile index 1 -> coordinate units (32 per tile), sign negated to
    # reconcile the renderer (+X up-right) with OpenRCT2 (+x lower-left).
    assert props["tiles"][1]["x"] == -32
    assert props["tiles"][0]["corners"] == 0xF
    assert props["hasPrimaryColour"] is True


def test_large_render_order_and_count(stub_render, tmp_path):
    obj = _make_large(tmp_path, ntiles=2)
    combined = combine_model_world(obj.meshes, obj.model)
    import numpy as np

    centers = np.array([[0.0, 0.0], [3.3, 0.0]])
    imgs = render_large_scenery(_FakeContext(), combined, centers)
    # 4 preview + 4 per tile * 2 tiles.
    assert len(imgs) == count_large_scenery_sprites(2) == 12
