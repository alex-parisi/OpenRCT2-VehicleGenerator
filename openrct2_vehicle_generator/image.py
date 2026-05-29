"""IndexedImage PNG I/O via Pillow.

Ports the PNG read/write portion of src/iso-render/Image.cpp.
"""


from pathlib import Path

import numpy as np
from PIL import Image as PILImage

from .palette import PALETTE_RGB, TRANSPARENT_INDEX
from .types import IndexedImage


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
    img.putpalette(PALETTE_RGB.tobytes())
    img.info["transparency"] = TRANSPARENT_INDEX
    img.save(path, format="PNG", optimize=False)
