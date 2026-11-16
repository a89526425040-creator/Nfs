#!/usr/bin/env python3
"""Resolve ZDIR filename hashes using an external candidate path list.

This tool reads index metadata only. It never extracts archive payloads.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from zdir_inspect import parse_index


def nfs_name_hash(value: str) -> int:
    """Ekey NFS.BIN.Tool path hash: h = 33*h + uppercase UTF-16 code unit."""
    result = 0xFFFFFFFF
    for char in value.upper():
        code = ord(char)
        if code > 0xFFFF:
            raise ValueError("supplementary Unicode characters are not supported")
        result = (33 * result + code) & 0xFFFFFFFF
    return result


def load_names(path: Path):
    by_hash = defaultdict(list)
    count = 0
    with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
        for raw in stream:
            name = raw.rstrip("\r\n")
            if not name:
                continue
            by_hash[nfs_name_hash(name)].append(name)
            count += 1
    return by_hash, count


def build_catalogue(zdir: bytes, names_path: Path):
    names, name_count = load_names(names_path)
    rows = []
    for entry in parse_index(zdir):
        key = int(entry["name_hash"], 16)
        candidates = names.get(key, [])
        if len(candidates) == 1:
            resolved_name, status = candidates[0], "resolved"
        elif len(candidates) > 1:
            resolved_name, status = "", "collision"
        else:
            resolved_name, status = f"__Unknown/{entry['name_hash']}", "unresolved"
        rows.append({
            **entry,
            "path": resolved_name,
            "resolution": status,
            "candidates": candidates,
        })
    summary = {
        "entry_count": len(rows),
        "name_list_lines": name_count,
        "resolved": sum(r["resolution"] == "resolved" for r in rows),
        "unresolved": sum(r["resolution"] == "unresolved" for r in rows),
        "collisions": sum(r["resolution"] == "collision" for r in rows),
    }
    return summary, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zdir", type=Path)
    parser.add_argument("--names", required=True, type=Path, help="external FileNames.list")
    parser.add_argument("--csv", required=True, type=Path, help="output CSV catalogue")
    parser.add_argument("--summary", required=True, type=Path, help="output JSON summary")
    args = parser.parse_args()

    try:
        summary, rows = build_catalogue(args.zdir.read_bytes(), args.names)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    fields = [
        "index", "name_hash", "path", "resolution", "archive_id",
        "local_offset_sectors", "byte_offset", "size", "total_offset", "checksum",
    ]
    with args.csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fields})
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
