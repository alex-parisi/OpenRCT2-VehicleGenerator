#!/usr/bin/env python3
"""Bundle the Blender add-on's dependency wheels and regenerate the manifest.

Blender extensions run in an isolated Python env and install ONLY the wheels
listed in ``blender_manifest.toml`` -- pip is never consulted at install time.
So every native runtime dependency (numpy, Pillow, PyYAML) must be vendored as a
wheel for each platform x Python combination Blender ships, or the add-on fails
to import (e.g. "No module named 'PIL'").

This script:
  1. Downloads those dependency wheels for all targets into blender_addon/wheels/.
  2. Rewrites the manifest's ``wheels = [...]`` list to reference the full set:
     the dependency wheels it just fetched plus the renderer wheels CI produces.

The renderer wheels themselves are NOT downloaded here -- they link Embree and
are compiled per-platform by .github/workflows/wheels.yml. Unzip those 6 files
from the CI artifacts into blender_addon/wheels/ before running
``blender --command extension build``; this script lists their expected names so
the manifest is complete, and reports which are still missing.

Run from the repo root (pip must be importable, so add it if your venv lacks it):

    uv run --with pip python scripts/collect_wheels.py
"""

from __future__ import annotations

import importlib.metadata as md
import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ADDON = REPO / "blender_addon"
WHEELS = ADDON / "wheels"
MANIFEST = ADDON / "blender_manifest.toml"

RENDERER = "openrct2_vehiclegenerator"
DEPS = ("numpy", "pillow", "pyyaml")

# (python version, abi tag) for each interpreter Blender ships: 3.11 (4.2/4.5
# LTS), 3.13 (5.x).
PYTHONS = (("3.11", "cp311"), ("3.13", "cp313"))

# (renderer wheel platform tag, dep-download --platform tags). Several dep tags
# per OS let pip pick each package's compatible wheel -- e.g. numpy publishes a
# higher macOS minimum than Pillow.
TARGETS = (
    ("win_amd64", ["win_amd64"]),
    (
        "macosx_11_0_arm64",
        ["macosx_11_0_arm64", "macosx_12_0_arm64", "macosx_13_0_arm64", "macosx_14_0_arm64"],
    ),
    (
        "manylinux_2_28_x86_64",
        ["manylinux_2_28_x86_64", "manylinux_2_17_x86_64", "manylinux2014_x86_64"],
    ),
)


def ensure_pip() -> None:
    try:
        subprocess.run([sys.executable, "-m", "pip", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise SystemExit(
            "pip is not available in this interpreter. Re-run with:\n"
            "  uv run --with pip python scripts/collect_wheels.py"
        ) from None


def project_version() -> str:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def dep_specs() -> list[str]:
    # Pin to the versions resolved in this env so the bundled deps match what the
    # renderer was built and tested against.
    return [f"{name}=={md.version(name)}" for name in DEPS]


def is_dep_wheel(name: str) -> bool:
    low = name.lower()
    return any(low.startswith(f"{d}-") for d in DEPS)


def clear_dep_wheels() -> None:
    for whl in WHEELS.glob("*.whl"):
        if is_dep_wheel(whl.name):
            whl.unlink()


def download_deps() -> None:
    specs = dep_specs()
    for py, abi in PYTHONS:
        for _renderer_tag, plat_tags in TARGETS:
            cmd = [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--only-binary=:all:",
                "--no-deps",
                "--python-version",
                py,
                "--implementation",
                "cp",
                "--abi",
                abi,
                "-d",
                str(WHEELS),
            ]
            for tag in plat_tags:
                cmd += ["--platform", tag]
            cmd += specs
            print("+", " ".join(cmd))
            subprocess.run(cmd, check=True)


def renderer_wheel_names(version: str) -> list[str]:
    return [
        f"{RENDERER}-{version}-{abi}-{abi}-{renderer_tag}.whl"
        for _py, abi in PYTHONS
        for renderer_tag, _plat_tags in TARGETS
    ]


def dep_wheel_names() -> list[str]:
    return [whl.name for whl in WHEELS.glob("*.whl") if is_dep_wheel(whl.name)]


def write_manifest(wheel_names: list[str]) -> None:
    entries = sorted(set(wheel_names))
    block = "\n".join(["wheels = ["] + [f'    "./wheels/{name}",' for name in entries] + ["]"])
    text = MANIFEST.read_text(encoding="utf-8")
    new_text, n = re.subn(r"wheels = \[.*?\]", block, text, count=1, flags=re.DOTALL)
    if n != 1:
        raise SystemExit("Could not find a 'wheels = [...]' block in the manifest")
    MANIFEST.write_text(new_text, encoding="utf-8")


def main() -> None:
    ensure_pip()
    WHEELS.mkdir(parents=True, exist_ok=True)
    clear_dep_wheels()
    download_deps()

    version = project_version()
    renderer = renderer_wheel_names(version)
    deps = dep_wheel_names()
    write_manifest(renderer + deps)
    print(
        f"\nManifest updated: {len(set(renderer + deps))} wheels "
        f"({len(renderer)} renderer + {len(deps)} deps)."
    )

    missing = [n for n in renderer if not (WHEELS / n).exists()]
    if missing:
        print(
            "\nRenderer wheels still missing -- unzip CI artifacts into "
            f"{WHEELS.relative_to(REPO)}/ before `extension build`:"
        )
        for m in missing:
            print(f"  - {m}")


if __name__ == "__main__":
    main()
