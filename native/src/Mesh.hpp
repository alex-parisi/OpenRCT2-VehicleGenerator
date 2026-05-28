/// Mesh.hpp

#pragma once

#include <cstddef>
#include <cstdint>

#include "VectorMath.hpp"

namespace RCTGen {
    struct Texture {
        std::uint16_t width;
        std::uint16_t height;
        Vector3 *pixels;
    };

    // Material flag bits, combined with bitwise OR. Kept as named uint16_t
    // constants (rather than enum class) because renderer.cpp / raytrace.cpp
    // mix-and-match these with implicit bool conversion (`if (flags & X)`),
    // and that idiomatic style would require `has_flag()` everywhere with a
    // scoped enum. The historical bit layout and names are preserved exactly.
    // NOLINTBEGIN(readability-identifier-naming) -- legacy bit-flag names, see comment above.
    inline constexpr std::uint16_t MATERIAL_HAS_TEXTURE = 1u << 0;
    inline constexpr std::uint16_t MATERIAL_IS_REMAPPABLE = 1u << 1;
    inline constexpr std::uint16_t MATERIAL_IS_MASK = 1u << 2;
    inline constexpr std::uint16_t MATERIAL_NO_AO = 1u << 3;
    inline constexpr std::uint16_t MATERIAL_BACKGROUND_AA = 1u << 4;
    inline constexpr std::uint16_t MATERIAL_BACKGROUND_AA_DARK = 1u << 5;
    inline constexpr std::uint16_t MATERIAL_IS_VISIBLE_MASK = 1u << 6;
    inline constexpr std::uint16_t MATERIAL_NO_BLEED = 1u << 7;
    inline constexpr std::uint16_t MATERIAL_IS_FLAT_SHADED = 1u << 8;
    // NOLINTEND(readability-identifier-naming)

    struct Material {
        std::uint16_t flags;
        std::uint8_t region;
        float specular_exponent;
        Vector3 specular_color;
        Vector3 ambient_color;

        union {
            Texture texture;
            Vector3 color;
        };
    };

    struct Face {
        std::size_t material;
        std::size_t indices[3];
    };

    struct Mesh {
        Vector3 *vertices;
        Vector3 *normals;
        Vector2 *uvs;
        Face *faces;
        Material *materials;
        std::size_t num_vertices;
        std::size_t num_faces;
        std::size_t num_materials;
    };

    void texture_init(Texture *texture, std::uint16_t width, std::uint16_t height);

    int texture_load_png(Texture *texture, const char *filename);

    Vector3 texture_sample(Texture *texture, Vector2 coord);

    void texture_destroy(Texture *texture);

    Material material_color(Vector3 color, Vector3 specular_color, float specular_exponent, std::uint8_t flags);

    Material material_texture(const char *filename, Vector3 specular_color, float specular_exponent,
                              std::uint8_t flags);

    int mesh_load(Mesh *mesh, const char *filename);

    int mesh_load_transform(Mesh *output, const char *filename, Matrix3 matrix);

    void mesh_destroy(Mesh *mesh);
}