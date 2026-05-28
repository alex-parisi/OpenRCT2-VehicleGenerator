// Verbatim port of the C-era raytrace implementation, adapted only to the
// modernized raytrace.h (std::bitset<kMaxMeshes> for Scene::mask and
// Scene::ghost instead of uint64_t[2]; std::uint32_t-typed counts). All
// AO sampling, intersection filtering, and ray-tracing math is left exactly
// as written -- this file is the source of truth for byte-equivalent ray
// hits / occlusion against the goldens captured pre-modernization (see
// bisect: first bad commit was 5eff54f "Modernize iso-render"). Any
// "modernization" of the math here (float-only literals, std::asin/std::sin
// /std::cos float overloads instead of unqualified asin/sin/cos which
// promote via C math.h to double, std::sqrt(float) instead of unqualified
// sqrt()) breaks byte-equivalence by 1 ULP on borderline samples.

#define NOMINMAX
#define _USE_MATH_DEFINES
#include <cstdlib>
#include <cstdio>
// NOLINTNEXTLINE(modernize-deprecated-headers) -- see header comment: <cmath> would pull in std:: float overloads that break byte-exact goldens.
#include <math.h>
#include <cassert>
#include <embree4/rtcore.h>
#include "RayTrace.hpp"

#ifdef min
#undef min
#endif
#ifdef max
#undef max
#endif
#ifndef M_PI
// NOLINTNEXTLINE(cppcoreguidelines-macro-usage) -- preserves C double-promotion; constexpr replacement breaks byte-exact goldens.
#define M_PI 3.14159265358979323846
#endif

//&& rayhit.hit.Ng_x*direction.x+rayhit.hit.Ng_y*direction.y+rayhit.hit.Ng_z*direction.z<0

namespace RCTGen {
    void rt_error(void * /*user_ptr*/, enum RTCError error, const char *str) {
        printf("error %d: %s\n", error, str);
        exit(1);
    }

    Device device_init() {
        Device device = rtcNewDevice(nullptr);
        if (!device) {
            printf("error %d: cannot create device\n", rtcGetDeviceError(nullptr));
            exit(1);
        }
        rtcSetDeviceErrorFunction(device, rt_error, nullptr);
        return device;
    }

    void device_destroy(Device device) {
        rtcReleaseDevice(device);
    }


    int scene_is_mask(Scene *scene, int index) {
        return scene->mask.test(index);
    }


    int scene_is_ghost(Scene *scene, int index) {
        return scene->ghost.test(index);
    }

    void scene_init(Scene *scene, Device device) {
        scene->num_meshes = 0;
        scene->mask.reset();
        scene->ghost.reset();
        scene->embree_device = device;
        scene->embree_scene = rtcNewScene(device);
        scene->x_max = -INFINITY;
        scene->y_max = -INFINITY;
        scene->z_max = -INFINITY;
        scene->x_min = INFINITY;
        scene->y_min = INFINITY;
        scene->z_min = INFINITY;
    }

    void scene_finalize(Scene *scene) {
        rtcCommitScene(scene->embree_scene);
    }

    void scene_destroy(Scene *scene) {
        rtcReleaseScene(scene->embree_scene);
    }

    float min(float x, float y) {
        return x <= y ? x : y;
    }

    float max(float x, float y) {
        return x >= y ? x : y;
    }


    void occlusionFilter(const struct RTCFilterFunctionNArguments *args) {
        //Check that packet size is 1 (I think this is guaranteed?)
        [[maybe_unused]] const unsigned int N = args->N;
        assert(N == 1);

        struct RTCRay *ray = (struct RTCRay *) args->ray;
        struct RTCHit *hit = (struct RTCHit *) args->hit;

        if (hit->Ng_x * ray->dir_x + hit->Ng_y * ray->dir_y + hit->Ng_z * ray->dir_z > 0)args->valid[0] = 0;
    }

    void scene_add_model(Scene * scene, Mesh * mesh, Vertex(*transform)(Vector3, Vector3, bool, void*), void*data,


    
    int flags
    )
 {
        //Add mesh to list of meshes
        assert(scene->num_meshes < kMaxMeshes);
        scene->meshes[scene->num_meshes] = mesh;
        if (flags & MESH_MASK)scene->mask.set(scene->num_meshes);
        if (flags & MESH_GHOST)scene->ghost.set(scene->num_meshes);
        scene->num_meshes++;
        //Create Embree geometry
        RTCGeometry geom = rtcNewGeometry(scene->embree_device, RTC_GEOMETRY_TYPE_TRIANGLE);
        if (geom == nullptr) {
            printf("Failed allocating geometry\n");
            return;
        }

        rtcSetGeometryVertexAttributeCount(geom, 1);
        float *vertices = (float *) rtcSetNewGeometryBuffer(geom, RTC_BUFFER_TYPE_VERTEX, 0, RTC_FORMAT_FLOAT3,
                                                            3 * sizeof(float), mesh->num_vertices);
        float *normals = (float *) rtcSetNewGeometryBuffer(geom, RTC_BUFFER_TYPE_VERTEX_ATTRIBUTE, 0, RTC_FORMAT_FLOAT3,
                                                           3 * sizeof(float), mesh->num_vertices);;
        unsigned int *indices = (unsigned int *) rtcSetNewGeometryBuffer(
            geom, RTC_BUFFER_TYPE_INDEX, 0, RTC_FORMAT_UINT3, 3 * sizeof(unsigned int), mesh->num_faces);
        if (!(vertices && indices && normals)) {
            printf("Failed allocating geometry buffer\n");
            rtcReleaseGeometry(geom);
            return;
        }

        for (uint32_t i = 0; i < mesh->num_vertices; i++) {
            bool flat_shaded = false;
            for (uint32_t face_index = 0; face_index < mesh->num_faces; face_index++) {
                if (mesh->materials[mesh->faces[face_index].material].flags & MATERIAL_IS_FLAT_SHADED) {
                    flat_shaded = true;
                    break;
                }
            }

            Vertex transformed_vertex = transform(mesh->vertices[i], mesh->normals[i], flat_shaded, data);
            vertices[3 * i + 0] = transformed_vertex.vertex.x;
            vertices[3 * i + 1] = transformed_vertex.vertex.y;
            vertices[3 * i + 2] = transformed_vertex.vertex.z;
            normals[3 * i + 0] = transformed_vertex.normal.x;
            normals[3 * i + 1] = transformed_vertex.normal.y;
            normals[3 * i + 2] = transformed_vertex.normal.z;
            scene->x_max = max(scene->x_max, transformed_vertex.vertex.x);
            scene->y_max = max(scene->y_max, transformed_vertex.vertex.y);
            scene->z_max = max(scene->z_max, transformed_vertex.vertex.z);
            scene->x_min = min(scene->x_min, transformed_vertex.vertex.x);
            scene->y_min = min(scene->y_min, transformed_vertex.vertex.y);
            scene->z_min = min(scene->z_min, transformed_vertex.vertex.z);
        }

        for (uint32_t i = 0; i < mesh->num_faces; i++) {
            indices[3 * i + 0] = mesh->faces[i].indices[0];
            indices[3 * i + 1] = mesh->faces[i].indices[1];
            indices[3 * i + 2] = mesh->faces[i].indices[2];
        }
        rtcSetGeometryOccludedFilterFunction(geom, occlusionFilter);
        rtcCommitGeometry(geom);
        //Add geometry to scene
        rtcAttachGeometry(scene->embree_scene, geom);
        rtcReleaseGeometry(geom);
    }

    int scene_trace_ray(Scene *scene, Vector3 origin, Vector3 direction, RayHit *hit) {
        struct RTCRayHit rayhit;

        rayhit.ray.org_x = origin.x;
        rayhit.ray.org_y = origin.y;
        rayhit.ray.org_z = origin.z;
        rayhit.ray.dir_x = direction.x;
        rayhit.ray.dir_y = direction.y;
        rayhit.ray.dir_z = direction.z;
        rayhit.ray.tnear = 0;
        rayhit.ray.tfar = INFINITY;
        rayhit.ray.mask = -1;
        rayhit.ray.flags = 0;
        rayhit.hit.geomID = RTC_INVALID_GEOMETRY_ID;
        rayhit.hit.instID[0] = RTC_INVALID_GEOMETRY_ID;

        rtcIntersect1(scene->embree_scene, &rayhit);

        hit->ghost_distance = rayhit.ray.tfar;

        //If we hit ghost mesh, keep tracing
        while ((rayhit.hit.geomID != RTC_INVALID_GEOMETRY_ID) && scene_is_ghost(scene, rayhit.hit.geomID)) {
            //printf("GeomID %d Distance %f\n",rayhit.hit.geomID,rayhit.ray.tfar);
            rayhit.ray.tnear = rayhit.ray.tfar + 0.0001;
            rayhit.ray.tfar = INFINITY;
            rayhit.hit.geomID = RTC_INVALID_GEOMETRY_ID;
            rayhit.hit.instID[0] = RTC_INVALID_GEOMETRY_ID;
            rtcIntersect1(scene->embree_scene, &rayhit);
        }


        if (rayhit.hit.geomID != RTC_INVALID_GEOMETRY_ID) {
            hit->mesh_index = rayhit.hit.geomID;
            hit->face_index = rayhit.hit.primID;
            hit->u = rayhit.hit.u;
            hit->v = rayhit.hit.v;


            //Interpolate normal
            float position_components[3];
            float normal_components[3];
            rtcInterpolate0(rtcGetGeometry(scene->embree_scene, rayhit.hit.geomID), rayhit.hit.primID, rayhit.hit.u,
                            rayhit.hit.v, RTC_BUFFER_TYPE_VERTEX, 0, position_components, 3);
            rtcInterpolate0(rtcGetGeometry(scene->embree_scene, rayhit.hit.geomID), rayhit.hit.primID, rayhit.hit.u,
                            rayhit.hit.v, RTC_BUFFER_TYPE_VERTEX_ATTRIBUTE, 0, normal_components, 3);
            hit->position = vector3(position_components[0], position_components[1], position_components[2]);
            hit->normal = vector3_normalize(vector3(normal_components[0], normal_components[1], normal_components[2]));
            hit->distance = rayhit.ray.tfar;
            return 1;
        }
        return 0;
    }

    int scene_trace_occlusion_ray(Scene *scene, Vector3 origin, Vector3 direction) {
        struct RTCRay ray;
        ray.org_x = origin.x;
        ray.org_y = origin.y;
        ray.org_z = origin.z;
        ray.dir_x = direction.x;
        ray.dir_y = direction.y;
        ray.dir_z = direction.z;
        ray.tnear = 1e-5;
        ray.tfar = INFINITY;
        ray.mask = -1;
        ray.flags = 0;

        rtcOccluded1(scene->embree_scene, &ray);

        return ray.tfar <= 0.0;
    }
}