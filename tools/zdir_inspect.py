#!/usr/bin/env python3
"""Inspect a PS2 NFS ZDIR index without extracting archive payloads."""

from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

# name hash:u32, archive id:i32, local sector offset:u32,
# total offset:u32, file size:i32, checksum:u32
RECORD = struct.Struct("<IiIIiI")
SECTOR_SIZE = 2048
ARCHIVE_COUNT = 4


def parse_index(data: bytes):
    if len(data) % RECORD.size:
        raise ValueError(
            f"ZDIR size {len(data)} is not divisible by {RECORD.size}"
        )

    rows = []
    for index, values in enumerate(RECORD.iter_unpack(data)):
        name_hash, archive_id, local_sectors, total_offset, size, checksum = values
        rows.append({
            "index": index,
            "name_hash": f"{name_hash:08X}",
            "archive_id": archive_id,
            "local_offset_sectors": local_sectors,
            "byte_offset": local_sectors * SECTOR_SIZE,
            "total_offset": total_offset,
            "size": size,
            "checksum": f"{checksum:08X}",
        })
    return rows


def inspect(data: bytes, archive_sizes: dict[int, int]):
    rows = parse_index(data)
    groups = defaultdict(list)
    problems = []

    for row in rows:
        aid = row["archive_id"]
        groups[aid].append(row)
        if aid < 0 or aid >= ARCHIVE_COUNT:
            problems.append(f"entry {row['index']}: invalid archive id {aid}")
            continue
        if row["size"] < 0:
            problems.append(f"entry {row['index']}: negative size {row['size']}")
            continue
        if archive_sizes:
            if aid not in archive_sizes:
                problems.append(f"entry {row['index']}: no size supplied for archive {aid}")
            elif (row["byte_offset"] > archive_sizes[aid]
                  or row["size"] > archive_sizes[aid] - row["byte_offset"]):
                problems.append(
                    f"entry {row['index']}: range "
                    f"[{row['byte_offset']}, {row['byte_offset'] + row['size']}) "
                    f"exceeds ZZDATA{aid}.BIN ({archive_sizes[aid]} bytes)"
                )

    summary = {
        "index_bytes": len(data),
        "record_size": RECORD.size,
        "record_count": len(rows),
        "sector_size": SECTOR_SIZE,
        "archive_validation_performed": bool(archive_sizes),
        "archives": {},
        "problem_count": len(problems),
        "problems": problems[:100],
    }

    for aid in sorted(set(groups) | set(archive_sizes)):
        entries = groups.get(aid, [])
        valid_entries = [e for e in entries if e["size"] >= 0 and 0 <= aid < ARCHIVE_COUNT]
        summary["archives"][str(aid)] = {
            "file": f"ZZDATA{aid}.BIN",
            "archive_bytes": archive_sizes.get(aid),
            "entry_count": len(entries),
            "declared_payload_bytes": sum(e["size"] for e in valid_entries),
            "max_entry_bytes": max((e["size"] for e in valid_entries), default=0),
            "max_end_offset": max(
                (e["byte_offset"] + e["size"] for e in valid_entries), default=0
            ),
        }

    return summary, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zdir", type=Path, help="path to ZDIR.BIN")
    parser.add_argument(
        "--archive", action="append", default=[], metavar="ID=PATH",
        help="corresponding ZZDATA archive; may be repeated for IDs 0..3",
    )
    parser.add_argument("--output", type=Path, help="write JSON report to this path")
    parser.add_argument("--entries", type=Path, help="write per-entry JSONL to this path")
    args = parser.parse_args()

    archive_sizes = {}
    for item in args.archive:
        try:
            key, value = item.split("=", 1)
            archive_id = int(key, 10)
            if archive_id < 0 or archive_id >= ARCHIVE_COUNT:
                raise ValueError("archive ID must be 0, 1, 2, or 3")
            archive_sizes[archive_id] = Path(value).stat().st_size
        except (ValueError, OSError) as exc:
            parser.error(f"invalid --archive {item!r}: {exc}")

    try:
        data = args.zdir.read_bytes()
        summary, rows = inspect(data, archive_sizes)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)

    if args.entries:
        with args.entries.open("w", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, sort_keys=True) + "\n")

    return 1 if summary["problem_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
