/// Image.hpp — minimal struct only (no PNG I/O in the binding build).
///
/// Renderer.cpp's image_from_framebuffer allocates `pixels` via calloc and
/// stores width/height/offsets; the binding then takes ownership of that
/// buffer and exposes it to Python as a numpy array.

#pragma once

#include <cstdint>

namespace RCTGen {
    struct Image {
        std::uint16_t width;
        std::uint16_t height;
        std::int16_t x_offset;
        std::int16_t y_offset;
        std::uint8_t *pixels;
    };
}
