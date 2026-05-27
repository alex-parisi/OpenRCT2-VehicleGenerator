"""IndexedImage helpers: PNG I/O via Pillow, blit, crop, atlas packing.

Ports src/iso-render/Image.cpp and Pack.cpp.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image as PILImage

from .palette import PALETTE_RGB, TRANSPARENT_INDEX
from .types import IndexedImage


# ---------------------------------------------------------------------------
# PNG I/O
# ---------------------------------------------------------------------------

def _palette_bytes() -> bytes:
    return bytes(int(v) for v in PALETTE_RGB.reshape(-1))


def read_png(path: Path | str) -> IndexedImage:
    """Read a paletted PNG into an IndexedImage. Mirrors image_read_png."""
    with PILImage.open(path) as img:
        if img.mode != "P":
            raise ValueError(f"PNG {path} is not paletted (mode={img.mode})")
        pixels = np.array(img, dtype=np.uint8)
    height, width = pixels.shape
    return IndexedImage(
        width=width,
        height=height,
        x_offset=0,
        y_offset=0,
        pixels=pixels,
    )


def write_png(image: IndexedImage, path: Path | str) -> None:
    """Write IndexedImage as a paletted PNG with transparent index 0."""
    img = PILImage.fromarray(image.pixels, mode="P")
    img.putpalette(_palette_bytes())
    img.info["transparency"] = TRANSPARENT_INDEX
    img.save(path, format="PNG", optimize=False)


# ---------------------------------------------------------------------------
# Blit / crop
# ---------------------------------------------------------------------------

def blit(dst: IndexedImage, src: IndexedImage, x_offset: int, y_offset: int) -> None:
    """Copy non-zero pixels from src into dst at (x_offset, y_offset).

    Offsets are adjusted by each image's own (x_offset, y_offset) hotspot,
    matching image_blit in Image.cpp.
    """
    x = x_offset + src.x_offset - dst.x_offset
    y = y_offset + src.y_offset - dst.y_offset

    # Clip
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(dst.width, x + src.width)
    y1 = min(dst.height, y + src.height)
    if x0 >= x1 or y0 >= y1:
        return

    sx0 = x0 - x
    sy0 = y0 - y
    src_slice = src.pixels[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
    dst_slice = dst.pixels[y0:y1, x0:x1]
    mask = src_slice != 0
    dst_slice[mask] = src_slice[mask]


def crop(image: IndexedImage) -> None:
    """In-place trim of fully-transparent border. Mirrors image_crop."""
    non_zero = np.argwhere(image.pixels != 0)
    if non_zero.size == 0:
        image.x_offset = 0
        image.y_offset = 0
        image.width = 1
        image.height = 1
        image.pixels = np.zeros((1, 1), dtype=np.uint8)
        return
    y_min, x_min = non_zero.min(axis=0)
    y_max, x_max = non_zero.max(axis=0)
    image.x_offset += int(x_min)
    image.y_offset += int(y_min)
    image.width = int(x_max - x_min + 1)
    image.height = int(y_max - y_min + 1)
    image.pixels = image.pixels[y_min:y_max + 1, x_min:x_max + 1].copy()


# ---------------------------------------------------------------------------
# Atlas packing
# ---------------------------------------------------------------------------

def _pack_rects_fixed(images: list[IndexedImage], width: int, height: int,
                      sort_key) -> tuple[bool, list[int], list[int]]:
    """Try to pack `images` into a width*height bin.

    Returns (success, x_coords, y_coords). x_coords[i] / y_coords[i] are
    populated for image i; if !success, they may be partially set.

    Mirrors the legacy pack_rects_fixed_with_comparator: sort by
    sort_key descending (stable on equal keys), greedily place each image
    into the last (most-recently-created) empty space that fits, splitting
    leftover space into at most two rectangles.
    """
    n = len(images)
    permutation = sorted(range(n), key=sort_key, reverse=True)

    empty_spaces: list[tuple[int, int, int, int]] = [(0, 0, width, height)]
    x_coords = [0] * n
    y_coords = [0] * n

    for idx in permutation:
        image = images[idx]
        iw, ih = image.width, image.height
        chosen = -1
        new_rects: list[tuple[int, int, int, int]] = []
        # Iterate backwards to mirror the legacy ordering.
        for j in range(len(empty_spaces) - 1, -1, -1):
            sx, sy, sw, sh = empty_spaces[j]
            x_coords[idx] = sx
            y_coords[idx] = sy
            if sw > iw and sh > ih:
                if sh - ih < sw - iw:
                    new_rects = [
                        (sx, sy + ih, sw, sh - ih),
                        (sx + iw, sy, sw - iw, ih),
                    ]
                else:
                    new_rects = [
                        (sx + iw, sy, sw - iw, sh),
                        (sx, sy + ih, iw, sh - ih),
                    ]
                chosen = j
                break
            elif sw == iw and sh > ih:
                new_rects = [(sx, sy + ih, sw, sh - ih)]
                chosen = j
                break
            elif sh == ih and sw > iw:
                new_rects = [(sx + iw, sy, sw - iw, sh)]
                chosen = j
                break
            elif sw == iw and sh == ih:
                new_rects = []
                chosen = j
                break
        if chosen < 0:
            return False, x_coords, y_coords
        empty_spaces.pop(chosen)
        empty_spaces.extend(new_rects)
    return True, x_coords, y_coords


def _pack_rects(images: list[IndexedImage]) -> tuple[int, int, list[int], list[int]]:
    """Find a near-minimal atlas size and pack. Returns (width, height,
    x_coords, y_coords).

    Tries multiple sort heuristics and then binary-searches the bin
    dimensions. Mirrors pack_rects in Pack.cpp.
    """
    keys = [
        lambda i, im=None: images[i].width * images[i].height,           # area
        lambda i: images[i].width + images[i].height,                    # perimeter
        lambda i: max(images[i].width, images[i].height),                # max dim
        lambda i: images[i].width,                                       # width
        lambda i: images[i].height,                                      # height
    ]

    def try_pack(w: int, h: int):
        for k in keys:
            ok, xs, ys = _pack_rects_fixed(images, w, h, k)
            if ok:
                return xs, ys
        return None

    size = 256
    while True:
        if try_pack(size, size) is not None:
            break
        size *= 2

    lower, upper = size // 2, size
    while upper - lower > 2:
        mid = (upper + lower) // 2
        if try_pack(mid, mid) is not None:
            upper = mid
        else:
            lower = mid

    # Shrink height.
    lower_h, upper_h = 0, upper
    while upper_h - lower_h > 2:
        mid = (upper_h + lower_h) // 2
        if try_pack(upper, mid) is not None:
            upper_h = mid
        else:
            lower_h = mid

    # Shrink width.
    lower_w, upper_w = 0, upper
    while upper_w - lower_w > 2:
        mid = (upper_w + lower_w) // 2
        if try_pack(mid, upper_h) is not None:
            upper_w = mid
        else:
            lower_w = mid

    if upper_w < upper_h:
        width, height = upper_w, upper
    else:
        width, height = upper, upper_h

    result = try_pack(width, height)
    assert result is not None, "final pack must succeed"
    xs, ys = result
    return width, height, xs, ys


def create_atlas(images: list[IndexedImage]) -> tuple[IndexedImage, list[int], list[int]]:
    """Pack `images` into a single atlas. Returns (atlas, x_coords, y_coords).

    x_coords[i] / y_coords[i] are the atlas-space top-left of image i
    (before applying its hotspot offset).
    """
    if not images:
        return IndexedImage.blank(1, 1), [], []
    width, height, xs, ys = _pack_rects(images)
    atlas = IndexedImage.blank(width, height, 0, 0)
    for i, image in enumerate(images):
        blit(atlas, image, xs[i] - image.x_offset, ys[i] - image.y_offset)
    return atlas, xs, ys
