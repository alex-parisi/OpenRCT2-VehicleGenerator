#!/usr/bin/env python3
"""Build the Blender extension fresh for THIS machine and its Blender.

The renderer (``openrct2-x7-renderer``) and shared layer (``OpenRCT2-ObjectCommon``)
ship released PyPI wheels, but inside the OpenRCT2-Tools meta-repo they are built
from the local workspace sources so unreleased changes are picked up; outside the
meta-repo the pinned PyPI releases are used instead. This script produces a
single-platform zip you can install into your local Blender right now:

  1. Build this repo's pure-Python front-end wheel (``openrct2_vehiclegenerator``,
     ``py3-none-any``) with `uv build --wheel`.
  2. Acquire the renderer wheel + the ``OpenRCT2-ObjectCommon`` shared layer (from
     the workspace, or PyPI) and numpy/pillow/pyyaml from PyPI, for your platform
     and your Blender's CPython. A workspace-built renderer is delocated so Embree
     is vendored into the wheel.
  3. Stage the add-on with a local-only manifest (just this platform + these
     wheels) and run `blender --command extension build`.

The committed <addon>/wheels/ and blender_manifest.toml are never touched;
everything is staged in a temp dir.

macOS only for now (the platform/arch mapping below covers macOS). For a
Linux/Windows release, use CI (.github/workflows/build-plugin.yml).

Usage:
    uv run python scripts/build_plugin_local.py [--install] [--no-verify] [-o dist]
"""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from _buildlib import (
    ADDONS,
    DEPS,
    FRONTEND_PREFIX,
    REPO,
    acquire_inrepo_wheels,
    one_renderer_wheel,
    run,
    set_toml_array,
    wheels_block,
)


def blender_python_tag() -> tuple[str, str]:
    """Return (python_version, abi_tag) for the `blender` on PATH, e.g. ('3.13','cp313')."""
    out = run(
        [
            "blender",
            "--background",
            "--python-expr",
            "import sys;print('PYTAG', sys.version_info.major, sys.version_info.minor)",
        ],
        capture=True,
    )
    m = re.search(r"PYTAG (\d+) (\d+)", out)
    if not m:
        raise SystemExit("Could not determine Blender's Python version.")
    major, minor = m.group(1), m.group(2)
    return f"{major}.{minor}", f"cp{major}{minor}"


def local_target() -> tuple[str, list[str]]:
    """Return (manifest_platform, pip_platform_tags) for the current macOS arch."""
    if platform.system() != "Darwin":
        raise SystemExit(
            "This script builds for macOS only.\n"
            "For a Linux/Windows release build, run the CI workflow "
            "(.github/workflows/build-plugin.yml)."
        )
    arch = platform.machine()
    if arch == "arm64":
        return "macos-arm64", [
            "macosx_11_0_arm64",
            "macosx_12_0_arm64",
            "macosx_13_0_arm64",
            "macosx_14_0_arm64",
        ]
    if arch == "x86_64":
        return "macos-x64", [
            "macosx_11_0_x86_64",
            "macosx_12_0_x86_64",
            "macosx_13_0_x86_64",
            "macosx_14_0_x86_64",
        ]
    raise SystemExit(f"Unsupported macOS arch: {arch}")


def dep_specs() -> list[str]:
    """Pin deps to the versions resolved in the build env."""
    out = run(
        [
            "uv",
            "run",
            "python",
            "-c",
            "import importlib.metadata as m;"
            f"print(' '.join(f'{{d}}=={{m.version(d)}}' for d in {DEPS!r}))",
        ],
        capture=True,
    )
    return out.split()


def build_frontend_wheel(out_dir: Path) -> Path:
    """Build this repo's pure-Python front-end wheel (py3-none-any)."""
    run(["uv", "build", "--wheel", "--out-dir", str(out_dir)])
    wheels = list(out_dir.glob(f"{FRONTEND_PREFIX}-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"Expected one front-end wheel in {out_dir}, found {wheels}")
    return wheels[0]


def acquire_packages(out_dir: Path, py_version: str, abi: str, pip_platforms: list[str]) -> None:
    """Stage the renderer, shared layer, and deps into `out_dir`.

    In the meta-repo the renderer + shared layer are built from the local
    workspace sources (so unreleased changes ship); a standalone checkout / CI
    falls back to the pinned PyPI releases. Deps always come from PyPI. See
    `_buildlib.acquire_inrepo_wheels`.
    """
    acquire_inrepo_wheels(
        ["uv", "run", "--with", "pip", "python", "-m", "pip"],
        dest=out_dir,
        py_version=py_version,
        abi=abi,
        platform_tags=pip_platforms,
        dep_specs=dep_specs(),
    )


def stage_addon(stage: Path, wheels_src: Path, manifest_platform: str, addon_dir: Path) -> None:
    """Copy add-on source into `stage` with a local-only manifest + wheels."""
    for item in addon_dir.iterdir():
        if item.suffix in {".py", ".toml", ".json"} and item.is_file():
            shutil.copy2(item, stage / item.name)
    stage_wheels = stage / "wheels"
    stage_wheels.mkdir()
    for whl in wheels_src.glob("*.whl"):
        shutil.copy2(whl, stage_wheels / whl.name)

    names = [p.name for p in stage_wheels.glob("*.whl")]
    manifest = stage / "blender_manifest.toml"
    text = manifest.read_text(encoding="utf-8")
    text = set_toml_array(text, "platforms", f'platforms = ["{manifest_platform}"]')
    text = set_toml_array(text, "wheels", wheels_block(names))
    manifest.write_text(text, encoding="utf-8")


def verify_wheel(wheel: Path) -> None:
    """Import the renderer wheel in a clean env to catch an unvendored Embree."""
    run(
        [
            "uv",
            "run",
            "--with",
            str(wheel),
            "python",
            "-c",
            "import openrct2_x7_renderer._x7_renderer as n;print('embree ok:', n.LIGHT_DIFFUSE)",
        ]
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the Blender extension locally.")
    ap.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=REPO / "dist",
        help="where to write the .zip (default: dist/)",
    )
    ap.add_argument(
        "--install", action="store_true", help="install the built zip into Blender afterwards"
    )
    ap.add_argument(
        "--no-verify",
        action="store_true",
        help="skip the standalone import check of the renderer wheel",
    )
    ap.add_argument("--addon", choices=ADDONS, default="vehicle", help="which add-on to build")
    args = ap.parse_args()
    addon_dir = REPO / ADDONS[args.addon]

    manifest_platform, pip_platforms = local_target()
    py_version, abi = blender_python_tag()
    print(f"Target: {manifest_platform}, Blender CPython {py_version} ({abi})")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="vg_plugin_") as tmp:
        tmp = Path(tmp)
        wheels = tmp / "wheels"
        wheels.mkdir()
        stage = tmp / "addon"
        stage.mkdir()

        build_frontend_wheel(wheels)
        acquire_packages(wheels, py_version, abi, pip_platforms)
        if not args.no_verify:
            verify_wheel(one_renderer_wheel(wheels))
        stage_addon(stage, wheels, manifest_platform, addon_dir)

        run(
            [
                "blender",
                "--command",
                "extension",
                "build",
                "--source-dir",
                str(stage),
                "--output-dir",
                str(args.output_dir),
            ]
        )

    zips = sorted(args.output_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    built = zips[0] if zips else None
    print(f"\nBuilt: {built}")

    if args.install and built:
        try:
            run(
                [
                    "blender",
                    "--command",
                    "extension",
                    "install-file",
                    "-r",
                    "user_default",
                    "-e",
                    str(built),
                ]
            )
            print("Installed. Restart Blender if it was open.")
        except subprocess.CalledProcessError:
            print(
                "Auto-install failed. Install manually: Blender > Preferences > "
                "Get Extensions > (dropdown) Install from Disk > pick the zip."
            )


if __name__ == "__main__":
    main()
