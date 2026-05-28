"""Tests for the RCT2 palette tables and nearest-color search."""

import numpy as np
import pytest

from openrct2_vehicle_generator import palette
from openrct2_vehicle_generator.palette import (
    PALETTE_LINEAR,
    PALETTE_RGB,
    TRANSPARENT_INDEX,
    _REGION_TABLE,
    _srgb2linear,
    color_from_vector,
    palette_get_nearest,
    vector_from_color,
)


def test_palette_shape_and_dtype():
    assert PALETTE_RGB.shape == (256, 3)
    assert PALETTE_RGB.dtype == np.uint8
    assert PALETTE_LINEAR.shape == (256, 3)


def test_transparent_index_is_zero():
    assert TRANSPARENT_INDEX == 0


def test_srgb_linear_roundtrip():
    xs = np.linspace(0.0, 1.0, 256)
    lin = _srgb2linear(xs)
    back = np.array([palette._linear2srgb_scalar(v) for v in lin])
    assert np.allclose(back, xs, atol=1e-9)


def test_color_vector_roundtrip_within_one_lsb():
    # Every palette entry should survive a round trip through linear space to
    # within a single 8-bit code (quantization rounding only).
    for rgb in map(tuple, PALETTE_RGB.tolist()):
        out = color_from_vector(vector_from_color(rgb))
        assert all(abs(a - b) <= 1 for a, b in zip(rgb, out)), (rgb, out)


@pytest.mark.parametrize("region", range(len(_REGION_TABLE)))
def test_region_indices_in_palette_range(region):
    indices, colors, _remap = _REGION_TABLE[region]
    assert indices.size == colors.shape[0]
    assert indices.size > 0
    assert indices.min() >= 0
    assert indices.max() < 256


def test_nearest_exact_match_in_base_region():
    # Region 0 (general dithering) is a straight nearest-color search, so an
    # exact palette color must map back to its own index with ~zero error.
    indices, _colors, _remap = _REGION_TABLE[0]
    for idx in indices.tolist():
        nearest, error = palette_get_nearest(0, PALETTE_LINEAR[idx])
        assert nearest == idx
        assert np.linalg.norm(error) < 1e-9


def test_nearest_remap_region_returns_remap_index():
    # Region 1 is the player-primary remap ramp (palette indices 243..254).
    indices, colors, remap = _REGION_TABLE[1]
    assert remap is True
    for row, idx in enumerate(indices.tolist()):
        nearest, error = palette_get_nearest(1, colors[row])
        assert nearest == idx
        # Remap error is a luma residual stored in the first channel only.
        assert error[1] == 0.0 and error[2] == 0.0
