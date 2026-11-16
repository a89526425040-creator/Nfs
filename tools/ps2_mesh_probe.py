#!/usr/bin/env python3
"""Inspect numeric prefixes of PS2 vehicle geometry leaves without exporting payloads."""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from pathlib import Path

from ps2_chunk_scan import flatten, scan_bytes

GEOMETRY_ID = "0x80134100"
LEAF_IDS = {"0x00134A00", "0x00134A01", "0x00134A02"}
CANDIDATE_STRIDES = (16, 20, 24, 28, 32, 36, 40, 44, 48)
CANDIDATE_SKIPS = (0, 4, 8, 12, 16, 20, 24, 32, 64, 128)


def probe_leaf(data: bytes, node: dict):
    payload_start = node["offset"] + 8
    payload = data[payload_start:payload_start + node["size"]]
    if len(payload) != node["size"]:
        raise ValueError("leaf payload exceeds resource boundary")
    fill_11 = 0
    while fill_11 < len(payload) and payload[fill_11] == 0x11:
        fill_11 += 1
    fill_00 = 0
    while fill_00 < len(payload) and payload[fill_00] == 0:
        fill_00 += 1

    numeric_start = fill_11
    u16_values = [
        struct.unpack_from("<H", payload, pos)[0]
        for pos in range(numeric_start, min(len(payload) - 1, numeric_start + 32), 2)
    ]
    u32_values = [
        f"0x{struct.unpack_from('<I', payload, pos)[0]:08X}"
        for pos in range(numeric_start, min(len(payload) - 3, numeric_start + 32), 4)
    ]
    float_values = []
    for pos in range(numeric_start, min(len(payload) - 3, numeric_start + 64), 4):
        value = struct.unpack_from("<f", payload, pos)[0]
        if math.isfinite(value) and abs(value) < 1_000_000:
            float_values.append({"offset": pos, "value": round(value, 6)})
    divisible = []
    for skip in CANDIDATE_SKIPS:
        if skip <= len(payload):
            for stride in CANDIDATE_STRIDES:
                remaining = len(payload) - skip
                if remaining > 0 and remaining % stride == 0:
                    divisible.append({
                        "skip": skip,
                        "stride": stride,
                        "records": remaining // stride,
                    })
    return {
        "id": node["id"],
        "chunk_offset": node["offset"],
        "payload_size": len(payload),
        "leading_0x11_bytes": fill_11,
        "leading_zero_bytes": fill_00,
        "first_u16": u16_values[:16],
        "first_u32_hex": u32_values[:8],
        "first_f32_candidates": float_values[:8],
        "size_divisibility_candidates": divisible[:20],
    }


def probe_catalogue(catalogue: Path, archives: dict[int, Path],
                    vehicle_limit: int = 3, meshes_per_vehicle: int = 3):
    if vehicle_limit < 1 or meshes_per_vehicle < 1:
        raise ValueError("vehicle_limit and meshes_per_vehicle must be positive")
    resources = []
    seen = set()
    with catalogue.open("r", newline="", encoding="utf-8-sig") as stream:
        for entry in csv.DictReader(stream):
            path = entry["path"]
            if (
                entry.get("resolution") != "resolved"
                or not path
                or path.upper() in seen
                or not path.upper().startswith("CARS\\")
                or not path.upper().endswith("\\GEOMETRY.BIN")
                or int(entry["size"]) < 1_000_000
            ):
                continue
            seen.add(path.upper())
            archive_id = int(entry["archive_id"])
            if archive_id not in archives:
                raise ValueError(f"archive {archive_id} was not supplied")
            offset, size = int(entry["byte_offset"]), int(entry["size"])
            with archives[archive_id].open("rb") as archive:
                archive.seek(offset)
                data = archive.read(size)
            if len(data) != size:
                raise ValueError(f"short read for {path}")
            scan = scan_bytes(data)
            if scan["errors"]:
                raise ValueError(f"chunk scan failed for {path}: {scan['errors'][0]}")
            meshes = [
                node for node in flatten(scan["nodes"])
                if node["id"] == GEOMETRY_ID
            ][:meshes_per_vehicle]
            mesh_rows = []
            for mesh_index, mesh in enumerate(meshes):
                leaves = [
                    probe_leaf(data, child)
                    for child in mesh["children"]
                    if child["id"] in LEAF_IDS
                ]
                mesh_rows.append({
                    "mesh_index": mesh_index,
                    "container_offset": mesh["offset"],
                    "container_size": mesh["size"],
                    "leaves": leaves,
                })
            resources.append({
                "path": path,
                "file_size": size,
                "archive_id": archive_id,
                "archive_offset": offset,
                "geometry_container_count": sum(
                    node["id"] == GEOMETRY_ID for node in flatten(scan["nodes"])
                ),
                "meshes": mesh_rows,
            })
            if len(resources) >= vehicle_limit:
                break
    return resources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalogue", type=Path)
    parser.add_argument("--archive", action="append", required=True, metavar="ID=PATH")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vehicles", type=int, default=3)
    parser.add_argument("--meshes", type=int, default=3)
    args = parser.parse_args()
    archives = {}
    for spec in args.archive:
        key, sep, value = spec.partition("=")
        if not sep:
            parser.error(f"invalid archive mapping: {spec}")
        archives[int(key)] = Path(value)
    try:
        resources = probe_catalogue(
            args.catalogue, archives, args.vehicles, args.meshes
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"resources": resources}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Probed {sum(len(r['meshes']) for r in resources)} geometry containers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
