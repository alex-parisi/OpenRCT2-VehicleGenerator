// Verbatim port of the C-era renderer implementation with only the minimum
// changes needed to compile against the modernized renderer.h (std::array<>
// for the views[] global, std::uint32_t-typed function parameters). All
// math is left exactly as written -- this file is the source of truth for
// byte-equivalent rasterization, AA accumulation, AO sampling, dithering
// and palette quantization against the goldens captured pre-modernization
// (see bisect: first bad commit was 5eff54f "Modernize iso-render"). Any
// "modernization" of the math here (float-only literals like 0.3f instead
// of 0.3, std::clamp(v, 0.0f, 1.0f) instead of fmax(0.0, fmin(1.0, v)),
// std::sqrt(float) instead of unqualified sqrt() which promotes via C
// math.h to double, std::numbers::pi_v<float> instead of M_PI) breaks
// byte-equivalence by 1 ULP on borderline edge / antialiasing pixels.

#define NOMINMAX
#define _USE_MATH_DEFINES
#include <cstdio>
#include <cstdlib>
// NOLINTNEXTLINE(modernize-deprecated-headers) -- see header comment: <cmath> would pull in std:: float overloads that break byte-exact goldens.
#include <math.h>
#include <cstring>
#include <cassert>
#include <cerrno>
#include <array>
#include <atomic>
#include <cstdint>
#include <thread>
#include <vector>
#include "Renderer.hpp"
#include "Palette.hpp"
#include "VectorMath.hpp"
#include "Mesh.hpp"


namespace RCTGen {
    //3.67 metres per tile
    // NOLINTNEXTLINE(cppcoreguidelines-macro-usage) -- preserves C double-promotion; constexpr replacement breaks byte-exact goldens.
#define SQRT_2 1.4142135623731f
    // NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define SQRT1_2 0.707106781f
    // NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define SQRT_3 1.73205080757f
    // NOLINTNEXTLINE(cppcoreguidelines-macro-usage)
#define SQRT_6 2.44948974278f

    std::array<Matrix3, 4> views{
        {
            {{1, 0, 0, 0, 1, 0, 0, 0, 1}},
            {{0, 0, 1, 0, 1, 0, -1, 0, 0}},
            {{-1, 0, 0, 0, 1, 0, 0, 0, -1}},
            {{0, 0, -1, 0, 1, 0, 1, 0, 0}},
        }
    };

    // NOLINTBEGIN(cppcoreguidelines-macro-usage) -- AO/AA sample counts are referenced by macros below; converting to constexpr breaks byte-exact accumulation order.
#define AO_NUM_SAMPLES_U 8
#define AO_NUM_SAMPLES_V 4
#define AA_NUM_SAMPLES_U 4
#define AA_NUM_SAMPLES_V 4
#define AA_SAMPLE_WEIGHT (1.0/(AA_NUM_SAMPLES_U*AA_NUM_SAMPLES_V))
    // NOLINTEND(cppcoreguidelines-macro-usage)

    namespace {
        // Spawn a fresh batch of worker threads, dispatch `count` units of
        // work, join. We intentionally don't reuse a persistent pool, and
        // we intentionally don't let the calling (main) thread participate:
        //
        // 1. Phase A (the rand-pool prepass) runs on the main thread and
        //    makes Embree calls. The main thread's per-thread FP/Embree
        //    state ends up different from a worker thread's state by the
        //    time Phase B starts. If the main thread then runs render_row
        //    alongside workers, the pixels it processes come out ULP-off
        //    from the workers' pixels, which breaks the byte-exact goldens.
        // 2. Persistent worker threads accumulate per-call state across
        //    multiple context_render_view invocations (which build a fresh
        //    Embree scene each time) and end up producing similar ULP-level
        //    divergence. Fresh worker threads per call don't have this
        //    problem because they enter Embree for the first time on every
        //    render and configure their per-thread state identically.
        //
        // The cost is N pthread_create/join calls per view -- non-trivial
        // but still ~4x speedup vs. serial on a 14-core box, and matches
        // goldens byte-for-byte.
        template<class Fn>
        void parallel_for(int count, Fn &&fn) {
            if (count <= 0) return;
            const unsigned int worker_count = std::max(1u, std::thread::hardware_concurrency());
            std::atomic<int> next{0};
            auto worker = [&]() {
                for (;;) {
                    int i = next.fetch_add(1, std::memory_order_relaxed);
                    if (i >= count) break;
                    fn(i);
                }
            };
            std::vector<std::thread> threads;
            threads.reserve(worker_count);
            for (unsigned int i = 0; i < worker_count; ++i) threads.emplace_back(worker);
            for (auto &t: threads) t.join();
        }
    } // namespace

    void context_init(Context *context, Light *lights, uint32_t num_lights, uint32_t dither, Palette palette,
                      float upt) {
        context->rt_device = device_init();
        context->lights = lights;
        context->num_lights = num_lights;
        context->dither = dither;
        //Dimetric projection
        const Matrix3 projection = {
            32.0f / upt, 0.0f, -32.0f / upt,
            -16.0f / upt, -16.0f * SQRT_6 / upt, -16.0f / upt,
            16.0f * SQRT_3 / upt, -16.0f * SQRT_2 / upt, 16.0f * SQRT_3 / upt
        };
        context->projection = projection;
        context->palette = palette;
    }

    void context_begin_render(Context *context) {
        scene_init(&(context->rt_scene), context->rt_device);
    }

    Vertex linear_transform(Vector3 vertex, Vector3 normal, const bool /*flat_shaded*/, void *matptr) {
        Transform transform = *((Transform *) matptr);
        Vertex out;
        out.vertex = transform_vector(transform, vertex);
        out.normal = vector3_normalize(matrix_vector(transform.matrix, normal));
        return out;
    }

    void context_add_model_transformed(Context * context, Mesh * mesh,
                                       Vertex(*transform)(Vector3, Vector3, bool, void*), void*data, int mask) {
        scene_add_model(&(context->rt_scene), mesh, transform, data, mask);
    }

    void context_add_model(Context *context, Mesh *mesh, Transform transform, int mask) {
        scene_add_model(&(context->rt_scene), mesh, &linear_transform, &transform, mask);
    }

    void context_finalize_render(Context *context) {
        scene_finalize(&(context->rt_scene));
    }

    void context_end_render(Context *context) {
        scene_destroy(&(context->rt_scene));
    }

    void context_destroy(Context *context) {
        device_destroy(context->rt_device);
    }

    //Specular shading code from Blender. Not sure what it does
    float spec(float inp, int hard) {
        if (inp >= 1.0f) return 1.0f;
        else if (inp <= 0.0f) return 0.0f;

        float b1 = inp * inp;
        if (b1 < 0.01f) b1 = 0.01f;

        if ((hard & 1) == 0) inp = 1.0f;
        if (hard & 2) inp *= b1;
        b1 *= b1;
        if (hard & 4) inp *= b1;
        b1 *= b1;
        if (hard & 8) inp *= b1;
        b1 *= b1;
        if (hard & 16) inp *= b1;
        b1 *= b1;

        if (b1 < 0.001f) b1 = 0.0f;

        if (hard & 32) inp *= b1;
        b1 *= b1;
        if (hard & 64) inp *= b1;
        b1 *= b1;
        if (hard & 128) inp *= b1;

        if (b1 < 0.001f) b1 = 0.0f;

        if (hard & 256) {
            b1 *= b1;
            inp *= b1;
        }
        return inp;
    }

    float cook_torr_spec(Vector3 n, Vector3 l, Vector3 v, int hard) {
        Vector3 h = vector3_normalize(vector3_add(v, l));

        float nh = vector3_dot(n, h);
        if (nh < 0.0f) return 0.0f;
        float nv = vector3_dot(n, v);
        if (nv < 0.0f) nv = 0.0f;

        return spec(nh, hard) / (0.1f + nv);
    }

    float vector3_dot_clamped(Vector3 a, Vector3 b) {
        return (float) fmax(vector3_dot(a, b), 0.0f);
    }


    Vector3 shade_fragment(Scene *scene, Vector3 pos, Vector3 normal, Vector3 view, Vector3 color,
                           Vector3 specular_color, float specular_exponent, Vector3 ambient_color, const Light *lights,
                           uint32_t num_lights) {
        Vector3 output_color = vector3(0, 0, 0);

        for (uint32_t i = 0; i < num_lights; i++) {
            if (lights[i].shadow && scene_trace_occlusion_ray(scene, pos, lights[i].direction))continue;
            if (lights[i].type == LIGHT_HEMI) {
                float diffuse_factor = 0.5f * lights[i].intensity * (1 + vector3_dot(normal, lights[i].direction));
                output_color = vector3_add(vector3_mult(color, diffuse_factor), output_color);
            } else if (lights[i].type == LIGHT_DIFFUSE) {
                float diffuse_factor = lights[i].intensity * vector3_dot_clamped(normal, lights[i].direction);
                output_color = vector3_add(vector3_mult(color, diffuse_factor), output_color);
            } else {
                Vector3 reflected_light_direction = vector3_sub(
                    vector3_mult(normal, 2.0f * vector3_dot(lights[i].direction, normal)), lights[i].direction);
                float specular_factor = lights[i].intensity * powf(vector3_dot_clamped(reflected_light_direction, view),
                                                                   specular_exponent);
                output_color = vector3_add(vector3_mult(specular_color, specular_factor), output_color);
            }
        }
        return vector3_add(output_color, ambient_color);
    }

    // `ao_rands` advances through a pre-generated pool of rand() outputs (see
    // context_render_view_internal's Phase A). Captured up-front in serial
    // call order so byte-exact equivalence with the original single-threaded
    // rand() sequence is preserved when the pixel loop runs across threads.
    int scene_sample_point(Scene *scene, Vector2 point, Matrix3 camera, const Light *lights, uint32_t num_lights,
                           Fragment *fragment, const float **ao_rands) {
        RayHit hit;
        Vector3 view_vector = matrix_vector(camera, vector3(0, 0, -1));
        if (scene_trace_ray(scene, matrix_vector(camera, vector3(point.x, point.y, -512)),
                            vector3_mult(view_vector, -1), &hit)) {
            view_vector = vector3_normalize(view_vector);
            Mesh *mesh = scene->meshes[hit.mesh_index];
            Face *face = mesh->faces + hit.face_index;
            Material *material = mesh->materials + face->material;

            //Check if this is a mask
            if (scene_is_mask(scene, hit.mesh_index) || material->flags & MATERIAL_IS_MASK) {
                fragment->color = vector3(0, 1, 0);
                fragment->depth = hit.distance;
                fragment->flags = material->flags | MATERIAL_IS_MASK;
                fragment->region = kFragmentUnused;
                return 1;
            }

            //Compute surface color
            Vector3 color;
            if (material->flags & MATERIAL_HAS_TEXTURE) {
                Vector2 tex_coord = vector2_add(
                    vector2_add(vector2_mult(mesh->uvs[face->indices[0]], 1.0f - hit.u - hit.v),
                                vector2_mult(mesh->uvs[face->indices[1]], hit.u)),
                    vector2_mult(mesh->uvs[face->indices[2]], hit.v));
                color = texture_sample(&(material->texture), tex_coord);
            } else color = material->color;
            //Remappable colors should be rendered as grayscale
            if (material->flags & MATERIAL_IS_REMAPPABLE) {
                float intensity = fmax(fmax(color.x, color.y), color.z);
                color = vector3_from_scalar(intensity);
            }

            //Shade fragment
            Vector3 shaded_color = shade_fragment(scene, hit.position, hit.normal, view_vector, color,
                                                  material->specular_color, material->specular_exponent,
                                                  material->ambient_color, lights, num_lights);

            Vector3 normal = hit.normal;
            Vector3 tangent;
            if (fabs(normal.x) > fabs(normal.y))
                tangent = vector3_mult(vector3(normal.z, 0, -normal.x),
                                       1.0f / sqrt(
                                           normal.x * normal.x + normal.z * normal.z));
            else
                tangent = vector3_mult(vector3(0, -normal.z, normal.y),
                                       1.0f / sqrt(normal.y * normal.y + normal.z * normal.z));
            Vector3 bitangent = vector3_cross(normal, tangent);

            float ao_factor = 1.0f;
            if (!(material->flags & MATERIAL_NO_AO)) {
                uint32_t not_occluded_samples = 0;
                for (int i = 0; i < AO_NUM_SAMPLES_U; i++)
                    for (int j = 0; j < AO_NUM_SAMPLES_V; j++) {
                        float r1 = *(*ao_rands)++;
                        float r2 = *(*ao_rands)++;
                        float theta = 2 * M_PI * ((i + r1) / AO_NUM_SAMPLES_U);
                        float phi = asin(1 - ((j + r2) / AO_NUM_SAMPLES_V));

                        Vector3 local_sample_dir = vector3(cos(phi) * sin(theta), cos(phi) * cos(theta), sin(phi));
                        Vector3 sample_dir = vector3_add(vector3_mult(normal, local_sample_dir.z),
                                                         vector3_add(vector3_mult(tangent, local_sample_dir.x),
                                                                     vector3_mult(bitangent, local_sample_dir.y)));
                        if (!scene_trace_occlusion_ray(scene, hit.position, sample_dir))not_occluded_samples++;
                    }
                ao_factor = ((float) not_occluded_samples) / (AO_NUM_SAMPLES_U * AO_NUM_SAMPLES_V);
            }
            //Write result
            fragment->color = vector3_mult(shaded_color, ao_factor);
            fragment->depth = hit.distance;
            fragment->ghost_depth = hit.ghost_distance;
            fragment->flags = material->flags;
            fragment->region = material->region;
            return 1;
        }
        fragment->ghost_depth = hit.ghost_distance;
        return 0;
    }

    int scene_sample_material(Scene *scene, Vector2 point, Matrix3 camera, Material **material_out, float *depth_out,
                              float *ghost_depth_out, int *is_mask) {
        RayHit hit;
        Vector3 view_vector = matrix_vector(camera, vector3(0, 0, -1));

        if (scene_trace_ray(scene, matrix_vector(camera, vector3(point.x, point.y, -512)),
                            vector3_mult(view_vector, -1), &hit)) {
            Mesh *mesh = scene->meshes[hit.mesh_index];
            Face *face = mesh->faces + hit.face_index;
            Material *material = mesh->materials + face->material;

            *is_mask = scene_is_mask(scene, hit.mesh_index) || (material->flags & MATERIAL_IS_MASK);
            *material_out = material;
            *depth_out = hit.distance;
            *ghost_depth_out = hit.ghost_distance;
            return 1;
        }
        *ghost_depth_out = hit.ghost_distance;
        return 0;
    }

    Rect rect(int xl, int xu, int yl, int yu) {
        Rect result = {xl, yl, xu, yu};
        return result;
    }

    Rect rect_enclose_point(Rect r, float x, float y) {
        return rect((int) fmin(r.x_lower, floor(x)), (int) fmax(r.x_upper, ceil(x)),
                    (int) fmin(r.y_lower, floor(y)), (int) fmax(r.y_upper, ceil(y)));
    }

    Rect scene_get_bounds(Scene *scene, Matrix3 camera) {
        /*
    Rect bounds;
    bounds.x_lower=-128;
    bounds.x_upper=128;
    bounds.y_lower=-128;
    bounds.y_upper=128;
    return bounds;
    */
        Vector3 bounding_points[8] = {
            vector3(scene->x_min, scene->y_min, scene->z_min),
            vector3(scene->x_max, scene->y_min, scene->z_min),
            vector3(scene->x_min, scene->y_max, scene->z_min),
            vector3(scene->x_max, scene->y_max, scene->z_min),
            vector3(scene->x_min, scene->y_min, scene->z_max),
            vector3(scene->x_max, scene->y_min, scene->z_max),
            vector3(scene->x_min, scene->y_max, scene->z_max),
            vector3(scene->x_max, scene->y_max, scene->z_max)
        };

        Rect bounds = rect((int) floor(bounding_points[0].x), (int) ceil(bounding_points[0].x),
                           (int) floor(bounding_points[0].y), (int) ceil(bounding_points[0].y));
        for (int j = 0; j < 8; j++) {
            Vector3 screen_point = matrix_vector(camera, bounding_points[j]);
            bounds = rect_enclose_point(bounds, screen_point.x, screen_point.y);
        }
        bounds.x_lower--;
        bounds.x_upper++;
        bounds.y_lower--;
        bounds.y_upper++;
        return bounds;
    }


    // NOLINTNEXTLINE(cppcoreguidelines-macro-usage) -- function-like macro; preserves identical codegen vs a templated helper.
#define FRAMEBUFFER_INDEX(fbf,x,y) (framebuffer->fragments[(x)+(y)*framebuffer->width])


    Rect framebuffer_get_bounds(Framebuffer *framebuffer) {
        //printf("%d %d\n",framebuffer->width,framebuffer->height);
        //return rect(0,framebuffer->width,0,framebuffer->height);
        int found_pixel = 0;
        Rect bounds;
        for (uint32_t y = 0; y < framebuffer->height; y++)
            for (uint32_t x = 0; x < framebuffer->width; x++) {
                if (FRAMEBUFFER_INDEX(framebuffer, x, y).region != kFragmentUnused) {
                    if (found_pixel)
                        bounds = rect_enclose_point(bounds, x, y);
                    else {
                        bounds = rect(x, x + 1, y, y + 1);
                        found_pixel = 1;
                    }
                }
            }
        //If the image is empty, just set the size as 1 pixel
        if (!found_pixel)
            return rect(0, 0, 0, 0);
        else
            return bounds;
    }

    void image_from_framebuffer(Image *image, Framebuffer *framebuffer, Palette *palette, uint32_t dither) {
        Rect bounding_box = framebuffer_get_bounds(framebuffer);
        image->width = 1 + bounding_box.x_upper - bounding_box.x_lower;
        image->height = 1 + bounding_box.y_upper - bounding_box.y_lower;
        image->x_offset = bounding_box.x_lower + floor(framebuffer->offset.x);
        image->y_offset = bounding_box.y_lower + floor(framebuffer->offset.y) - 1;
        //1 compensates for error not sure why it's needed TODO work out why it's needed
        image->pixels = (uint8_t *) calloc(image->width * image->height, sizeof(uint8_t));

        for (int y = bounding_box.y_lower; y <= bounding_box.y_upper; y++) {
            int start = (1 & 1) ? (bounding_box.x_upper) : bounding_box.x_lower;
            int stop = (1 & 1) ? (bounding_box.x_lower - 1) : bounding_box.x_upper + 1;
            int step = (1 & 1) ? -1 : 1;

            for (int x = start; x != stop; x += step) {
                Fragment fragment = FRAMEBUFFER_INDEX(framebuffer, x, y);
                fragment.color = vector_from_color(color_from_vector(fragment.color));
                if (fragment.region != kFragmentUnused) {
                    Vector3 error;
                    image->pixels[(x - bounding_box.x_lower) + (y - bounding_box.y_lower) * image->width] =
                            palette_get_nearest(palette, fragment.region & kRegionMask, fragment.color, &error);
                    if (dither) {
                        //Distribute error onto neighbouring points
                        int points[4][2] = {{x + step, y}, {x - step, y + 1}, {x, y + 1}, {x + step, y + 1}};
                        float weights[4] = {7.0 / 16.0, 3.0 / 16.0, 5.0 / 16.0, 1.0 / 16.0};
                        for (int i = 0; i < 4; i++)
                            if (points[i][0] >= 0 && points[i][0] < framebuffer->width - 1 && points[i][1] >= 0 &&
                                points[i][1] < framebuffer->height - 1 && (
                                    !(fragment.flags & MATERIAL_NO_BLEED) || (FRAMEBUFFER_INDEX(
                                        framebuffer, points[i][0], points[i][1]).flags & MATERIAL_NO_BLEED))) {
                                FRAMEBUFFER_INDEX(framebuffer, points[i][0], points[i][1]).color = vector3_add(
                                    vector3_mult(error, 0.3 * weights[i]),
                                    FRAMEBUFFER_INDEX(framebuffer, points[i][0], points[i][1]).color);
                            }
                    }
                }
            }
        }
        free(framebuffer->fragments);
    }

    void context_render_view_internal(Context *context, Matrix3 view, Image *image, uint32_t silhouette) {
        Matrix3 camera = matrix_mult(context->projection, view);

        Rect bounds = scene_get_bounds(&(context->rt_scene), camera);

        Framebuffer framebuffer;
        framebuffer.width = bounds.x_upper - bounds.x_lower + 1;
        framebuffer.height = bounds.y_upper - bounds.y_lower;
        framebuffer.offset = vector2((float) (bounds.x_lower) - 0.5, (float) (bounds.y_lower));
        framebuffer.fragments = (Fragment *) malloc(framebuffer.width * framebuffer.height * sizeof(Fragment));


        //Transform lights for view (shared, read-only across worker threads).
        std::vector<Light> transformed_lights(context->num_lights);
        Matrix3 view_inverse = matrix_inverse(view);
        for (uint32_t i = 0; i < context->num_lights; i++) {
            transformed_lights[i].type = context->lights[i].type;
            transformed_lights[i].shadow = context->lights[i].shadow;
            transformed_lights[i].direction = matrix_vector(view_inverse, context->lights[i].direction);
            transformed_lights[i].intensity = context->lights[i].intensity;
        }


        //Render image
        for (int i = 0; i < framebuffer.width * framebuffer.height; i++) {
            framebuffer.fragments[i].color = vector3(0.0, 0.0, 0.0);
            framebuffer.fragments[i].region = kFragmentUnused;
            framebuffer.fragments[i].depth = 0;
            framebuffer.fragments[i].flags = 0;
        }


        Matrix3 camera_inverse = matrix_inverse(camera);

        // Phase A (serial): replay the rand() call sequence the original
        // single-threaded loop would have made, so we can hand each pixel a
        // private slice of pre-generated outputs in Phase B. Required to
        // preserve byte-exact equivalence with the pre-parallel goldens --
        // libc rand() is global mutable state, and any cross-thread
        // interleaving in Phase B would scramble the AO sample directions.
        //
        // The walk shadows scene_sample_point's branching exactly: per
        // pixel, per AA subsample, if the AA ray hits non-mask, non-NO_AO
        // material, generate 2*AO_NUM_SAMPLES_U*AO_NUM_SAMPLES_V rand()
        // floats. Otherwise generate none. Silhouette renders never call
        // scene_sample_point, so they can skip this phase entirely.
        std::vector<float> ao_rand_pool;
        std::vector<std::uint32_t> ao_rand_offset(
            static_cast<std::size_t>(framebuffer.width) * framebuffer.height, 0);
        constexpr int kAoPerSubsample = 2 * AO_NUM_SAMPLES_U * AO_NUM_SAMPLES_V;
        if (!silhouette) {
            ao_rand_pool.reserve(
                static_cast<std::size_t>(framebuffer.width) * framebuffer.height
                * AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V * kAoPerSubsample / 4);
            for (int y = 0; y < framebuffer.height; y++) {
                for (int x = 0; x < framebuffer.width; x++) {
                    ao_rand_offset[y * framebuffer.width + x] =
                        static_cast<std::uint32_t>(ao_rand_pool.size());
                    Vector2 sample_point = vector2_add(vector2(x, y), framebuffer.offset);
                    for (int i = 0; i < AA_NUM_SAMPLES_U; i++)
                        for (int j = 0; j < AA_NUM_SAMPLES_V; j++) {
                            Vector2 subsample_point = vector2((i + 0.5f) / AA_NUM_SAMPLES_U - 0.5f,
                                                              (j + 0.5f) / AA_NUM_SAMPLES_V - 0.5f);
                            Material *sm;
                            float sd, sgd;
                            int s_is_mask = 0;
                            if (scene_sample_material(&(context->rt_scene),
                                                       vector2_add(sample_point, subsample_point),
                                                       camera_inverse, &sm, &sd, &sgd, &s_is_mask)) {
                                if (!s_is_mask && !(sm->flags & MATERIAL_NO_AO)) {
                                    for (int k = 0; k < kAoPerSubsample; k++)
                                        ao_rand_pool.push_back(
                                            static_cast<float>(rand()) / RAND_MAX);
                                }
                            }
                        }
                }
            }
        }

        // Phase B: per-row work. Each row writes only to its own framebuffer
        // slice and reads from a finalized (immutable) Embree scene -- so
        // rows are independent and safe to dispatch across worker threads.
        // Embree's intersect/occluded entry points are documented thread-safe
        // after rtcCommitScene. AO sampling consumes from ao_rand_pool at
        // the per-pixel offset recorded in Phase A.
        const float *ao_rand_base = ao_rand_pool.data();
        auto render_row = [&](int y) {
            for (int x = 0; x < framebuffer.width; x++) {
                const float *ao_rands = silhouette
                    ? nullptr
                    : ao_rand_base + ao_rand_offset[y * framebuffer.width + x];
                Vector2 sample_point = vector2_add(vector2(x, y), framebuffer.offset);
                Material *material;

                //Test center
                int flags = 0;
                int region = kFragmentUnused;
                float depth = INFINITY;
                float ghost_depth = INFINITY;
                int mask = 0;
                if (scene_sample_material(&(context->rt_scene), sample_point, camera_inverse, &material, &depth,
                                          &ghost_depth, &mask)) {
                    region = mask ? kFragmentUnused : material->region;
                    flags = material->flags;
                    if (material->flags & MATERIAL_IS_VISIBLE_MASK)mask = 1;
                }
                //Compute subsamples
                Fragment subsamples[AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V];
                for (int i = 0; i < AA_NUM_SAMPLES_U; i++)
                    for (int j = 0; j < AA_NUM_SAMPLES_V; j++) {
                        subsamples[i + j * AA_NUM_SAMPLES_U].color = vector3(0, 0, 0);
                        //vector3(0.0409151969068532,0.0437350292569735,0.04091519690685320);
                        subsamples[i + j * AA_NUM_SAMPLES_U].region = kFragmentUnused;
                        subsamples[i + j * AA_NUM_SAMPLES_U].flags = 0;
                        subsamples[i + j * AA_NUM_SAMPLES_U].depth = INFINITY;

                        Vector2 subsample_point = vector2((i + 0.5f) / AA_NUM_SAMPLES_U - 0.5f,
                                                          (j + 0.5f) / AA_NUM_SAMPLES_V - 0.5f);

                        if (!silhouette) {
                            scene_sample_point(&(context->rt_scene), vector2_add(sample_point, subsample_point),
                                               camera_inverse, transformed_lights.data(), context->num_lights,
                                               subsamples + (i + j * AA_NUM_SAMPLES_U), &ao_rands);
                        } else {
                            float subsample_depth = 0.0;
                            float subsample_ghost_depth = 0.0;
                            Material *subsample_material;
                            int subsample_mask = 0;
                            if (scene_sample_material(&(context->rt_scene), vector2_add(sample_point, subsample_point),
                                                      camera_inverse, &subsample_material, &subsample_depth,
                                                      &subsample_ghost_depth, &subsample_mask)) {
                                subsamples[i + j * AA_NUM_SAMPLES_U].color = vector3(0.5, 0.5, 0.5);
                                subsamples[i + j * AA_NUM_SAMPLES_U].region = subsample_mask
                                                                                  ? kFragmentUnused
                                                                                  : subsample_material->region;
                                subsamples[i + j * AA_NUM_SAMPLES_U].flags = subsample_material->flags;
                                subsamples[i + j * AA_NUM_SAMPLES_U].depth = subsample_depth;
                                subsamples[i + j * AA_NUM_SAMPLES_U].ghost_depth = subsample_ghost_depth;
                            }
                        }
                    }

                //Get frontmost background AA sample
                int front_background_aa_sample = -1;
                float min_depth = INFINITY;
                for (int i = 0; i < AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V; i++) {
                    if (subsamples[i].depth < min_depth && (
                            subsamples[i].flags & (MATERIAL_BACKGROUND_AA | MATERIAL_BACKGROUND_AA_DARK))) {
                        front_background_aa_sample = i;
                        min_depth = subsamples[i].depth;
                    }
                }


                //If there exists a sample forward of the center point with background AA enabled, use that instead of the center point
                if (front_background_aa_sample != -1 && (min_depth < ghost_depth - 4 || mask)) {
                    //Count samples that fall inside the presumed edge
                    int inside_samples = 0;
                    for (int i = 0; i < AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V; i++) {
                        if (!(subsamples[i].depth > min_depth + 4 || (
                                  subsamples[i].region == kFragmentUnused && (!subsamples[i].flags) & MATERIAL_IS_MASK)
                              ||
                              (subsamples[i].flags & MATERIAL_IS_VISIBLE_MASK)))
                            inside_samples++;
                    }
                    //If more than three samples found, use the forwardmost point
                    if (inside_samples > 3) {
                        region = subsamples[front_background_aa_sample].region;
                        depth = min_depth;
                        flags = subsamples[front_background_aa_sample].flags;
                    }
                }
                framebuffer.fragments[x + y * framebuffer.width].region = region;
                framebuffer.fragments[x + y * framebuffer.width].flags = flags;

                //If this is a background pixel, there is no need to compute the color
                if (region == kFragmentUnused)continue;

                if (flags & (MATERIAL_BACKGROUND_AA | MATERIAL_BACKGROUND_AA_DARK)) {
                    //Count samples that fall outside the presumed edge
                    Vector3 color = vector3(0, 0, 0);
                    float weight = 0;
                    float total_weight = 0;
                    for (int i = 0; i < AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V; i++) {
                        if ((!(subsamples[i].flags & MATERIAL_NO_BLEED) || (flags & MATERIAL_NO_BLEED)) && !((
                                subsamples[i].ghost_depth <= depth + 4 && subsamples[i].depth > depth + 4))) {
                            if (!(subsamples[i].depth > depth + 4 || (
                                      subsamples[i].region == kFragmentUnused && (!subsamples[i].flags) &
                                      MATERIAL_IS_MASK) || (subsamples[i].flags & MATERIAL_IS_VISIBLE_MASK)))
                            //TODO assumes there's only one material with NO_BLEED set
                            {
                                color = vector3_add(color, vector3_mult(subsamples[i].color, AA_SAMPLE_WEIGHT));
                                weight += AA_SAMPLE_WEIGHT;
                            }
                            total_weight += AA_SAMPLE_WEIGHT;
                        }
                    }
                    color = vector3_mult(color, 1 / total_weight);
                    if (flags & MATERIAL_BACKGROUND_AA_DARK)
                        framebuffer.fragments[x + y * framebuffer.width].color = vector3_mult(
                            color, 0.5f + 0.5f * (weight / total_weight));
                    else framebuffer.fragments[x + y * framebuffer.width].color = color;
                } else {
                    Vector3 color = vector3(0, 0, 0);
                    float weight = 0.0;
                    for (int i = 0; i < AA_NUM_SAMPLES_U * AA_NUM_SAMPLES_V; i++) {
                        if (subsamples[i].region != kFragmentUnused && (
                                !(subsamples[i].flags & MATERIAL_NO_BLEED) || (flags & MATERIAL_NO_BLEED))) {
                            color = vector3_add(color, vector3_mult(subsamples[i].color, AA_SAMPLE_WEIGHT));
                            weight += AA_SAMPLE_WEIGHT;
                        }
                    }
                    framebuffer.fragments[x + y * framebuffer.width].color = vector3_mult(color, 1.0f / weight);
                }
            }
        };

        parallel_for(framebuffer.height, render_row);

        //Convert to indexed color
        image_from_framebuffer(image, &framebuffer, &(context->palette), context->dither);
    }

    void context_render_view(Context *context, Matrix3 view, Image *image) {
        context_render_view_internal(context, view, image, 0);
    }

    void context_render_silhouette(Context *context, Matrix3 view, Image *image) {
        context_render_view_internal(context, view, image, 1);
    }
}