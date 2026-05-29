/// Image.hpp — minimal struct only (no PNG I/O in the binding build).
///
/// Renderer.cpp's image_from_framebuffer populates `pixels` via
/// std::vector; the binding then copies it into a numpy array.

#pragma once

#include <cstdint>
#include <vector>

namespace RCTGen {
    struct Image {
        std::uint16_t width{};
        std::uint16_t height{};
        std::int16_t x_offset{};
        std::int16_t y_offset{};
        std::vector<std::uint8_t> pixels{};
    };
} // namespace RCTGen
