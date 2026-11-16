#!/usr/bin/env python3
"""Probe headers of selected ZDIR resources without extracting payloads."""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path


def _probe(entry, archives):
    path = entry["path"]
    size = int(entry["size"])
    archive_id = int(entry["archive_id"])
    offset = int(entry["byte_offset"])
    row = {
        "index": entry["index"],
        "path": path,
        "archive_id": archive_id,
        "offset": offset,
        "size": size,
        "status": "empty" if size == 0 else "probed",
        "header_hex": "",
        "ascii_preview": "",
        "sha256_sample": "",
    }
    if size > 0:
        if archive_id not in archives:
            raise ValueError(f"archive {archive_id} was not supplied")
        with archives[archive_id].open("rb") as archive:
            archive.seek(offset)
            sample = archive.read(min(size, 64))
        if len(sample) != min(size, 64):
            raise ValueError(f"short read for {path} at archive {archive_id}:{offset}")
        row["header_hex"] = sample.hex().upper()
        row["ascii_preview"] = "".join(chr(b) if 32 <= b < 127 else "." for b in sample)
        row["sha256_sample"] = hashlib.sha256(sample).hexdigest()
    return row


def probe_catalogue(catalogue: Path, archives: dict[int, Path], limit: int = 32):
    if limit < 2:
        raise ValueError("limit must be at least 2 to sample both resource groups")
    vehicles, tracks = [], []
    seen = set()
    with catalogue.open("r", newline="", encoding="utf-8-sig") as stream:
        for entry in csv.DictReader(stream):
            path = entry["path"]
            if entry["resolution"] != "resolved" or not path or path in seen:
                continue
            upper = path.upper()
            is_vehicle = upper.startswith("CARS\\") and (
                upper.endswith("\\GEOMETRY.BIN")
                or upper.endswith(".BGV")
                or upper.endswith(".HWD")
                or upper.endswith(".LWD")
                or upper.endswith(".BTV")
            )
            is_track = upper.startswith("TRACKS\\") and (
                "\\ROUTES" in upper or "TRACKMAP" in upper or upper.endswith(".RWS")
            )
            if not (is_vehicle or is_track):
                continue
            seen.add(path)
            target = vehicles if is_vehicle else tracks
            target.append(_probe(entry, archives))
    # Keep both families represented instead of allowing the larger track
    # family to crowd all vehicle samples out of the report.
    vehicle_limit = limit // 2
    track_limit = limit - vehicle_limit
    return vehicles[:vehicle_limit] + tracks[:track_limit]


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
        rows = probe_catalogue(args.catalogue, archives, args.limit)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    fields = [
        "index", "path", "archive_id", "offset", "size", "status",
        "header_hex", "ascii_preview", "sha256_sample",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Probed {len(rows)} unique resources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
