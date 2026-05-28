# OpenRCT2-VehicleGenerator

Python interface to a curated subset of the OpenRCT2 sprite renderer. Builds
ride `.parkobj` files from a JSON config + OBJ meshes by running Embree-backed
isometric ray tracing through a pybind11 binding.

## Build

Requires:
- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- CMake 3.25+
- Embree 4 (`brew install embree` on macOS; system package on Linux)

```bash
uv sync
```

`uv sync` runs scikit-build-core to compile the native extension
(`openrct2_vehicle_generator/_native.so`) against Embree, then installs the
package in editable mode.

## Usage

```bash
# Build a .parkobj
uv run openrct2-vehicle-generator path/to/ride.json

# Single-viewpoint render to test/ (for quick iteration)
uv run openrct2-vehicle-generator --test path/to/ride.json

# Reuse previously rendered sprites; rebuild object.json + .parkobj only
uv run openrct2-vehicle-generator --skip-render path/to/ride.json
```

## Layout

| Path | What |
|---|---|
| `openrct2_vehicle_generator/` | Python package: loader, exporter, sprite renderer, JSON → object.json |
| `openrct2_vehicle_generator/ray_trace.py` | Thin wrapper around the native extension |
| `native/src/` | Subset of OpenRCT2's iso-render C++ (VectorMath, Mesh, Palette, RayTrace, Renderer) |
| `native/bindings.cpp` | pybind11 binding |
| `native/CMakeLists.txt` | Native build config (links Embree + pthread) |
| `pyproject.toml` | scikit-build-core build backend |
