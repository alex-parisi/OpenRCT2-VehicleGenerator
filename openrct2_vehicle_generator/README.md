# openrct2_vehicle_generator

The pure-Python front-end that turns a ride config (YAML/JSON or an in-memory
dict) into a finished OpenRCT2 `.parkobj`. It owns the vehicle-specific parts
(the config schema, the sprite-group rotation tables, and `.parkobj` assembly)
and calls into [`openrct2-x7-renderer`](https://pypi.org/project/openrct2-x7-renderer/)
for the actual ray tracing, OBJ/MTL parsing, RCT2 palette, and `images.dat`
packing.

Heavily inspired by X7's [RCTGen](https://github.com/X123M3-256/RCTGen).

## How it works

A render goes through three stages, each in its own module:

1. Load (`loader.py`). `build_ride(config, meshes, preview)` validates a
   parsed config dict and returns a `Ride` dataclass (`types.py`). It resolves
   every config string to a flag/enum via the name→enum tables in `constants.py`,
   ORs in implied sprite groups (banking pulls in diagonal-bank transitions;
   `dive_loops` pulls in `zero_g_rolls`), broadcasts per-frame mesh/position/
   orientation lists, and derives each car's seat count from its rider meshes.
   `load_ride(path)` is the convenience wrapper that parses the file and loads
   meshes + preview from disk first.
2. Render (`sprite_renderer.py`). For each enabled sprite group, a rotation
   table (`_Rot(num_frames, pitch, roll, yaw)`) describes the poses OpenRCT2
   expects. `render_vehicle_frame` walks the ordered render plan, builds a view
   matrix per yaw step, and renders each against a finalized X7 scene. The same
   plan feeds `count_sprites`, so the declared sprite count can never drift
   from the rendered set. Independent `render_view` calls are issued across a
   small thread pool to overlap the native renderer's per-image tails.
3. Export (`exporter.py`). `build_ride_json` emits the OpenRCT2 `object.json`
   (properties, cars, sprite groups, colour presets, loading positions).
   `export_ride` renders every sprite for every car (plus a peep pass per rider
   row), concatenates them into one `images.dat`, references it via the `$LGX:`
   syntax, and zips the pair into `<id>.parkobj`.

`__main__.py` wires these together behind the `openrct2-vehicle-generator` CLI,
reusing X7's `run_cli`/`make_context` helpers so the CLI flags, config parsing,
and default light rig match the renderer's.

## Coordinate convention

Mesh OBJs use **+X = direction of travel (front of car)**, **+Y = up**,
**+Z = passenger's right**. Geometry that should lead the moving train sits at
positive X. Orientation Euler angles `[a, b, c]` (degrees) are applied as
`rotate_y(a) @ rotate_z(b) @ rotate_x(c)`.

## Public API

```python
from openrct2_vehicle_generator.loader import load_ride, build_ride
from openrct2_vehicle_generator.exporter import export_ride, export_ride_to, build_ride_json
from openrct2_vehicle_generator.types import Ride, Vehicle
from openrct2_x7_renderer.cli import make_context

ride = load_ride("examples/wooden/classic_wooden.yaml")   # parse + load meshes
context = make_context(lights=[], units_per_tile=ride.units_per_tile, test=False)
export_ride(ride, context, output_directory=".")          # writes <id>.parkobj
```

| Function | Module | Purpose |
|---|---|---|
| `load_ride(path)` | `loader` | Parse a config file, load its meshes + preview, build a `Ride`. |
| `build_ride(config, meshes, preview)` | `loader` | Build a `Ride` from an already-parsed dict + in-memory meshes (used by the Blender add-on, which has no files to read). |
| `build_ride_json(ride)` | `exporter` | Produce the `object.json` dict (no rendering). |
| `export_ride(ride, ctx, out_dir)` | `exporter` | Render all sprites and write `<id>.parkobj` into `out_dir`. |
| `export_ride_to(ride, ctx, parkobj_path, work_dir)` | `exporter` | Same, with caller-chosen paths; `skip_render=True` reuses a prior `images.dat`. |
| `export_ride_test(ride, ctx)` | `exporter` | One viewpoint per frame to `test/` for fast iteration. |
| `count_sprites(sprite_flags, vehicle_flags)` | `sprite_renderer` | Number of sprites a car will produce. |

## Sprite groups

The 16 groups (bit order in `SpriteFlag`, names in `SPRITE_GROUP_NAMES`):

`flat`, `gentle_slopes`, `steep_slopes`, `vertical_slopes`, `diagonals`,
`banked_turns`, `inline_twists`, `slope_bank_transition`,
`diagonal_bank_transition`, `sloped_bank_transition`, `banked_sloped_turns`,
`banked_slope_transition`, `corkscrews`, `zero_g_rolls`,
`diagonal_sloped_bank_transition`, `dive_loops`.

The loader ORs in implied groups, so the rendered set may be a superset of what
was requested. A full coaster (`sprites: all`) is ~4,640 vehicle sprites per car
plus 3 preview entries. `restraint_animation` adds 12 sprites per car (3 extra
animation frames × 4 views each).

## CLI

```bash
# Fast single-viewpoint render per frame, written to test/.
uv run openrct2-vehicle-generator --test path/to/ride.yaml

# Full render: writes object/ and <id>.parkobj in the current directory.
uv run openrct2-vehicle-generator path/to/ride.yaml

# Reuse the previous run's images.dat (rebuild object.json only).
uv run openrct2-vehicle-generator --skip-render path/to/ride.yaml
```

All paths in the ride config (`meshes`, `preview`, and `map_Kd` lines in `.mtl`
files) resolve relative to the **current working directory**.

For the complete config schema (every top-level field, vehicle entry, and
model/rider entry) see the [repository README](../README.md#ride-config).

## Performance

Sprite rendering is parallelized across a thread pool sized to
`min(8, os.cpu_count())`. Set `OPENRCT2VG_RENDER_THREADS` to override it
(`OPENRCT2VG_RENDER_THREADS=1` forces serial rendering); output is
byte-identical regardless of worker count. The renderer's own per-pixel thread
pool is controlled separately by `OPENRCT2_X7_NUM_THREADS` (see the
[X7 renderer docs](https://github.com/alex-parisi/OpenRCT2-X7-Renderer)).

## Source layout

```
openrct2_vehicle_generator/
├── __init__.py          # package version
├── __main__.py          # `openrct2-vehicle-generator` CLI entry point
├── constants.py         # SpriteFlag/RideFlag/VehicleFlag enums + name<->enum tables
├── types.py             # Ride / Vehicle dataclasses (+ re-exported render primitives)
├── loader.py            # config dict -> Ride (validation, implied flags, frames)
├── sprite_renderer.py   # rotation tables, count_sprites, per-frame render dispatch
└── exporter.py          # object.json builder + images.dat packing + .parkobj zip
```

## Development

```bash
uv sync --group dev          # install the package + dev tools
uv run pytest                # tests (coverage on by default via pyproject.toml)
uv run ruff check .          # lint
uv run mypy                  # type-check
```

The package is pure Python; the Embree-backed renderer installs from PyPI as a
prebuilt wheel, so no compiler or CMake is needed.

## License

GPL-3.0-or-later. Depends on `openrct2-x7-renderer` (also GPL-3.0-or-later;
its distributed wheels bundle Embree and TBB, Apache-2.0).
