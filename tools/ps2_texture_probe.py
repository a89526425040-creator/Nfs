#!/usr/bin/env python3
"""Inspect PS2 car TEXTURES.BIN resources without exporting proprietary payloads."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from ps2_chunk_scan import flatten, scan_bytes

MAGICS = {
    b"TIM2": "TIM2",
    b"DDS ": "DDS",
    b"\x89PNG\r\n\x1a\n": "PNG",
    b"\xff\xd8\xff": "JPEG",
    b"BM": "BMP",
}



def _bmp_info(data: bytes, offset: int) -> dict | None:
    if offset + 26 > len(data):
        return None
    declared_size = int.from_bytes(data[offset + 2:offset + 6], "little")
    pixel_offset = int.from_bytes(data[offset + 10:offset + 14], "little")
    dib_size = int.from_bytes(data[offset + 14:offset + 18], "little")
    if dib_size < 12 or offset + 14 + dib_size > len(data):
        return None
    if dib_size >= 40:
        width = int.from_bytes(data[offset + 18:offset + 22], "little", signed=True)
        height = int.from_bytes(data[offset + 22:offset + 26], "little", signed=True)
        planes = int.from_bytes(data[offset + 26:offset + 28], "little")
        bpp = int.from_bytes(data[offset + 28:offset + 30], "little")
        compression = int.from_bytes(data[offset + 30:offset + 34], "little")
        image_size = int.from_bytes(data[offset + 34:offset + 38], "little")
    elif dib_size == 12:
        width = int.from_bytes(data[offset + 18:offset + 20], "little")
        height = int.from_bytes(data[offset + 20:offset + 22], "little")
        planes = int.from_bytes(data[offset + 22:offset + 24], "little")
        bpp = int.from_bytes(data[offset + 24:offset + 26], "little")
        compression, image_size = 0, 0
    else:
        return None
    end = offset + declared_size if declared_size else len(data)
    if (width <= 0 or width > 16384 or height == 0 or abs(height) > 16384
            or planes != 1 or bpp not in (1, 4, 8, 16, 24, 32)):
        return None
    if pixel_offset < 14 + dib_size or offset + pixel_offset > len(data) or end > len(data) or end < offset + pixel_offset:
        return None
    return {"format":"BMP","offset":offset,"file_bytes":declared_size,"width":width,
            "height":height,"bits_per_pixel":bpp,"compression":compression,
            "pixel_offset":pixel_offset,"image_bytes":image_size}


def _jpeg_info(data: bytes, offset: int) -> dict | None:
    if data[offset:offset + 3] != b"\xff\xd8\xff":
        return None
    sof = {0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF}
    pos = offset + 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            pos += 1
            continue
        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos >= len(data):
            return None
        marker = data[pos]
        pos += 1
        if marker in (0xD8,0xD9,0x01) or 0xD0 <= marker <= 0xD7:
            continue
        if pos + 2 > len(data):
            return None
        size = int.from_bytes(data[pos:pos + 2], "big")
        if size < 2 or pos + size > len(data):
            return None
        if marker in sof and size >= 8:
            precision = data[pos + 2]
            height = int.from_bytes(data[pos + 3:pos + 5], "big")
            width = int.from_bytes(data[pos + 5:pos + 7], "big")
            components = data[pos + 7]
            if (precision not in (8, 12, 16) or not (1 <= width <= 16384)
                    or not (1 <= height <= 16384) or components not in (1, 3, 4)
                    or size != 8 + 3 * components):
                return None
            return {"format":"JPEG","offset":offset,"width":width,"height":height,
                    "precision":precision,"components":components}
            return None
        pos += size
    return None


def inspect_image_headers(payload: bytes) -> list[dict]:
    images = []
    for magic, label in MAGICS.items():
        if label not in ("BMP","JPEG"):
            continue
        cursor = 0
        while True:
            found = payload.find(magic, cursor)
            if found < 0:
                break
            cursor = found + 1
            info = _bmp_info(payload, found) if label == "BMP" else _jpeg_info(payload, found)
            if info is not None:
                images.append(info)
            if len(images) >= 512:
                return sorted(images, key=lambda item:item["offset"])
    return sorted(images, key=lambda item:item["offset"])


def inspect_texture_resources(catalogue: Path, archives: dict[int, Path], limit: int = 32):
    selected = []
    seen = set()
    with catalogue.open("r", newline="", encoding="utf-8-sig") as stream:
        for entry in csv.DictReader(stream):
            path = entry.get("path", "")
            upper = path.upper()
            if entry.get("resolution") != "resolved" or not upper.startswith("CARS\\") or not upper.endswith("\\TEXTURES.BIN"):
                continue
            if upper in seen:
                continue
            seen.add(upper)
            archive_id = int(entry["archive_id"])
            offset, size = int(entry["byte_offset"]), int(entry["size"])
            if archive_id not in archives:
                raise ValueError(f"archive {archive_id} was not supplied")
            with archives[archive_id].open("rb") as archive:
                archive.seek(offset)
                payload = archive.read(size)
            if len(payload) != size:
                raise ValueError(f"short read for {path}")
            scan = scan_bytes(payload)
            flat = list(flatten(scan["nodes"]))
            signatures = []
            for magic, label in MAGICS.items():
                cursor = 0
                while True:
                    found = payload.find(magic, cursor)
                    if found < 0:
                        break
                    signatures.append({"format": label, "offset": found})
                    cursor = found + 1
                    if len(signatures) >= 128:
                        break
            images = inspect_image_headers(payload)
            selected.append({
                "path": path,
                "archive_id": archive_id,
                "archive_offset": offset,
                "file_size": size,
                "prefix_hex": payload[:64].hex().upper(),
                "chunk_count": len(flat),
                "container_count": sum(n["kind"] == "container" for n in flat),
                "leaf_count": sum(n["kind"] == "leaf" for n in flat),
                "chunk_ids": dict(sorted(Counter(n["id"] for n in flat).items())),
                "chunk_errors": scan["errors"],
                "signatures": signatures,
                "validated_images": images,
                "top_level": [
                    {"id": n["id"], "offset": n["offset"], "size": n["size"], "kind": n["kind"]}
                    for n in scan["nodes"]
                ],
            })
            if len(selected) >= limit:
                break
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalogue", type=Path)
    parser.add_argument("--archive", action="append", required=True, metavar="ID=PATH")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=32)
    args = parser.parse_args()
    archives = {}
    for spec in args.archive:
        key, sep, value = spec.partition("=")
        if not sep:
            parser.error(f"invalid archive mapping: {spec}")
        archives[int(key)] = Path(value)
    try:
        resources = inspect_texture_resources(args.catalogue, archives, args.limit)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"resources": resources}, indent=2) + "\n", encoding="utf-8")
    print(f"Inspected {len(resources)} car texture archives.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
