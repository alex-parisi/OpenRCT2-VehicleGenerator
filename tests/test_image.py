"""Tests for IndexedImage blit/crop and atlas packing."""

import numpy as np

from openrct2_vehicle_generator.image import blit, create_atlas, crop
from openrct2_vehicle_generator.types import IndexedImage


def _img(pixels, x_offset=0, y_offset=0):
    arr = np.array(pixels, dtype=np.uint8)
    h, w = arr.shape
    return IndexedImage(width=w, height=h, x_offset=x_offset,
                        y_offset=y_offset, pixels=arr)


def test_blit_skips_transparent_pixels():
    dst = _img([[0, 0], [0, 0]])
    src = _img([[5, 0], [0, 7]])
    blit(dst, src, 0, 0)
    # Zero (transparent) source pixels leave the destination untouched.
    assert np.array_equal(dst.pixels, [[5, 0], [0, 7]])


def test_blit_overwrites_with_opaque_pixels():
    dst = _img([[1, 1], [1, 1]])
    src = _img([[0, 9], [0, 0]])
    blit(dst, src, 0, 0)
    assert np.array_equal(dst.pixels, [[1, 9], [1, 1]])


def test_blit_clips_out_of_bounds():
    dst = _img([[0, 0], [0, 0]])
    src = _img([[3, 3], [3, 3]])
    blit(dst, src, 1, 1)  # only top-left source pixel lands in-bounds
    assert np.array_equal(dst.pixels, [[0, 0], [0, 3]])


def test_blit_respects_hotspot_offsets():
    dst = _img([[0, 0], [0, 0]], x_offset=0, y_offset=0)
    src = _img([[8]], x_offset=1, y_offset=1)
    # effective x = 0 + src.x_offset(1) - dst.x_offset(0) = 1, same for y.
    blit(dst, src, 0, 0)
    assert np.array_equal(dst.pixels, [[0, 0], [0, 8]])


def test_crop_trims_transparent_border_and_updates_hotspot():
    img = _img(
        [[0, 0, 0, 0],
         [0, 4, 5, 0],
         [0, 0, 0, 0]],
        x_offset=10,
        y_offset=20,
    )
    crop(img)
    assert img.width == 2 and img.height == 1
    assert np.array_equal(img.pixels, [[4, 5]])
    assert img.x_offset == 11  # +1 column trimmed
    assert img.y_offset == 21  # +1 row trimmed


def test_crop_fully_transparent_becomes_one_pixel():
    img = _img([[0, 0], [0, 0]], x_offset=3, y_offset=3)
    crop(img)
    assert (img.width, img.height) == (1, 1)
    assert img.pixels.shape == (1, 1)


def test_create_atlas_packs_without_overlap():
    images = [_img(np.full((h, w), 1)) for w, h in
              [(10, 5), (4, 8), (6, 6), (3, 3), (12, 2)]]
    atlas, xs, ys = create_atlas(images)
    assert len(xs) == len(ys) == len(images)
    # Every image must fit inside the atlas bounds.
    for img, x, y in zip(images, xs, ys):
        assert 0 <= x and x + img.width <= atlas.width
        assert 0 <= y and y + img.height <= atlas.height
    # Placed rectangles must not overlap.
    occupancy = np.zeros((atlas.height, atlas.width), dtype=int)
    for img, x, y in zip(images, xs, ys):
        occupancy[y:y + img.height, x:x + img.width] += 1
    assert occupancy.max() <= 1


def test_create_atlas_empty():
    atlas, xs, ys = create_atlas([])
    assert (atlas.width, atlas.height) == (1, 1)
    assert xs == [] and ys == []
