#!/usr/bin/env python3
"""Split atlas PNG sub-images into individual ≤256x256 PNGs.

OpenRCT2's ImageImporter rejects any PNG >256x256. makevehicle emits one
large atlas per car with sub-image refs via src_x/src_y/src_width/src_height,
which the engine refuses to load.

This rewrites a .parkobj in place: for every image entry that addresses a
sub-rect of an atlas PNG, it crops the sub-image, writes it as its own
PNG inside the archive, and rewrites the entry to point at the new file
with no src_* fields.
"""

import argparse
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path

from PIL import Image


def split(parkobj_path: Path) -> None:
    with zipfile.ZipFile(parkobj_path, "r") as zin:
        names = zin.namelist()
        object_json = json.loads(zin.read("object.json"))
        blobs = {n: zin.read(n) for n in names}

    images = object_json.get("images")
    if not isinstance(images, list):
        sys.exit("object.json has no images array")

    atlases: dict[str, Image.Image] = {}
    for path, data in blobs.items():
        if not path.endswith(".png"):
            continue
        img = Image.open(io.BytesIO(data))
        img.load()
        if img.size[0] > 256 or img.size[1] > 256:
            atlases[path] = img

    if not atlases:
        print("no oversized atlases; nothing to do")
        return

    print(f"oversized atlas PNGs: {len(atlases)}")
    for p, im in atlases.items():
        print(f"  {p}: {im.size[0]}x{im.size[1]}")

    new_pngs: dict[str, bytes] = {}
    new_images: list[dict] = []
    counter = 0
    for entry in images:
        path = entry.get("path", "")
        if path not in atlases:
            new_images.append(entry)
            continue
        sx = entry.get("src_x", 0)
        sy = entry.get("src_y", 0)
        sw = entry.get("src_width")
        sh = entry.get("src_height")
        if sw is None or sh is None:
            sys.exit(f"entry references atlas without src_width/src_height: {entry}")
        sub = atlases[path].crop((sx, sy, sx + sw, sy + sh))
        if atlases[path].palette is not None:
            sub.putpalette(atlases[path].getpalette())
        # tRNS chunk: preserve index-0 as transparent (matches atlas convention)
        if "transparency" in atlases[path].info:
            sub.info["transparency"] = atlases[path].info["transparency"]
        buf = io.BytesIO()
        sub.save(buf, format="PNG", transparency=sub.info.get("transparency"))
        # Stem the atlas filename, e.g., images/car_0.png -> images/car_0/00001.png
        stem = path[: -len(".png")]
        new_path = f"{stem}/{counter:05d}.png"
        counter += 1
        new_pngs[new_path] = buf.getvalue()

        new_entry = {
            "path": new_path,
            "x": entry.get("x", 0),
            "y": entry.get("y", 0),
            "palette": entry.get("palette", "keep"),
        }
        new_images.append(new_entry)

    object_json["images"] = new_images
    print(f"split into {len(new_pngs)} individual sprite PNGs")

    backup = parkobj_path.with_suffix(parkobj_path.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(parkobj_path, backup)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in blobs.items():
            if name in atlases:
                continue
            if name == "object.json":
                continue
            zout.writestr(name, data)
        zout.writestr(
            "object.json",
            json.dumps(object_json, indent=4).encode("utf-8"),
        )
        for name, data in new_pngs.items():
            zout.writestr(name, data)

    parkobj_path.write_bytes(buf.getvalue())
    print(f"rewrote {parkobj_path} ({parkobj_path.stat().st_size/1024/1024:.2f} MB)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("parkobj", type=Path, help=".parkobj to update in place")
    args = ap.parse_args()
    if not args.parkobj.is_file():
        sys.exit(f"not a file: {args.parkobj}")
    split(args.parkobj)


if __name__ == "__main__":
    main()
