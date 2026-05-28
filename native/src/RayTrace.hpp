/// RayTrace.hpp

#pragma once

#include <bitset>
#include <cstdint>
#include <type_traits>

#include <embree4/rtcore.h>

#include "Mesh.hpp"
#include "VectorMath.hpp"

namespace RCTGen {
    inline constexpr std::size_t kMaxMeshes = 128;

    using Device = RTCDevice;

    struct Vertex {
        Vector3 vertex;
        Vector3 normal;
    };

    // Mesh flag bits, combined with bitwise OR. Plain int constants because
    // callers OR them with masking integer flags (the `track_mask` parameter
    // in track.cpp is a 0/1 bool-int that gets ORed with these).
    // NOLINTBEGIN(readability-identifier-naming) -- legacy bit-flag names, see comment above.
    inline constexpr int MESH_MASK = 1 << 0;
    inline constexpr int MESH_GHOST = 1 << 1;
    // NOLINTEND(readability-identifier-naming)

    struct Context;

    struct Scene {
        Context *context;
        Mesh *meshes[kMaxMeshes];
        std::bitset<kMaxMeshes> mask;
        std::bitset<kMaxMeshes> ghost;
        std::uint32_t num_meshes;
        float x_min, x_max, y_min, y_max, z_min, z_max;
        RTCDevice embree_device;
        RTCScene embree_scene;
    };

    struct RayHit {
        std::uint32_t mesh_index;
        std::uint32_t face_index;
        Vector3 position;
        Vector3 normal;
        float ghost_distance;
        float distance;
        float u;
        float v;
    };

    Device device_init();

    void device_destroy(Device device);

    void scene_init(Scene *scene, Device device);

    void scene_finalize(Scene *scene);

    void scene_destroy(Scene *scene);

    void scene_add_model(Scene * scene, Mesh * mesh,
                         Vertex(*transform)(Vector3, Vector3, bool, void *),
                         void *data, int flags);

    int scene_trace_ray(Scene *scene, Vector3 origin, Vector3 direction, RayHit *hit);

    int scene_trace_occlusion_ray(Scene *scene, Vector3 origin, Vector3 direction);

    int scene_is_mask(Scene *scene, int index);

    int scene_is_ghost(Scene *scene, int index);
}