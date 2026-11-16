#!/usr/bin/env python3
"""Bounds-checked diagnostic walker for EA-style PS2 resource chunks.

Only chunk metadata is emitted; payload bytes are never exported.
"""
from __future__ import annotations

import argparse
import csv
import json
import struct
from collections import Counter
from pathlib import Path

HEADER = struct.Struct("<II")


def _walk(data: bytes, begin: int, end: int, depth: int, max_depth: int, errors: list, padding: list):
    nodes = []
    pos = begin
    while pos < end:
        remaining = end - pos
        if remaining < HEADER.size:
            tail = data[pos:end]
            if all(byte in (0, 0x11) for byte in tail):
                padding.append({"offset": pos, "size": len(tail), "depth": depth})
            else:
                errors.append(f"trailing {remaining} bytes at 0x{pos:X} in depth {depth}")
            break

        chunk_id, size = HEADER.unpack_from(data, pos)
        if chunk_id == 0:
            if size > remaining - HEADER.size:
                tail = data[pos:end]
                if all(byte == 0 for byte in tail):
                    padding.append({"offset": pos, "size": len(tail), "depth": depth})
                    break
                errors.append(f"padding size {size} exceeds parent at 0x{pos:X}")
                break
            total = HEADER.size + size
            padding.append({"offset": pos, "size": total, "depth": depth})
            pos += total
            continue

        if chunk_id == 0x11111111:
            run_end = pos
            while run_end < end and data[run_end] == 0x11:
                run_end += 1
            padding.append({"offset": pos, "size": run_end - pos, "depth": depth})
            pos = run_end
            continue

        body = pos + HEADER.size
        body_end = body + size
        if body_end < body or body_end > end:
            errors.append(
                f"chunk 0x{chunk_id:08X} at 0x{pos:X} declares {size} bytes "
                f"past parent end 0x{end:X}"
            )
            break

        is_container = (chunk_id >> 28) == 0x8
        node = {
            "offset": pos,
            "id": f"0x{chunk_id:08X}",
            "size": size,
            "depth": depth,
            "kind": "container" if is_container else "leaf",
            "children": [],
        }
        if is_container:
            if depth >= max_depth:
                errors.append(f"maximum nesting depth {max_depth} reached at 0x{pos:X}")
            else:
                node["children"] = _walk(
                    data, body, body_end, depth + 1, max_depth, errors, padding
                )
        nodes.append(node)
        pos = body_end
    return nodes


def scan_bytes(data: bytes, max_depth: int = 24):
    if max_depth < 1:
        raise ValueError("max_depth must be positive")
    errors, padding = [], []
    nodes = _walk(data, 0, len(data), 0, max_depth, errors, padding)
    return {
        "file_size": len(data),
        "nodes": nodes,
        "padding": padding,
        "errors": errors,
    }


def flatten(nodes):
    for node in nodes:
        yield node
        yield from flatten(node["children"])


def scan_catalogue(catalogue: Path, archives: dict[int, Path], limit: int = 8):
    if limit < 1:
        raise ValueError("limit must be positive")
    selected, seen = [], set()
    with catalogue.open("r", newline="", encoding="utf-8-sig") as stream:
        for entry in csv.DictReader(stream):
            path = entry["path"]
            if (
                entry.get("resolution") != "resolved"
                or not path
                or path.upper() in seen
                or not path.upper().startswith("CARS\\")
                or not path.upper().endswith("\\GEOMETRY.BIN")
            ):
                continue
            seen.add(path.upper())
            archive_id = int(entry["archive_id"])
            if archive_id not in archives:
                raise ValueError(f"archive {archive_id} was not supplied")
            offset, size = int(entry["byte_offset"]), int(entry["size"])
            with archives[archive_id].open("rb") as archive:
                archive.seek(offset)
                payload = archive.read(size)
            if len(payload) != size:
                raise ValueError(f"short read for {path}")
            result = scan_bytes(payload)
            flat = list(flatten(result["nodes"]))
            counts = Counter(node["id"] for node in flat)
            selected.append({
                "path": path,
                "archive_id": archive_id,
                "archive_offset": offset,
                "scan": {
                    "file_size": result["file_size"],
                    "chunk_count": len(flat),
                    "container_count": sum(n["kind"] == "container" for n in flat),
                    "leaf_count": sum(n["kind"] == "leaf" for n in flat),
                    "padding_regions": len(result["padding"]),
                    "padding_bytes": sum(p["size"] for p in result["padding"]),
                    "errors": result["errors"],
                    "id_counts": dict(sorted(counts.items())),
                    "tree": result["nodes"],
                },
            })
            if len(selected) >= limit:
                break
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalogue", type=Path)
    parser.add_argument("--archive", action="append", required=True, metavar="ID=PATH")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    archives = {}
    for spec in args.archive:
        key, sep, value = spec.partition("=")
        if not sep:
            parser.error(f"invalid archive mapping: {spec}")
        archives[int(key)] = Path(value)
    try:
        resources = scan_catalogue(args.catalogue, archives, args.limit)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"resources": resources}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Scanned {len(resources)} complete vehicle geometry resources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
