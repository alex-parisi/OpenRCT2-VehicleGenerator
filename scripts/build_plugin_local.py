#!/usr/bin/env python3
"""Build the Blender extension fresh for THIS machine and its Blender.

The CI release (.github/workflows/build-plugin.yml) cross-builds renderer wheels
for every platform x CPython 3.11/3.13 and bundles them into one zip. That can't
be reproduced locally -- you can only compile a wheel for the interpreter and OS
you're running on. This script instead produces a single-platform zip you can
install into your local Blender right now:

  1. Compile the renderer wheel from x7_renderer/ against your Homebrew Embree.
  2. Vendor Embree (+its TBB) into the wheel with delocate, so it's
     self-contained and needs no system Embree at runtime.
  3. Download numpy/pillow/pyyaml wheels matching your Blender's CPython.
  4. Stage the add-on with a local-only manifest (just this platform + these 4
     wheels) and run `blender --command extension build`.

The committed blender_addon/wheels/ and blender_manifest.toml are never touched;
everything is staged in a temp dir.

macOS only (vendoring uses delocate). For a Linux/Windows release, use CI.

Usage:
    uv run python scripts/build_plugin_local.py [--install] [--no-verify] [-o dist]
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ADDON = REPO / "blender_addon"
MANIFEST = ADDON / "blender_manifest.toml"

RENDERER = "openrct2_vehiclegenerator"
DEPS = ("numpy", "pillow", "pyyaml")


def run(cmd: list[str], *, env: dict | None = None, capture: bool = False) -> str:
    """Run a command, echoing it; raise on failure. Return stdout if captured."""
    print("+", " ".join(cmd))
    res = subprocess.run(
        cmd,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return res.stdout if capture else ""


def brew_prefix(formula: str | None = None) -> str:
    cmd = ["brew", "--prefix"] + ([formula] if formula else [])
    try:
        return subprocess.run(cmd, check=True, text=True, capture_output=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise SystemExit(
            f"Could not find {'Homebrew' if not formula else formula} via `brew`. "
            "Install Embree first: brew install embree"
        ) from None


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
            "This script builds for macOS only (vendoring uses delocate).\n"
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
    """Pin deps to the versions in the build env, so they match what we compiled against."""
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


def one_renderer_wheel(d: Path) -> Path:
    wheels = list(d.glob(f"{RENDERER}-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"Expected one renderer wheel in {d}, found {wheels}")
    return wheels[0]


def build_renderer_wheel(out_dir: Path) -> Path:
    """Compile the renderer wheel against Homebrew Embree; return its path."""
    env = os.environ.copy()
    # find_package(embree) + its TBB dependency resolve from the Homebrew prefix.
    env["CMAKE_PREFIX_PATH"] = os.pathsep.join(
        p for p in [brew_prefix(), env.get("CMAKE_PREFIX_PATH", "")] if p
    )
    env["MACOSX_DEPLOYMENT_TARGET"] = "11.0"
    run(["uv", "build", "--wheel", "--out-dir", str(out_dir)], env=env)
    return one_renderer_wheel(out_dir)


def vendor_embree(out_dir: Path) -> Path:
    """Copy Embree + TBB into the renderer wheel so it loads without Homebrew.

    delocate retags the wheel to the macOS minimum of the libs it vendors (the
    Homebrew build's, i.e. this host's) and renames the file, so re-glob for the
    result rather than trusting the pre-delocate name.
    """
    wheel = one_renderer_wheel(out_dir)
    env = os.environ.copy()
    env["DYLD_FALLBACK_LIBRARY_PATH"] = os.pathsep.join(
        [
            f"{brew_prefix('embree')}/lib",
            f"{brew_prefix('tbb')}/lib",
            env.get("DYLD_FALLBACK_LIBRARY_PATH", ""),
        ]
    )
    run(["uv", "run", "--with", "delocate", "delocate-wheel", "-v", str(wheel)], env=env)
    return one_renderer_wheel(out_dir)


def download_deps(out_dir: Path, py_version: str, abi: str, pip_platforms: list[str]) -> None:
    cmd = [
        "uv",
        "run",
        "--with",
        "pip",
        "python",
        "-m",
        "pip",
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
        str(out_dir),
    ]
    for tag in pip_platforms:
        cmd += ["--platform", tag]
    cmd += dep_specs()
    run(cmd)


def stage_addon(stage: Path, wheels_src: Path, manifest_platform: str) -> None:
    """Copy add-on source into `stage` with a local-only manifest + wheels."""
    for item in ADDON.iterdir():
        if item.suffix in {".py", ".toml", ".json"} and item.is_file():
            shutil.copy2(item, stage / item.name)
    stage_wheels = stage / "wheels"
    stage_wheels.mkdir()
    for whl in wheels_src.glob("*.whl"):
        shutil.copy2(whl, stage_wheels / whl.name)

    names = sorted(p.name for p in stage_wheels.glob("*.whl"))
    wheels_block = "\n".join(["wheels = ["] + [f'    "./wheels/{n}",' for n in names] + ["]"])
    text = (stage / "blender_manifest.toml").read_text(encoding="utf-8")
    text, n1 = re.subn(
        r"platforms = \[.*?\]",
        f'platforms = ["{manifest_platform}"]',
        text,
        count=1,
        flags=re.DOTALL,
    )
    text, n2 = re.subn(r"wheels = \[.*?\]", wheels_block, text, count=1, flags=re.DOTALL)
    if n1 != 1 or n2 != 1:
        raise SystemExit("Could not rewrite 'platforms'/'wheels' in the manifest.")
    (stage / "blender_manifest.toml").write_text(text, encoding="utf-8")


def verify_wheel(wheel: Path) -> None:
    """Import the vendored wheel in a clean env -- catches an unvendored Embree."""
    run(
        [
            "uv",
            "run",
            "--with",
            str(wheel),
            "python",
            "-c",
            "import openrct2_vehicle_generator._x7_renderer as n;print('embree ok:', n.LIGHT_DIFFUSE)",
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
    args = ap.parse_args()

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

        build_renderer_wheel(wheels)
        renderer = vendor_embree(wheels)
        if not args.no_verify:
            verify_wheel(renderer)
        download_deps(wheels, py_version, abi, pip_platforms)
        stage_addon(stage, wheels, manifest_platform)

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
