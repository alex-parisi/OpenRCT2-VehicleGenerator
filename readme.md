# OpenRCT2-VehicleGenerator

Python tool for generating custom vehicle `.parkobj` files for OpenRCT2.
Reads a ride JSON config + OBJ meshes, renders the full set of dimetric
sprites against Embree (via a pybind11 binding to a curated subset of
OpenRCT2's iso-render C++), and writes a ready-to-install parkobj.

A typical full single-rail-coaster vehicle (~4,640 sprites across two
car types with restraint animation) renders in **~10 seconds** on a
modern Mac.

---

## Quick start

```bash
# Build
uv sync

# Render the wooden example and write openrct2vg.ride.single_rail_on_wooden.parkobj
uv run openrct2-vehicle-generator examples/wooden/classic_wooden.json

# Install into OpenRCT2 (macOS path; adjust for Linux/Windows)
cp openrct2vg.ride.single_rail_on_wooden.parkobj \
   ~/Library/Application\ Support/OpenRCT2/object/

# Restart OpenRCT2 and the new train shows up in the vehicle dropdown
```

---

## Dependencies

| | |
|---|---|
| Python | 3.10+ |
| Build | [uv](https://docs.astral.sh/uv/), CMake ≥ 3.25, a C++23 compiler |
| Runtime | Embree 4 (`brew install embree` on macOS; distro package on Linux) |

`uv sync` invokes scikit-build-core to compile
`openrct2_vehicle_generator/_native.so` against your installed Embree,
then installs the package editably into `.venv/`.

---

## Usage

```bash
# Full render -> writes object/ and <id>.parkobj in the cwd
uv run openrct2-vehicle-generator path/to/ride.json

# Quick single-viewpoint render per vehicle frame (no full sprite set)
# Outputs to test/ for visual iteration on meshes/lighting/materials.
uv run openrct2-vehicle-generator --test path/to/ride.json

# Reuse sprites from a previous full run; rebuild object.json + parkobj only
uv run openrct2-vehicle-generator --skip-render path/to/ride.json
```

All paths in the ride JSON (`meshes`, `preview`, `map_Kd` lines in .mtl)
are resolved relative to the **current working directory**, so run from
the repo root unless you've copied assets elsewhere.

---

## Tests

`uv sync` installs the `dev` dependency group (pytest). The Python suite
covers the parts of the port that don't need Embree — palette tables and
nearest-color search, OBJ/MTL parsing and material classification, atlas
packing + blit/crop, the `images.dat` (G1) blob format, JSON loading +
validation + implied sprite flags, and the invariant that `count_sprites`
agrees with what `render_vehicle_frame` actually emits (the renderer is
stubbed so this runs without the native extension):

```bash
uv run pytest
```

The native C++ has its own unit tests under `native/test/`.

---

## Examples

One example vehicle is included under `examples/`.

| Example | Ride type | Notes |
|---|---|---|
| `wooden/` | `classic_wooden_rc` | A 4-rider classic wooden car (2 rows × 2 seats, lap-bar restraint animation, 8 custom lights). Geometry is generated procedurally by `scripts/build_wooden_car.py` + `scripts/build_wooden_restraint.py` (see [Procedural mesh generation](#procedural-mesh-generation) below). Renders **all 16 sprite groups** via `"sprites": "all"` so the vehicle looks correct if swapped onto more complex ride types in-game. |

Shared assets:

| Path | Used by |
|---|---|
| `textures/` | Generic material + remap textures (chassis, metal, seat, remap gradients) referenced from each example's `materials.mtl` |
| `examples/<ride>/{*.obj, materials.mtl, preview.png}` | Per-example meshes, materials, preview thumbnail |

Each example's JSON sets a custom `id` (`openrct2vg.ride.…`) so the
output doesn't collide with vanilla OpenRCT2 objects.

---

## Architecture

```
                  ┌──────────────────────────────────────────────────┐
                  │ openrct2_vehicle_generator/  (Python)            │
                  │   __main__.py    CLI                             │
                  │   loader.py      JSON -> Ride dataclass          │
                  │   mesh.py        OBJ/MTL parser + textures       │
                  │   sprite_renderer.py   per-group rotation tables │
                  │   exporter.py    -> object.json + .parkobj zip   │
                  │   ray_trace.py   thin wrapper over _native       │
                  │   palette.py / image.py / constants.py / types.py│
                  └──────────────────────────────────────────────────┘
                                       │
                                       ▼
                  ┌──────────────────────────────────────────────────┐
                  │ openrct2_vehicle_generator/_native.so            │
                  │   pybind11 binding (native/bindings.cpp)         │
                  │                                                  │
                  │ native/src/  (C++23, ~1500 LOC, copied verbatim  │
                  │   from OpenRCT2's iso-render):                   │
                  │     VectorMath, RayTrace, Renderer, Palette, Mesh│
                  └──────────────────────────────────────────────────┘
                                       │
                                       ▼
                                Embree 4 (BVH ray tracing, OS lib)
```

**What's in C++:** the rendering hot path — Embree scene management, AA
(4×4 subsamples), ambient occlusion (8×4 hemisphere samples), Blender-
style specular shading, Floyd-Steinberg palette dither, and image-frame
quantization. Around 1500 LOC of OpenRCT2 source compiled into the
extension; the binding marshalling layer is ~250 LOC.

**What's in Python:** everything that doesn't need to be fast — OBJ/MTL
parsing, JSON loading + validation (with implied-sprite-flag logic),
ride dataclasses, sprite-group dispatch (the rotation tables for each of
the 16 sprite groups), object.json construction, .parkobj zipping.

**Why this split:** the C++ pipeline (`makevehicle` + `maketrack` +
`merge_parkobj.py`) was already a working renderer but tightly coupled
to assimp / libpng / libzip / jansson. Replacing them with their Python
counterparts (Pillow, stdlib `json` / `zipfile`, a hand-written OBJ
parser) eliminates four native deps without giving up Embree speed —
the only native dep we still need is the ray tracer itself.

---

## Project layout

```
OpenRCT2-VehicleGenerator/
├── openrct2_vehicle_generator/      # Python package
│   ├── __init__.py
│   ├── __main__.py                  # CLI
│   ├── constants.py                 # enums, flag bits, material flags, AA/AO sample counts
│   ├── types.py                     # Ride / Vehicle / Model / MeshFrame / Light / IndexedImage
│   ├── loader.py                    # JSON -> Ride (implied sprite flags, validation)
│   ├── mesh.py                      # OBJ/MTL parser, material name classification, textures
│   ├── palette.py                   # RCT2 palette (matches Image.cpp's rct2_palette for PNG output)
│   ├── image.py                     # IndexedImage PNG read/write via Pillow
│   ├── sprite_renderer.py           # Rotation tables + per-group render dispatch
│   ├── ray_trace.py                 # Wrapper around _native (Context, render_view, rotate_*)
│   ├── exporter.py                  # build_ride_json + per-sprite PNG emission + parkobj zip
│   └── _native.so                   # Built by scikit-build-core
├── native/
│   ├── CMakeLists.txt               # find_package(embree 4), pybind11_add_module
│   ├── bindings.cpp                 # Context class + add_mesh + render_view marshalling
│   └── src/                         # Subset of OpenRCT2 iso-render (verbatim copies)
│       ├── VectorMath.{hpp,cpp}
│       ├── RayTrace.{hpp,cpp}      # Embree wrapper
│       ├── Renderer.{hpp,cpp}      # Per-pixel AA + AO + shading + dither
│       ├── Palette.{hpp,cpp}       # Internal palette + nearest-color search
│       ├── Mesh.{hpp,cpp}          # Mesh struct + texture_sample (assimp/PNG loaders stripped)
│       └── {Image.hpp,Color.hpp}   # Minimal struct definitions
├── examples/
│   └── wooden/                      # 4-rider classic wooden coaster car (procedurally generated meshes)
├── textures/                        # Shared material + remap textures
├── data/track_types.json            # OpenRCT2 ride-type definitions (sprite groups, car counts)
├── scripts/                         # Utility scripts
│   ├── ride_gen.py
│   ├── build_track_types.py
│   ├── build_wooden_car.py          # Blender script: chassis + body + seats -> examples/wooden/car.obj
│   ├── build_wooden_restraint.py    # Blender script: lap bar mesh    -> examples/wooden/restraint.obj
│   ├── split_atlas.py               # Post-process: split atlas PNGs into per-sprite PNGs
│   └── merge_parkobj.py             # Post-process: merge maketrack output into a parkobj
├── CMakeLists.txt                   # Top-level (currently passthrough; build is driven by native/)
├── pyproject.toml                   # scikit-build-core backend, pybind11+cmake build deps
└── readme.md
```

---

## Sprite output format

The exporter writes a single binary blob `images.dat` containing all
sprites, with a one-element `images` field in `object.json` referencing
it via OpenRCT2's `$LGX:` syntax:

```json
"images": ["$LGX:images.dat[0..2322]"]
```

This is the same format the vanilla OpenRCT2 ride parkobjs use. It is
**not** the `src_x`-atlas PNG format that the upstream C++ `makevehicle`
emits — that format is silently rejected by current OpenRCT2 (see notes
below).

### images.dat layout

```
+--------------------+--------------------+
| num_entries (u32)  | total_pixels (u32) |   8-byte header
+--------------------+--------------------+
| element 0          (16 bytes)           |
| element 1          (16 bytes)           |   num_entries * 16 bytes
| ...                                     |
| element N-1        (16 bytes)           |
+-----------------------------------------+
| sprite 0 pixels    (w * h bytes)        |
| sprite 1 pixels    (w * h bytes)        |   total_pixels bytes
| ...                                     |
+-----------------------------------------+
```

Each element is `u32 offset, i16 width, i16 height, i16 x_offset,
i16 y_offset, u16 flags, u16 zoom`. `flags = 0x0001` (`G1_FLAG_BMP`)
indicates raw indexed pixel data — palette index 0 is transparent. RLE
compression (`flags = 0x0008`) would be more compact but is not
implemented; raw BMP already loads in ~10ms in OpenRCT2's object picker.

### Why this format vs per-PNG or atlas-PNG

| Format | File size | Object-picker load | Status |
|---|---|---|---|
| Atlas PNG with `src_x` (upstream C++ `makevehicle`) | smallest | n/a | **Rejected** by OpenRCT2 (256×256 PNG size limit) |
| One PNG per sprite | 10× the blob size — PNG headers + 768B palette + zlib framing per sprite | seconds of lag (libpng called once per sprite) | Works but slow |
| `$LGX:images.dat` (current) | matches vanilla | ~one read, near-instant | Works, matches vanilla |

---

## OpenRCT2 format notes worth knowing

A handful of things bit us during development; preserving them here so
future contributors don't repeat the debugging.

| Gotcha | What |
|---|---|
| **PNG ≤ 256×256** | OpenRCT2's `ImageImporter` silently skips larger PNGs. The C++ pipeline's atlas-with-`src_x` format trips this. We sidestep it entirely by emitting `images.dat` (binary blob, no PNG involved). |
| **Object ID collisions** | A custom parkobj whose `id` matches a vanilla one (e.g. `rct1.ride.wooden_rc_trains`) won't override it cleanly — the engine keeps both around and you can't tell them apart in the dropdown. Use the `openrct2vg.ride.*` namespace (or your own `<author>.ride.*`) to avoid collision. |
| **Two RCT2 palettes** | OpenRCT2's source has *two* near-identical 256-color palette tables: the **internal** one (Palette.cpp `palette_rct2`) used for nearest-color quantization, and the **image** one (Image.cpp `rct2_palette`) written into PNG PLTE chunks. They differ at indices 0–9 (placeholder ramp vs all zeros) and 243–254 (red/orange remap1 vs green remap). PNG output **must** use the image palette — the engine recognizes the remap region by the PLTE layout. `palette.py` sources from Image.cpp. |
| **Vehicle objects don't bundle track sprites** | Track piece sprites come from OpenRCT2's built-in data per `ride_type`. A custom `.parkobj` only needs to provide vehicle sprites (4640 for a fully-fledged coaster + 3 preview entries = 4643 image entries — matches vanilla). The `maketrack` / `merge_parkobj.py` step from the C++ pipeline isn't required for vehicle-only customization. |
| **Object cache** | OpenRCT2 caches object metadata in `~/Library/Application Support/OpenRCT2/objects.idx`. After installing a new parkobj, **restart OpenRCT2** — it doesn't hot-reload the object dir. |
| **Coordinate convention** | Mesh OBJs use **+X = direction of travel (front of car)**, **+Y = up**, **+Z = passenger's right looking forward**. Geometry that should appear at the front of the moving train must sit at *positive* X. Get this wrong and the car renders backwards (rear seat back leads the train, etc.) even though the riders themselves face correctly — the peep mesh's facing is baked in. |
| **Orientation array axis order** | The `orientation` array in JSON is `[a, b, c]` but maps to `rotate_y(a) * rotate_z(b) * rotate_x(c)` per `exporter.py`. So `[0, 90, 0]` rotates around the **Z** (cross-car) axis, not Y. A lap bar that should swing top-to-bottom uses `[0, ±angle, 0]`; setting `[0, 0, angle]` would tip it sideways around the travel axis instead. |
| **Riders array = rows, not individuals** | Each entry in `riders[]` is one **seat row**, and `numSeatRows` is set to `len(riders)`. For a 2-across × 2-rows car (capacity 4), use **2** rider entries, each containing 2 peep mesh entries (left + right at ±Z). Using 4 separate single-peep entries makes the engine think it has 4 rows; the wooden-coaster ride type then only fills 2 of them and you see half-empty cars. |

---

## Authoring a new vehicle

1. **Model in Blender.** Export the car body and any sub-meshes (front
   variant, peep, restraint, peep+restraint locked-in pose) as `.obj`
   with a shared `materials.mtl`. Naming conventions in material names
   trigger special handling (mirrors `Mesh.cpp` in iso-render):

   | Substring | Effect |
   |---|---|
   | `Remap1` / `Remap2` / `Remap3` | Player-recolorable (palette regions 1/2/3) |
   | `Greyscale` | Shaded into greyscale ramp (palette region 4) |
   | `Peep` | Peep palette region (5) |
   | `Chain` | Chain lift palette region (6) |
   | `Mask` | Cutout mask (transparency) |
   | `VisibleMask` | Cutout mask that still blocks AO |
   | `NoAO` | Skip ambient occlusion sampling |
   | `Edge` / `DarkEdge` | Background-AA / dark background-AA edges |
   | `NoBleed` | Don't bleed pixel colors across atlas seams |
   | `FlatShaded` | Disable normal smoothing on this material |

2. **Write the JSON config.** Use one of the `examples/` configs as a
   starting point. Required fields are validated by `loader.py` — error
   messages will tell you what's missing or misshapen.

   The `sprites` field controls which of the 16 sprite groups to
   render. Two forms accepted:

   ```json
   "sprites": ["flat", "gentle_slopes", "banked_turns"]   // explicit list
   "sprites": "all"                                        // every group
   ```

   Use the explicit list when you want a minimal render for a vehicle
   that will only ever live on its native ride type — the loader ORs in
   implied flags too (`banking` → `diagonal_bank_transition`,
   `dive_loops` → `zero_g_rolls`, etc). The dive-loop implication is
   required: dive-loop sprites reuse the 8-frame zero-g rotations, so
   without `zero_g_rolls` the declared sprite count would not match the
   rendered set.

   Use `"all"` when you want the vehicle to look correct even if a
   player swaps it onto a more capable ride type in-game (e.g. a
   wooden-coaster vehicle being placed on a hyper-coaster track with
   loops and corkscrews). This renders the full set of 16 sprite
   groups regardless of what `ride_type` normally uses — a few seconds
   more render time, larger parkobj, but no glitchy fallback sprites.
   The `examples/wooden/` config uses `"all"` for this reason.

3. **Pick a unique `id`.** Use the `openrct2vg.ride.<name>` namespace
   or your own (`<author>.ride.<name>`) — must not collide with
   vanilla.

4. **Iterate.** Use `--test` for fast feedback (one viewpoint per
   vehicle frame, ~1 s). Switch to a full run (~10 s) when you're
   happy with the model + lighting.

5. **Install.** Copy the `.parkobj` into OpenRCT2's `object/`
   directory; restart OpenRCT2. It appears in the Roller Coasters
   build menu as its own entry (with the `name` you gave it) and is
   also offered as a swap-in vehicle option for any placed ride with
   matching `ride_type`.

---

## Procedural mesh generation

For simple vehicles (boxy chassis, bench seats, lap bars, etc.) it's often
faster to **generate the OBJ from a Blender Python script** than to model
by hand. The `examples/wooden/` car + restraint are built this way:

```bash
# Regenerate examples/wooden/car.obj from primitives
blender --background --python scripts/build_wooden_car.py

# Regenerate examples/wooden/restraint.obj (the lap bar)
blender --background --python scripts/build_wooden_restraint.py
```

Each script defines dimensions as constants at the top, builds the parts
out of `bpy.ops.mesh.primitive_*` calls, and exports through Blender's
OBJ exporter. A post-process step rewrites the `mtllib` line so the OBJ
points at the hand-authored `materials.mtl` instead of the auto-generated
sidecar `.mtl`. Iteration loop: edit constants → re-run script → run
`uv run openrct2-vehicle-generator --test …` → check sprite → repeat.

A few conventions worth knowing:

- **Build in OBJ space, not Blender space.** Blender's default OBJ
  exporter maps Blender `(X, Y, Z)` → OBJ `(X, -Z, Y)`. The build
  scripts use tiny `loc()` and `scl()` helpers that take coordinates in
  OBJ space (+X forward, +Y up, +Z right) and emit Blender-space
  positions and box scales. Saves you from doing the swap in your head
  for every primitive.
- **Pivot location matters for animated parts.** The lap bar's pivot is
  the bar's *forward-bottom* edge — i.e. the mesh is modelled extending
  from origin in the −X direction, so when it rotates around Z the free
  end swings up and over the riders. If you model with origin at the
  bar's center, the bar rotates around its center and tears through the
  body instead.
- **Don't fight the existing `materials.mtl`.** The scripts assign
  materials by name (`Remap1`, `Metal`, `Seat`, `ShinyMetal_Edge`, …)
  to leverage the name-based classification in `mesh.py`. Blender
  itself doesn't need the materials to be defined — just create empty
  `bpy.data.materials.new(name)` slots; the rendering pipeline picks
  them up from the `.mtl` file at OBJ load time.

---

## Light source format

Default lighting is hard-coded in `__main__.py` (a 9-light rig matching
the upstream C++ `default_lights()`). To override, add a `lights` array
to the ride JSON:

```json
"lights": [
  {"type": "diffuse",  "shadow": false, "direction": [0, -1, 0],   "strength": 0.1},
  {"type": "specular", "shadow": false, "direction": [1, 1.65, -1], "strength": 1.0}
]
```

`direction` is normalized on load. `shadow: true` makes the light
respect occlusion (slower; cast shadow rays per pixel).
