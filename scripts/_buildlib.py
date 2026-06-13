"""Shared constants and helpers for the Blender add-on build scripts.

Used by both ``collect_wheels.py`` (CI: bundle every-platform wheels) and
``build_plugin_local.py`` (dev: build a single-platform zip). Keeping the
renderer pin, dependency list, and manifest rewriting in one place stops the two
scripts from drifting; previously each carried its own copy of
``RENDERER_VERSION``, the ``pip download`` invocation, and the manifest regex.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Sibling workspace sources. These generator repos are checked out side by side
# as submodules of the OpenRCT2-Tools meta-repo; when that layout is present the
# local build bundles the renderer + shared layer built FROM THESE SOURCES, so
# unreleased meta-repo changes are picked up. Without the siblings (a standalone
# repo checkout, or CI) the build falls back to the pinned PyPI releases. See
# acquire_inrepo_wheels.
WORKSPACE = REPO.parent
RENDERER_SRC = WORKSPACE / "OpenRCT2-X7-Renderer"
OBJECTCOMMON_SRC = WORKSPACE / "OpenRCT2-ObjectCommon"

# Add-on label -> source directory (room for more add-ons later).
ADDONS = {"vehicle": "vehicle_renderer_addon"}

# External renderer: PyPI dist name, wheel-filename prefix, and the exact version
# to bundle. Keep RENDERER_VERSION in step with the floor in pyproject.toml's
# `openrct2-x7-renderer>=...` dependency.
RENDERER_DIST = "openrct2-x7-renderer"
RENDERER_PREFIX = "openrct2_x7_renderer"
RENDERER_VERSION = "0.3.8"

# Shared layer (openrct2_object_common): PyPI dist name, wheel-filename prefix,
# and the exact version to bundle. Pure Python (py3-none-any), so one wheel
# covers every target. Downloaded from PyPI alongside the renderer. Keep
# OBJECTCOMMON_VERSION in step with the floor in pyproject.toml's
# `OpenRCT2-ObjectCommon>=...` dependency.
OBJECTCOMMON_DIST = "OpenRCT2-ObjectCommon"
OBJECTCOMMON_PREFIX = "openrct2_objectcommon"
OBJECTCOMMON_VERSION = "0.2.3"

# This repo's pure-Python front-end wheel (built + placed by the caller).
FRONTEND_PREFIX = "openrct2_vehiclegenerator"

# Runtime deps that must be vendored into the add-on alongside the renderer.
DEPS = ("numpy", "pillow", "pyyaml")


def run(cmd: list[str], *, capture: bool = False) -> str:
    """Run a command, echoing it; raise on failure. Return stdout if captured."""
    print("+", " ".join(cmd))
    res = subprocess.run(
        cmd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return res.stdout if capture else ""


def renderer_spec() -> str:
    """The pinned ``dist==version`` requirement for the bundled renderer."""
    return f"{RENDERER_DIST}=={RENDERER_VERSION}"


def objectcommon_spec() -> str:
    """The pinned ``dist==version`` requirement for the bundled shared layer."""
    return f"{OBJECTCOMMON_DIST}=={OBJECTCOMMON_VERSION}"


def pip_download_cmd(
    pip_prefix: list[str],
    *,
    dest: Path,
    py_version: str,
    abi: str,
    platform_tags: list[str],
    specs: list[str],
) -> list[str]:
    """Build a ``pip download`` command for one (Python, platform) target.

    ``pip_prefix`` is the interpreter+pip invocation to prepend, e.g.
    ``[sys.executable, "-m", "pip"]`` (collect_wheels, already inside the uv env)
    or ``["uv", "run", "--with", "pip", "python", "-m", "pip"]``
    (build_plugin_local). Several ``platform_tags`` let pip pick each package's
    compatible wheel (numpy and Pillow publish different OS minimums).
    """
    cmd = [
        *pip_prefix,
        "download",
        "--only-binary=:all:",
        "--no-deps",
        "--python-version",
        py_version,
        "--implementation",
        "cp",
        "--abi",
        abi,
        "-d",
        str(dest),
    ]
    for tag in platform_tags:
        cmd += ["--platform", tag]
    return cmd + specs


def one_renderer_wheel(d: Path) -> Path:
    """The single renderer wheel in ``d`` (raises if not exactly one)."""
    wheels = list(d.glob(f"{RENDERER_PREFIX}-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"Expected one renderer wheel in {d}, found {wheels}")
    return wheels[0]


def wheels_block(names: list[str]) -> str:
    """The manifest ``wheels = [...]`` block listing each wheel filename."""
    entries = sorted(set(names))
    return "\n".join(["wheels = ["] + [f'    "./wheels/{n}",' for n in entries] + ["]"])


def set_toml_array(text: str, key: str, block: str) -> str:
    """Replace the ``{key} = [...]`` array in ``text`` with ``block``.

    Raises ``SystemExit`` if the array isn't found exactly once.
    """
    new_text, n = re.subn(rf"{key} = \[.*?\]", block, text, count=1, flags=re.DOTALL)
    if n != 1:
        raise SystemExit(f"Could not find a '{key} = [...]' block in the manifest")
    return new_text


def has_local_source(src: Path) -> bool:
    """True if `src` is a buildable Python project (has a pyproject.toml)."""
    return (src / "pyproject.toml").is_file()


def ensure_embree_env() -> None:
    """Point CMake at a Homebrew Embree when no explicit hint is set.

    Building the renderer wheel is a native scikit-build/CMake compile; on a dev
    machine Embree is usually a `brew install embree`. Mirror how `uv sync` finds
    it so the local build works without the caller exporting EMBREE_ROOT.
    """
    if os.environ.get("EMBREE_ROOT") or os.environ.get("CMAKE_PREFIX_PATH"):
        return
    brew = shutil.which("brew")
    if brew is None:
        return
    try:
        prefix = run([brew, "--prefix", "embree"], capture=True).strip()
    except subprocess.CalledProcessError:
        return
    if prefix:
        os.environ["EMBREE_ROOT"] = prefix
        os.environ["CMAKE_PREFIX_PATH"] = prefix


def build_shared_wheel(dest: Path) -> None:
    """Build the pure-Python shared layer from the workspace source into `dest`."""
    run(["uv", "build", "--wheel", str(OBJECTCOMMON_SRC), "--out-dir", str(dest)])


def build_renderer_wheel(dest: Path, py_version: str) -> None:
    """Build the native renderer from the workspace source for Blender's CPython.

    scikit-build-core does not vendor Embree, so the freshly built wheel is run
    through `delocate-wheel` to copy the Embree/TBB dylibs into it — the same
    vendoring the released PyPI wheels ship. Leaves one importable renderer wheel
    in `dest`.
    """
    ensure_embree_env()
    raw = dest / "_renderer_raw"
    raw.mkdir(exist_ok=True)
    run(
        [
            "uv",
            "build",
            "--wheel",
            str(RENDERER_SRC),
            "--python",
            py_version,
            "--out-dir",
            str(raw),
        ]
    )
    run(
        [
            "uv",
            "run",
            "--with",
            "delocate",
            "delocate-wheel",
            "--wheel-dir",
            str(dest),
            str(one_renderer_wheel(raw)),
        ]
    )
    shutil.rmtree(raw)


def acquire_inrepo_wheels(
    pip_prefix: list[str],
    *,
    dest: Path,
    py_version: str,
    abi: str,
    platform_tags: list[str],
    dep_specs: list[str],
) -> None:
    """Stage the renderer, shared layer, and third-party deps into `dest`.

    The two in-repo packages (renderer + shared layer) are built from the local
    workspace sources when present, so a local meta-repo build always reflects the
    current source — not whatever is pinned on PyPI. Without the sibling sources
    (standalone checkout / CI) they are downloaded from PyPI at the pinned
    versions instead. Third-party deps (numpy/pillow/pyyaml) always come from PyPI.
    """
    pypi_specs = list(dep_specs)

    if has_local_source(OBJECTCOMMON_SRC):
        print(f"  shared layer: building from {OBJECTCOMMON_SRC}")
        build_shared_wheel(dest)
    else:
        pypi_specs.append(objectcommon_spec())

    if has_local_source(RENDERER_SRC):
        print(f"  renderer: building from {RENDERER_SRC} (delocate-vendored Embree)")
        build_renderer_wheel(dest, py_version)
    else:
        pypi_specs.append(renderer_spec())

    run(
        pip_download_cmd(
            pip_prefix,
            dest=dest,
            py_version=py_version,
            abi=abi,
            platform_tags=platform_tags,
            specs=pypi_specs,
        )
    )
