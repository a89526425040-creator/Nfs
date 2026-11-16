#!/usr/bin/env python3
"""Inspect PS2 car TEXTURES.BIN resources without exporting proprietary payloads."""
from __future__ import annotations

import argparse
import csv
import json
import struct
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
    args.output.write_text(json.dumps({"resources": resources}, indent=2) + "\\n", encoding="utf-8")
    print(f"Inspected {len(resources)} car texture archives.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
