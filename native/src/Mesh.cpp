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

#include <cmath>
#include "Mesh.hpp"

namespace RCTGen {
    static float wrap_coord(float coord) {
        return fmax(0.0, fmin(1.0, coord - floor(coord)));
    }

    Vector3 texture_sample(Texture *texture, Vector2 coord) {
        uint16_t tex_x = (uint32_t)(texture->width * wrap_coord(coord.x));
        uint16_t tex_y = (uint32_t)(texture->height * wrap_coord(coord.y));
        if (tex_x == texture->width) tex_x = 0;
        if (tex_y == texture->height) tex_y = 0;
        return texture->pixels[tex_y * texture->width + tex_x];
    }
}
