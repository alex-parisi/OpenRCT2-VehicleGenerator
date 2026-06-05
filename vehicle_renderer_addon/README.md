# vehicle_renderer_addon

The Blender 4.2+ add-on (extension). It is the UI and scene adapter only. The
whole pipeline (config validation, rendering, `.parkobj` assembly) lives in the
bundled [`openrct2_vehicle_generator`](../openrct2_vehicle_generator/) and
[`openrct2-x7-renderer`](https://pypi.org/project/openrct2-x7-renderer/) wheels.
This package reads the Blender scene, hands the core an in-memory config dict +
`Mesh` list, and surfaces the result in the viewport.

> Authoring a vehicle? Read the user-facing guides instead:
> [installation](../doc/blender-plugin-installation.md),
> [tutorial](../doc/blender-plugin-tutorial.md),
> [reference](../doc/blender-plugin-reference.md). This file documents the
> add-on's internals for contributors.

## How it works

1. Properties (`props.py`). Native Blender `PropertyGroup`s store the entire
   vehicle in the `.blend` file: ride-wide settings on `scene.vg_ride`, per-object
   role/animation on `object.vg_object`, per-material region/shading on
   `material.vg_material`. Enum item lists are sourced from the installed
   `openrct2_vehicle_generator` package, so the UI can never offer a value the
   loader would reject.
2. Panels (`panels.py`). Draw those properties in the 3D Viewport **OpenRCT2**
   sidebar tab: `VG_PT_ride` (ride-wide) and `VG_PT_object_view3d` (active
   object and its materials), plus the `UIList`s for colour presets, car types,
   and custom lights.
3. Scene adapter (`scene_to_ride.py`). The `bpy → Mesh` bridge. It bakes each
   object's world transform into an in-memory `Mesh` (no OBJ files written),
   converts Blender axes to OBJ space, builds the config dict the core expects,
   sorts riders into seat rows, and synthesizes the restraint animation frames
   (from a swing angle or sampled keyframes).
4. Operators (`operators.py`). `vg.test_render` renders a single viewpoint
   and loads it into an Image Editor for fast iteration; `vg.export_parkobj`
   renders every sprite on a background thread (spinner in the status bar) and
   writes the `.parkobj`. Both call the same core `build_ride` → render → export
   path the CLI uses.

`__init__.py` registers props → operators → panels in that order (panels draw
properties, so the property groups must exist first).

## Coordinate convention

The repo's build scripts place OBJ-space coords into Blender via
`loc(x, y, z) → (x, -z, y)`. Inverting that, a Blender vertex `(bx, by, bz)`
maps to OBJ `(bx, bz, -by)`, a proper rotation (det = +1), so triangle winding
is preserved. See the module docstring in `scene_to_ride.py` for the basis
matrix and per-object transform handling.

## Packaging model

Blender extensions run in an isolated Python environment and install only the
wheels listed in `blender_manifest.toml`; pip is never consulted at install time.
So everything the add-on imports must be vendored as a wheel for every
platform and Python version Blender ships. Three kinds of wheel are bundled
under `wheels/`:

| Wheel | Source | Variants |
|---|---|---|
| `openrct2_x7_renderer` | PyPI (Embree-vendored native extension) | per platform and CPython 3.11/3.13 |
| `numpy`, `pillow`, `pyyaml` | PyPI | per platform and CPython 3.11/3.13 |
| `openrct2_vehiclegenerator` | this repo (`uv build --wheel`, pure Python) | one `py3-none-any` for all targets |

`track_types.json` (read at runtime, shipped in the zip) maps each OpenRCT2 ride
type to the vehicle sprite groups it needs; regenerate it from `objects-master`
with [`scripts/build_track_types.py`](../scripts/build_track_types.py).

## Building the extension

```bash
# Local single-platform build for the Blender on THIS machine (macOS for now):
uv run python scripts/build_plugin_local.py

# Refresh the committed wheels/ + manifest for all target platforms:
uv build --wheel                              # build the front-end wheel first
uv run python scripts/collect_wheels.py       # download deps, regenerate manifest
blender --command extension build             # zip the extension
```

`build_plugin_local.py` stages everything in a temp dir and never touches the
committed `wheels/` or `blender_manifest.toml`. Multi-platform release zips are
produced by CI ([`.github/workflows/build-plugin.yml`](../.github/workflows/build-plugin.yml)),
triggered manually or on a `v*` tag.

## Source layout

```
vehicle_renderer_addon/
├── __init__.py            # register/unregister (props -> operators -> panels)
├── blender_manifest.toml  # extension manifest (id, version, platforms, wheels)
├── props.py               # PropertyGroups: scene/object/material data
├── panels.py              # 3D Viewport OpenRCT2 sidebar panels + UILists
├── operators.py           # vg.test_render + threaded vg.export_parkobj
├── scene_to_ride.py       # bpy -> Mesh adapter + config-dict builder
├── track_types.json       # ride type -> sprite-group requirements (bundled)
└── wheels/                # vendored wheels (regenerated by collect_wheels.py)
```

## License

GPL-3.0-or-later. The bundled wheels carry Embree + TBB (Apache-2.0); their
license texts ship alongside in the extension zip.
