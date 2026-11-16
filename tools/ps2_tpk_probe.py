#!/usr/bin/env python3
"""Probe the nested B3300000 texture-pack layout in NFSU2 resources."""
from __future__ import annotations

import argparse
import csv
import json
import struct
from pathlib import Path

ROOT = 0xB3300000
INFO = 0xB3310000
DATA = 0xB3320000
HEADER = 0x33310001
INDEX = 0x33310002
STREAM = 0x33310003
VRAM_HEADER = 0x33320001
VRAM_DATA = 0x33320002


def chunks(data: bytes, start: int, end: int):
    """Yield bounded (id, size, header offset, payload offset, end) chunks."""
    pos = start
    while pos + 8 <= end:
        chunk_id, size = struct.unpack_from("<II", data, pos)
        payload = pos + 8
        chunk_end = payload + size
        if chunk_end > end:
            raise ValueError(
                f"chunk 0x{chunk_id:08X} at 0x{pos:X} ends at 0x{chunk_end:X}, "
                f"outside 0x{end:X}"
            )
        yield chunk_id, size, pos, payload, chunk_end
        if chunk_end <= pos:
            raise ValueError(f"non-advancing chunk at 0x{pos:X}")
        pos = chunk_end
    if pos != end and any(data[pos:end]):
        raise ValueError(f"non-zero trailing bytes at 0x{pos:X}..0x{end:X}")


def _cstring(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("ascii", "replace")


def parse_tpk(data: bytes) -> dict:
    if len(data) < 8:
        raise ValueError("file is shorter than a chunk header")
    root_id, root_size = struct.unpack_from("<II", data, 0)
    if root_id != ROOT:
        raise ValueError(f"expected B3300000 root, got 0x{root_id:08X}")
    root_end = 8 + root_size
    if root_end > len(data):
        raise ValueError(f"root ends at 0x{root_end:X}, file ends at 0x{len(data):X}")

    result = {
        "file_bytes": len(data),
        "root_size": root_size,
        "root_end": root_end,
        "top_level": [],
        "info_chunks": [],
        "data_chunks": [],
        "errors": [],
    }
    info_payload = None
    data_payload = None
    for cid, size, offset, payload, end in chunks(data, 8, root_end):
        result["top_level"].append({
            "id": f"0x{cid:08X}", "offset": offset, "size": size,
            "payload_offset": payload, "end": end,
        })
        if cid == INFO:
            info_payload = (payload, end)
        elif cid == DATA:
            data_payload = (payload, end)

    header = None
    index_entries = []
    stream_entries = []
    if info_payload:
        pstart, pend = info_payload
        for cid, size, offset, payload, end in chunks(data, pstart, pend):
            item = {"id": f"0x{cid:08X}", "offset": offset, "size": size}
            result["info_chunks"].append(item)
            raw = data[payload:end]
            if cid == HEADER:
                if size < 0x7C:
                    result["errors"].append("33310001 header shorter than 0x7C")
                else:
                    header = {
                        "version": struct.unpack_from("<I", raw, 0)[0],
                        "name": _cstring(raw[4:0x20]),
                        "filename": _cstring(raw[0x20:0x60]),
                        "filename_hash": f"0x{struct.unpack_from('<I', raw, 0x60)[0]:08X}",
                    }
            elif cid == INDEX:
                if size % 8:
                    result["errors"].append(f"33310002 size {size} is not divisible by 8")
                else:
                    for pos in range(0, size, 8):
                        name_hash, ptr = struct.unpack_from("<II", raw, pos)
                        index_entries.append({"name_hash": f"0x{name_hash:08X}", "ptr": ptr})
            elif cid == STREAM:
                if size % 0x18:
                    result["errors"].append(f"33310003 size {size} is not divisible by 0x18")
                else:
                    for pos in range(0, size, 0x18):
                        name_hash, blob_offset, compressed, uncompressed = struct.unpack_from("<IIii", raw, pos)
                        descriptor_word_4, descriptor_word_5 = struct.unpack_from("<II", raw, pos + 0x10)
                        stream_entries.append({
                            "name_hash": f"0x{name_hash:08X}",
                            "blob_offset": blob_offset,
                            "compressed_bytes": compressed,
                            "uncompressed_bytes": uncompressed,
                            "descriptor_word_4": descriptor_word_4,
                            "descriptor_word_5": descriptor_word_5,
                        })
    result["header"] = header
    result["index_count"] = len(index_entries)
    result["stream_count"] = len(stream_entries)
    result["index_entries"] = index_entries
    result["stream_entries"] = stream_entries
    result["vram_chunks"] = []
    if data_payload:
        pstart, pend = data_payload
        for cid, size, offset, payload, end in chunks(data, pstart, pend):
            result["vram_chunks"].append({
                "id": f"0x{cid:08X}", "offset": offset, "size": size,
                "payload_offset": payload, "end": end,
            })
            if cid == VRAM_DATA:
                result["vram_data_offset"] = payload
                result["vram_data_bytes"] = size
    if len(index_entries) != len(stream_entries):
        result["errors"].append(
            f"index/stream count mismatch: {len(index_entries)} vs {len(stream_entries)}"
        )
    for index, entry in enumerate(stream_entries):
        off = entry["blob_offset"]
        size = entry["compressed_bytes"]
        item = dict(entry)
        item["index_hash_matches"] = (
            index < len(index_entries)
            and index_entries[index]["name_hash"] == entry["name_hash"]
        )
        if off < 0 or size < 0 or off + size > root_end:
            item["blob_error"] = "blob range outside TPK root"
        else:
            blob = data[off:off + size]
            item["blob_magic"] = blob[:4].decode("ascii", "replace")
            if len(blob) >= 16 and blob[:4] in (b"JDLZ", b"HUFF", b"RAWW"):
                item["compression_header"] = {
                    "version": blob[4],
                    "header_size": blob[5],
                    "flags": struct.unpack_from("<H", blob, 6)[0],
                    "uncompressed_bytes": struct.unpack_from("<I", blob, 8)[0],
                    "compressed_bytes": struct.unpack_from("<I", blob, 12)[0],
                }
            else:
                item["blob_prefix_hex"] = blob[:24].hex().upper()
        result.setdefault("blob_checks", []).append(item)
    return result


def inspect_catalogue(catalogue: Path, archives: dict[int, Path], limit: int = 64) -> list[dict]:
    resources = []
    seen = set()
    with catalogue.open("r", newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            path = row.get("path", "")
            upper = path.upper()
            if row.get("resolution") != "resolved" or not upper.startswith("CARS\\") or not upper.endswith("\\TEXTURES.BIN"):
                continue
            if upper in seen:
                continue
            seen.add(upper)
            size = int(row["size"])
            if size == 0:
                resources.append({"path": path, "file_bytes": 0, "empty": True})
            else:
                archive_id = int(row["archive_id"])
                if archive_id not in archives:
                    raise ValueError(f"archive {archive_id} was not supplied")
                with archives[archive_id].open("rb") as archive:
                    archive.seek(int(row["byte_offset"]))
                    payload = archive.read(size)
                if len(payload) != size:
                    raise ValueError(f"short read for {path}: {len(payload)} / {size}")
                try:
                    report = parse_tpk(payload)
                except ValueError as exc:
                    report = {"file_bytes": len(payload), "errors": [str(exc)]}
                report["path"] = path
                resources.append(report)
            if len(resources) >= limit:
                break
    return resources


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalogue", type=Path)
    parser.add_argument("--archive", action="append", required=True, metavar="ID=PATH")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=64)
    args = parser.parse_args()
    archives = {}
    for spec in args.archive:
        key, sep, value = spec.partition("=")
        if not sep:
            parser.error(f"invalid archive mapping: {spec}")
        archives[int(key)] = Path(value)
    try:
        resources = inspect_catalogue(args.catalogue, archives, args.limit)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"resources": resources}, indent=2) + "\n", encoding="utf-8")
    print(f"Parsed {sum(1 for item in resources if item.get('header'))} TPK texture packs; inspected {len(resources)} resources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
