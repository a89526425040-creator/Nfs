#!/usr/bin/env python3
"""Bounds-checked parser for VIF command streams embedded in PS2 geometry leaves."""
from __future__ import annotations

import argparse
import csv
import json
import struct
from collections import Counter
from pathlib import Path

from ps2_chunk_scan import flatten, scan_bytes

TARGET_LEAF = "0x00134A02"
PADDING_BYTE = 0x11


def unpack_payload_bytes(command: int, count: int) -> tuple[int, int, int]:
    fmt = command & 0x0F
    if fmt in (3, 7, 11):
        raise ValueError(f"reserved VIF UNPACK format 0x{fmt:X}")
    if fmt == 15:
        bits_per_component = 5
    else:
        bits_per_component = 32 >> (fmt & 0x03)
    components = ((fmt >> 2) & 0x03) + 1
    bits_per_vector = components * bits_per_component
    bytes_per_vector = ((bits_per_vector + 31) // 32) * 4
    return bytes_per_vector * count, components, bits_per_component


def parse_vif_stream(payload: bytes) -> dict:
    pos = 0
    commands = []
    counts = Counter()
    unpack_formats = Counter()
    unpack_vectors = 0
    unpack_data_bytes = 0
    padding_bytes = 0

    while pos < len(payload):
        if payload[pos] == PADDING_BYTE:
            end = pos
            while end < len(payload) and payload[end] == PADDING_BYTE:
                end += 1
            padding_bytes += end - pos
            pos = end
            continue

        if len(payload) - pos < 4:
            tail = payload[pos:]
            if all(byte in (0, PADDING_BYTE) for byte in tail):
                padding_bytes += len(tail)
                pos = len(payload)
                break
            raise ValueError(f"non-padding tail of {len(tail)} bytes at 0x{pos:X}")

        word = struct.unpack_from("<I", payload, pos)[0]
        opcode = (word >> 24) & 0x7F
        num = (word >> 16) & 0xFF
        immediate = word & 0xFFFF
        effective_num = num or 256
        command_start = pos
        pos += 4
        data_bytes = 0
        label = f"0x{opcode:02X}"

        if 0x60 <= opcode <= 0x7F:
            data_bytes, components, bits_per_component = unpack_payload_bytes(
                opcode, effective_num
            )
            if data_bytes > len(payload) - pos:
                raise ValueError(
                    f"UNPACK 0x{opcode:02X} at 0x{command_start:X} "
                    f"needs {data_bytes} data bytes, only {len(payload) - pos} remain"
                )
            fmt = opcode & 0x0F
            label = f"UNPACK_{components}x{bits_per_component}"
            unpack_formats[f"0x{fmt:X}"] += 1
            unpack_vectors += effective_num
            unpack_data_bytes += data_bytes
        elif opcode == 0x20:  # STMASK
            data_bytes, label = 4, "STMASK"
        elif opcode in (0x30, 0x31):  # STROW / STCOL
            data_bytes = 16
            label = "STROW" if opcode == 0x30 else "STCOL"
        elif opcode == 0x4A:  # MPG: NUM 64-bit microinstructions
            data_bytes, label = effective_num * 8, "MPG"
        elif opcode in (0x50, 0x51):  # DIRECT / DIRECTHL: QWC in immediate
            data_bytes = (immediate or 65536) * 16
            label = "DIRECT" if opcode == 0x50 else "DIRECTHL"
        elif opcode in {
            0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
            0x10, 0x11, 0x13, 0x14, 0x15, 0x17,
        }:
            label = {
                0x00: "NOP", 0x01: "STCYCL", 0x02: "OFFSET",
                0x03: "BASE", 0x04: "ITOP", 0x05: "STMOD",
                0x06: "MSKPATH3", 0x07: "MARK", 0x10: "FLUSHE",
                0x11: "FLUSH", 0x13: "FLUSHA", 0x14: "MSCAL",
                0x15: "MSCALF", 0x17: "MSCNT",
            }[opcode]
        else:
            raise ValueError(
                f"unknown VIF opcode 0x{opcode:02X} at 0x{command_start:X} "
                f"(word 0x{word:08X})"
            )

        if data_bytes > len(payload) - pos:
            raise ValueError(
                f"{label} at 0x{command_start:X} needs {data_bytes} data bytes, "
                f"only {len(payload) - pos} remain"
            )
        pos += data_bytes
        counts[label] += 1
        commands.append({
            "offset": command_start,
            "word": f"0x{word:08X}",
            "opcode": f"0x{opcode:02X}",
            "label": label,
            "num": num,
            "immediate": f"0x{immediate:04X}",
            "data_bytes": data_bytes,
        })

    return {
        "stream_bytes": len(payload),
        "commands": commands,
        "command_count": len(commands),
        "command_counts": dict(sorted(counts.items())),
        "unpack_format_counts": dict(sorted(unpack_formats.items())),
        "unpack_vector_count": unpack_vectors,
        "unpack_data_bytes": unpack_data_bytes,
        "padding_bytes": padding_bytes,
        "consumed_bytes": pos,
    }


def probe_catalogue(catalogue: Path, archives: dict[int, Path],
                    vehicle_limit: int = 3, meshes_per_vehicle: int = 3):
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
            offset, size = int(entry["byte_offset"]), int(entry["size"])
            with archives[archive_id].open("rb") as archive:
                archive.seek(offset)
                data = archive.read(size)
            if len(data) != size:
                raise ValueError(f"short read for {path}")
            scan = scan_bytes(data)
            if scan["errors"]:
                raise ValueError(f"chunk scan failed for {path}: {scan['errors'][0]}")
            leaves = [
                node for node in flatten(scan["nodes"])
                if node["id"] == TARGET_LEAF
            ][:meshes_per_vehicle]
            leaf_rows = []
            for node in leaves:
                start = node["offset"] + 8
                raw = data[start:start + node["size"]]
                if len(raw) != node["size"]:
                    raise ValueError(f"leaf exceeds resource boundary: {path}")
                leading = 0
                while leading < len(raw) and raw[leading] == PADDING_BYTE:
                    leading += 1
                parsed = parse_vif_stream(raw[leading:])
                leaf_rows.append({
                    "chunk_offset": node["offset"],
                    "payload_size": node["size"],
                    "leading_padding_bytes": leading,
                    **parsed,
                })
            resources.append({
                "path": path,
                "geometry_leaf_count": sum(
                    node["id"] == TARGET_LEAF for node in flatten(scan["nodes"])
                ),
                "streams": leaf_rows,
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
    print(f"Parsed {sum(len(r['streams']) for r in resources)} VIF streams.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
