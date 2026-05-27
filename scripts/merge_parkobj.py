#!/usr/bin/env python3
"""Merge maketrack output (sprites_out.json + PNGs) into a makevehicle .parkobj.

Pipeline:
    1. cmake build (makevehicle, maketrack)
    2. cd <workdir>   # where object/ will be written
    3. ./makevehicle examples/single_rail/single_rail.json
       -> openrct2.ride.single_rail_coaster.parkobj
       -> object/object.json, object/images/preview.png, object/images/car_*.png
    4. ./maketrack examples/single_rail/track.json
       -> object/images/<track-sprite>.png ... (lots)
       -> examples/single_rail/sprites_out.json
    5. python3 merge_parkobj.py \
           openrct2.ride.single_rail_coaster.parkobj \
           examples/single_rail/sprites_out.json
"""

import argparse
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path


def merge(parkobj_path: Path, sprites_out_path: Path, workdir: Path) -> None:
    with sprites_out_path.open() as f:
        track_entries = json.load(f)
    if not isinstance(track_entries, list):
        sys.exit(f"{sprites_out_path}: expected a JSON array at the top level")

    with zipfile.ZipFile(parkobj_path, "r") as zin:
        names = set(zin.namelist())
        if "object.json" not in names:
            sys.exit(f"{parkobj_path}: object.json missing from archive")
        object_json = json.loads(zin.read("object.json"))
        existing_blobs = {n: zin.read(n) for n in names}

    images = object_json.setdefault("images", [])
    existing_paths = {e.get("path") for e in images if isinstance(e, dict)}

    # sprites_out paths look like "object/images/flat_single_rail_1.png".
    # Inside the .parkobj, paths are relative to the archive root, so the
    # leading "object/" prefix is stripped.
    new_image_entries = []
    pngs_to_add: dict[str, Path] = {}  # archive path -> source path on disk
    skipped = 0
    for entry in track_entries:
        if not isinstance(entry, dict) or "path" not in entry:
            sys.exit(f"{sprites_out_path}: malformed entry {entry!r}")
        disk_path = workdir / entry["path"]
        src_path = entry["path"]
        if src_path.startswith("object/"):
            archive_path = src_path[len("object/"):]
        else:
            archive_path = src_path
        if not disk_path.is_file():
            sys.exit(f"missing sprite PNG: {disk_path}")

        rewritten = dict(entry)
        rewritten["path"] = archive_path
        if archive_path in existing_paths:
            skipped += 1
            continue
        new_image_entries.append(rewritten)
        existing_paths.add(archive_path)
        pngs_to_add[archive_path] = disk_path

    images.extend(new_image_entries)

    backup = parkobj_path.with_suffix(parkobj_path.suffix + ".bak")
    shutil.copy2(parkobj_path, backup)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in existing_blobs.items():
            if name == "object.json":
                continue
            if name in pngs_to_add:
                # New PNG overrides the prior copy (shouldn't normally happen).
                continue
            zout.writestr(name, data)
        zout.writestr(
            "object.json",
            json.dumps(object_json, indent=4).encode("utf-8"),
        )
        for archive_path, disk_path in pngs_to_add.items():
            zout.write(disk_path, archive_path)

    parkobj_path.write_bytes(buf.getvalue())

    print(f"merged {len(new_image_entries)} track sprites into {parkobj_path}")
    if skipped:
        print(f"  ({skipped} entries already present, skipped)")
    print(f"  backup: {backup}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("parkobj", type=Path, help="path to the .parkobj to update")
    ap.add_argument("sprites_out", type=Path, help="sprites_out.json from maketrack")
    ap.add_argument(
        "--workdir",
        type=Path,
        default=Path.cwd(),
        help="directory containing the object/images/ tree (default: CWD)",
    )
    args = ap.parse_args()

    if not args.parkobj.is_file():
        sys.exit(f"not a file: {args.parkobj}")
    if not args.sprites_out.is_file():
        sys.exit(f"not a file: {args.sprites_out}")

    merge(args.parkobj, args.sprites_out, args.workdir)


if __name__ == "__main__":
    main()
