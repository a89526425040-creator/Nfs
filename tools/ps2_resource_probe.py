#!/usr/bin/env python3
"""Summarize aligned words and printable strings in PS2 resource prefixes.

The tool reads a bounded prefix from each selected resource and emits metadata
only. It does not write or export raw game payload bytes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
from pathlib import Path

STRING_RE = re.compile(rb"[ -~]{5,}")


def inspect_prefix(entry, archives, sample_size=256):
    path = entry["path"]
    size = int(entry["size"])
    archive_id = int(entry["archive_id"])
    offset = int(entry["byte_offset"])
    if sample_size < 16:
        raise ValueError("sample_size must be at least 16")
    if size < 0:
        raise ValueError(f"negative resource size for {path}")
    if size and archive_id not in archives:
        raise ValueError(f"archive {archive_id} was not supplied for {path}")
    amount = min(size, sample_size)
    if amount:
        with archives[archive_id].open("rb") as stream:
            stream.seek(offset)
            data = stream.read(amount)
        if len(data) != amount:
            raise ValueError(f"short read for {path} at {archive_id}:{offset}")
    else:
        data = b""

    words = []
    for pos in range(0, len(data) - 3, 4):
        value = struct.unpack_from("<I", data, pos)[0]
        words.append({"offset": pos, "hex": f"0x{value:08X}", "u32": value})
    strings = [
        {"offset": match.start(), "text": match.group().decode("ascii")}
        for match in STRING_RE.finditer(data)
    ]
    return {
        "index": int(entry["index"]),
        "path": path,
        "archive_id": archive_id,
        "offset": offset,
        "file_size": size,
        "sampled_bytes": len(data),
        "sample_sha256": hashlib.sha256(data).hexdigest(),
        "words_le_u32": words,
        "ascii_strings": strings,
    }


def inspect_catalogue(catalogue, archives, limit=16, sample_size=256):
    if limit < 2:
        raise ValueError("limit must be at least 2")
    vehicles, tracks, seen = [], [], set()
    with catalogue.open("r", newline="", encoding="utf-8-sig") as stream:
        for entry in csv.DictReader(stream):
            path = entry["path"]
            upper = path.upper()
            if entry.get("resolution") != "resolved" or not path or path in seen:
                continue
            is_vehicle = upper.startswith("CARS\\") and upper.endswith("\\GEOMETRY.BIN")
            is_track = upper.startswith("TRACKS\\") and (
                "\\ROUTES" in upper or "TRACKMAP" in upper
                or upper.endswith(".RWS")
            )
            if not (is_vehicle or is_track):
                continue
            seen.add(path)
            target = vehicles if is_vehicle else tracks
            target.append(inspect_prefix(entry, archives, sample_size))
    v_limit = limit // 2
    t_limit = limit - v_limit
    return vehicles[:v_limit] + tracks[:t_limit]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalogue", type=Path)
    parser.add_argument("--archive", action="append", required=True, metavar="ID=PATH")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=16)
    parser.add_argument("--sample-size", type=int, default=256)
    args = parser.parse_args()
    archives = {}
    for spec in args.archive:
        key, sep, value = spec.partition("=")
        if not sep:
            parser.error(f"invalid archive mapping: {spec}")
        archives[int(key)] = Path(value)
    try:
        resources = inspect_catalogue(
            args.catalogue, archives, args.limit, args.sample_size
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"resources": resources}, indent=2) + "\\n",
        encoding="utf-8",
    )
    print(f"Inspected {len(resources)} resource prefixes ({args.sample_size} byte limit).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
