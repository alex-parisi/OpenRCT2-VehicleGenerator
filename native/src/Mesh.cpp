/// Mesh.cpp — slim version for the Python binding.
///
/// We do not link assimp or libpng, so the OBJ/MTL/PNG loaders from the
/// original Mesh.cpp (texture_load_png, mesh_load*, material_color,
/// material_texture, texture_init, texture_destroy, mesh_destroy) are
/// omitted. Texture buffers and mesh arrays are constructed in Python and
/// handed to the binding; ownership is tracked in PyContext.
///
/// Only texture_sample is needed at C++ scope, because Renderer.cpp's
/// scene_sample_point calls it directly.

#include "Mesh.hpp"
#include <algorithm>
#include <cmath>

namespace RCTGen {
    static float wrap_coord(float coord) { return std::clamp(coord - std::floor(coord), 0.0f, 1.0f); }

    Vector3 texture_sample(const Texture& texture, Vector2 coord) {
        auto tex_x = static_cast<std::uint16_t>(static_cast<std::uint32_t>(texture.width * wrap_coord(coord.x)));
        auto tex_y = static_cast<std::uint16_t>(static_cast<std::uint32_t>(texture.height * wrap_coord(coord.y)));
        if (tex_x == texture.width) tex_x = 0;
        if (tex_y == texture.height) tex_y = 0;
        return texture.pixels[tex_y * texture.width + tex_x];
    }
} // namespace RCTGen
