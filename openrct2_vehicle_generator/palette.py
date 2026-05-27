"""RCT2 256-color palette and nearest-color search.

Ports src/iso-render/Palette.cpp and the palette data from
src/iso-render/Image.cpp / Palette.cpp.
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Palette data
# ---------------------------------------------------------------------------

# Full 256-color RCT2 palette (sRGB, 0..255). Indices 9 entries plus 247
# meaningful colors -- matches the C++ `Palette palette_rct2()` colors[]
# array exactly (entries 226..237 are the green-remap range).
_RCT2_COLORS: list[tuple[int, int, int]] = [
    (0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    (0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    (23, 35, 35), (35, 51, 51), (47, 67, 67), (63, 83, 83), (75, 99, 99),
    (91, 115, 115), (111, 131, 131), (131, 151, 151), (159, 175, 175),
    (183, 195, 195), (211, 219, 219), (239, 243, 243),
    (51, 47, 0), (63, 59, 0), (79, 75, 11), (91, 91, 19), (107, 107, 31),
    (119, 123, 47), (135, 139, 59), (151, 155, 79), (167, 175, 95),
    (187, 191, 115), (203, 207, 139), (223, 227, 163),
    (67, 43, 7), (87, 59, 11), (111, 75, 23), (127, 87, 31), (143, 99, 39),
    (159, 115, 51), (179, 131, 67), (191, 151, 87), (203, 175, 111),
    (219, 199, 135), (231, 219, 163), (247, 239, 195),
    (71, 27, 0), (95, 43, 0), (119, 63, 0), (143, 83, 7), (167, 111, 7),
    (191, 139, 15), (215, 167, 19), (243, 203, 27), (255, 231, 47),
    (255, 243, 95), (255, 251, 143), (255, 255, 195),
    (35, 0, 0), (79, 0, 0), (95, 7, 7), (111, 15, 15), (127, 27, 27),
    (143, 39, 39), (163, 59, 59), (179, 79, 79), (199, 103, 103),
    (215, 127, 127), (235, 159, 159), (255, 191, 191),
    (27, 51, 19), (35, 63, 23), (47, 79, 31), (59, 95, 39), (71, 111, 43),
    (87, 127, 51), (99, 143, 59), (115, 155, 67), (131, 171, 75),
    (147, 187, 83), (163, 203, 95), (183, 219, 103),
    (31, 55, 27), (47, 71, 35), (59, 83, 43), (75, 99, 55), (91, 111, 67),
    (111, 135, 79), (135, 159, 95), (159, 183, 111), (183, 207, 127),
    (195, 219, 147), (207, 231, 167), (223, 247, 191),
    (15, 63, 0), (19, 83, 0), (23, 103, 0), (31, 123, 0), (39, 143, 7),
    (55, 159, 23), (71, 175, 39), (91, 191, 63), (111, 207, 87),
    (139, 223, 115), (163, 239, 143), (195, 255, 179),
    (79, 43, 19), (99, 55, 27), (119, 71, 43), (139, 87, 59), (167, 99, 67),
    (187, 115, 83), (207, 131, 99), (215, 151, 115), (227, 171, 131),
    (239, 191, 151), (247, 207, 171), (255, 227, 195),
    (15, 19, 55), (39, 43, 87), (51, 55, 103), (63, 67, 119), (83, 83, 139),
    (99, 99, 155), (119, 119, 175), (139, 139, 191), (159, 159, 207),
    (183, 183, 223), (211, 211, 239), (239, 239, 255),
    (0, 27, 111), (0, 39, 151), (7, 51, 167), (15, 67, 187), (27, 83, 203),
    (43, 103, 223), (67, 135, 227), (91, 163, 231), (119, 187, 239),
    (143, 211, 243), (175, 231, 251), (215, 247, 255),
    (11, 43, 15), (15, 55, 23), (23, 71, 31), (35, 83, 43), (47, 99, 59),
    (59, 115, 75), (79, 135, 95), (99, 155, 119), (123, 175, 139),
    (147, 199, 167), (175, 219, 195), (207, 243, 223),
    (63, 0, 95), (75, 7, 115), (83, 15, 127), (95, 31, 143), (107, 43, 155),
    (123, 63, 171), (135, 83, 187), (155, 103, 199), (171, 127, 215),
    (191, 155, 231), (215, 195, 243), (243, 235, 255),
    (63, 0, 0), (87, 0, 0), (115, 0, 0), (143, 0, 0), (171, 0, 0),
    (199, 0, 0), (227, 7, 0), (255, 7, 0), (255, 79, 67), (255, 123, 115),
    (255, 171, 163), (255, 219, 215),
    (79, 39, 0), (111, 51, 0), (147, 63, 0), (183, 71, 0), (219, 79, 0),
    (255, 83, 0), (255, 111, 23), (255, 139, 51), (255, 163, 79),
    (255, 183, 107), (255, 203, 135), (255, 219, 163),
    (0, 51, 47), (0, 63, 55), (0, 75, 67), (0, 87, 79), (7, 107, 99),
    (23, 127, 119), (43, 147, 143), (71, 167, 163), (99, 187, 187),
    (131, 207, 207), (171, 231, 231), (207, 255, 255),
    (63, 0, 27), (103, 0, 51), (123, 11, 63), (143, 23, 79), (163, 31, 95),
    (183, 39, 111), (219, 59, 143), (239, 91, 171), (243, 119, 187),
    (247, 151, 203), (251, 183, 223), (255, 215, 239),
    (39, 19, 0), (55, 31, 7), (71, 47, 15), (91, 63, 31), (107, 83, 51),
    (123, 103, 75), (143, 127, 107), (163, 147, 127), (187, 171, 147),
    (207, 195, 171), (231, 219, 195), (255, 243, 223),
    (55, 75, 75), (255, 183, 0), (255, 219, 0), (255, 255, 0),
    (39, 143, 135),
    (7, 107, 99), (7, 107, 99), (7, 107, 99),
    (27, 131, 123), (155, 227, 227),
    (55, 155, 151), (55, 155, 151), (55, 155, 151),
    (115, 203, 203),
    (67, 91, 91), (83, 107, 107), (99, 123, 123),
    # Green remap (indices 226..237) -- present in Palette.cpp `colors`,
    # absent in Image.cpp's rct2_palette (which has different entries for
    # those positions). Palette.cpp is the source-of-truth for quantization.
    (8, 67, 8), (16, 85, 16), (24, 103, 24), (32, 121, 32), (40, 139, 40),
    (48, 157, 48), (56, 175, 56), (64, 193, 64), (72, 211, 72), (80, 219, 80),
    (88, 237, 88), (92, 255, 92),
]

# The C++ declares Palette::colors as std::array<Color, 256> but the
# brace-init list provides 255 entries — element 255 is zero-initialized.
# Pad to 256 to match exactly.
assert len(_RCT2_COLORS) == 255, f"Expected 255, got {len(_RCT2_COLORS)}"
_RCT2_COLORS = _RCT2_COLORS + [(0, 0, 0)] * (256 - len(_RCT2_COLORS))

# Remap colors -- 16 entries from grey ramp, indices 10..21 of the base
# palette. (Used when a region has remap=True.)
_REMAP_COLORS: list[tuple[int, int, int]] = [
    (23, 35, 35), (35, 51, 51), (47, 67, 67), (63, 83, 83), (75, 99, 99),
    (91, 115, 115), (111, 131, 131), (131, 151, 151), (159, 175, 175),
    (183, 195, 195), (211, 219, 219), (239, 243, 243),
]


# Region table from Palette.cpp `palette_rct2()`. Each region is
# (subregions, [start_indices], [end_indices], remap).
# Region indices match material.region:
#   0 = base (general dithering)
#   1..3 = remap1/2/3
#   4 = greyscale
#   5 = peep
#   6 = chain
#   7 = unused/transparent fallback
_REGIONS_RAW: list[tuple[int, list[int], list[int], bool]] = [
    (3, [10, 214, 240, 0], [202, 227, 243, 0], False),
    (1, [243, 0, 0, 0], [255, 0, 0, 0], True),
    (1, [202, 0, 0, 0], [214, 0, 0, 0], True),
    (1, [46, 0, 0, 0], [58, 0, 0, 0], True),
    (3, [10, 226, 240, 0], [22, 227, 243, 0], False),
    (2, [10, 106, 0, 0], [11, 118, 0, 0], False),
    (1, [1, 0, 0, 0], [2, 0, 0, 0], False),
    (1, [0, 0, 0, 0], [1, 0, 0, 0], False),
]

TRANSPARENT_INDEX = 0
NUM_REGIONS = 8


# ---------------------------------------------------------------------------
# sRGB <-> linear conversion
# ---------------------------------------------------------------------------


def _srgb2linear(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    out = np.empty_like(x)
    lo = x <= 0.04045
    out[lo] = x[lo] / 12.92
    out[~lo] = np.power((x[~lo] + 0.055) / 1.055, 2.4)
    return out


def _linear2srgb_scalar(x: float) -> float:
    if x <= 0.0031308:
        return x * 12.92
    return 1.055 * (x ** (1.0 / 2.4)) - 0.055


def vector_from_color(rgb: tuple[int, int, int]) -> np.ndarray:
    r, g, b = rgb
    arr = np.array([r, g, b], dtype=np.float64) / 255.0
    return _srgb2linear(arr)


def color_from_vector(vec: np.ndarray) -> tuple[int, int, int]:
    """Quantize a linear-RGB vector back to 8-bit sRGB.

    Mirrors color_from_vector in Palette.cpp: clamp, convert, then
    `floor(x*255 + 0.4999)`.
    """
    out = []
    for component in vec:
        c = _linear2srgb_scalar(max(0.0, min(1.0, float(component))))
        out.append(int(np.floor(c * 255.0 + 0.4999)))
    return out[0], out[1], out[2]


# ---------------------------------------------------------------------------
# Palette tables / region indices
# ---------------------------------------------------------------------------

# Palette as np.uint8 (256, 3).
PALETTE_RGB = np.array(_RCT2_COLORS, dtype=np.uint8)
# Same but in linear RGB (256, 3) for nearest-color search.
PALETTE_LINEAR = _srgb2linear(PALETTE_RGB.astype(np.float64) / 255.0)

# Remap colors in linear space (16, 3).
_REMAP_LINEAR = _srgb2linear(
    np.array(_REMAP_COLORS, dtype=np.float64) / 255.0)


# For each region, pre-flatten the candidate (palette_index, linear_color)
# lists.
def _build_region_table() -> list[tuple[np.ndarray, np.ndarray, bool]]:
    table = []
    for subregions, starts, ends, remap in _REGIONS_RAW:
        indices = []
        colors = []
        for s in range(subregions):
            start = starts[s]
            end = ends[s]
            for i in range(start, end):
                indices.append(i)
                if remap:
                    # Use remap color table indexed by (i - start_indices[0]).
                    colors.append(_REMAP_LINEAR[i - starts[0]])
                else:
                    colors.append(PALETTE_LINEAR[i])
        table.append(
            (np.array(indices, dtype=np.int32),
             np.array(colors, dtype=np.float64),
             remap))
    return table


_REGION_TABLE = _build_region_table()


# Linear-luma weights from Palette.cpp vector3_get_luma (operates on
# linear-space "color" but with the sRGB-luma coefficients -- legacy quirk).
_LUMA_WEIGHTS = np.array([0.299, 0.587, 0.114], dtype=np.float64)


def palette_get_nearest(region: int, target: np.ndarray) -> tuple[int, np.ndarray]:
    """Return (palette_index, error) for the closest color in `region`.

    Mirrors `palette_get_nearest` in Palette.cpp:
      - search by Euclidean distance in *linear* RGB (against region
        colors -- remap colors if region.remap, else palette entries);
      - error is the linear-space residual for non-remap regions;
      - for remap regions, error is the luma residual against the actual
        palette color of the chosen index (not the remap color).
    """
    indices, colors, remap = _REGION_TABLE[region]
    deltas = colors - target  # (N, 3)
    norms = np.linalg.norm(deltas, axis=1)
    best = int(np.argmin(norms))
    nearest_index = int(indices[best])
    if remap:
        target_luma = float(target @ _LUMA_WEIGHTS)
        palette_color = PALETTE_LINEAR[nearest_index]
        nearest_luma = float(palette_color @ _LUMA_WEIGHTS)
        error = np.array([target_luma - nearest_luma, 0.0, 0.0], dtype=np.float64)
    else:
        error = target - PALETTE_LINEAR[nearest_index]
    return nearest_index, error
