#!/usr/bin/env python3
"""Extract and group ELF .DVP.overlay chunks using .DVP.ovlytab metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path


def _cstring(data: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(data):
        raise ValueError(f"string offset 0x{offset:X} outside table")
    end = data.find(b"\0", offset)
    if end < 0:
        end = len(data)
    return data[offset:end].decode("ascii", "replace")


def parse_dvp_overlays(elf: bytes) -> dict:
    if len(elf) < 52 or elf[:7] != bytes.fromhex("7f454c46010101"):
        raise ValueError("expected ELF32 little-endian executable")
    header = struct.unpack_from("<16sHHIIIIIHHHHHH", elf, 0)
    shoff, shentsize, shnum, shstrndx = header[6], header[11], header[12], header[13]
    if shentsize < 40 or shstrndx >= shnum or shoff + shentsize * shnum > len(elf):
        raise ValueError("invalid ELF section-header table")
    sections = []
    for index in range(shnum):
        fields = struct.unpack_from("<IIIIIIIIII", elf, shoff + index * shentsize)
        name_off, kind, flags, addr, offset, size, link, info, align, entsize = fields
        sections.append({
            "index": index, "name_off": name_off, "type": kind, "flags": flags,
            "addr": addr, "offset": offset, "size": size, "link": link,
            "info": info, "align": align, "entsize": entsize,
        })
    shstr = sections[shstrndx]
    names = elf[shstr["offset"]:shstr["offset"] + shstr["size"]]
    for section in sections:
        section["name"] = _cstring(names, section["name_off"]) if section["name_off"] else ""
        if section["offset"] + section["size"] > len(elf) and section["type"] != 8:
            raise ValueError(f"section {section['name']} exceeds ELF bounds")
    by_name = {section["name"]: section for section in sections}
    table = by_name.get(".DVP.ovlytab")
    strings = by_name.get(".DVP.ovlystrtab")
    if table is None or strings is None:
        raise ValueError("ELF has no .DVP.ovlytab / .DVP.ovlystrtab pair")
    if table["size"] % 12:
        raise ValueError(f".DVP.ovlytab size {table['size']} is not divisible by 12")
    linked_strings = sections[table["link"]] if table["link"] < len(sections) else strings
    if linked_strings["type"] != 3:
        linked_strings = strings
    str_data = elf[linked_strings["offset"]:linked_strings["offset"] + linked_strings["size"]]
    shstr_data = names
    tab_data = elf[table["offset"]:table["offset"] + table["size"]]
    overlay_sections = [section for section in sections if section["name"].startswith(".DVP.overlay.")]
    overlay_sections.sort(key=lambda section: section["index"])
    entries = []
    groups: dict[str, list[dict]] = {}
    errors = []
    for pos in range(0, len(tab_data), 12):
        name_off, ee_addr, vu_addr = struct.unpack_from("<III", tab_data, pos)
        try:
            name = _cstring(str_data, name_off)
        except ValueError:
            name = ""
        if not name.startswith(".DVP.overlay."):
            try:
                alternate = _cstring(shstr_data, name_off)
            except ValueError:
                alternate = ""
            if alternate.startswith(".DVP.overlay."):
                name = alternate
        section = by_name.get(name)
        if section is None and pos // 12 < len(overlay_sections):
            section = overlay_sections[pos // 12]
            name = section["name"]
        match = re.fullmatch(r"\.DVP\.overlay\.\.(?:0x[0-9a-fA-F]+|unknvma)\.(\d+)\.(\d+)\.(\d+)", name)
        if section is None:
            errors.append(f"table entry {pos // 12}: section {name!r} not found")
            continue
        if not match:
            errors.append(f"overlay name does not match expected convention: {name}")
            continue
        program_id, line, chunk = match.groups()
        section_type = section["type"]
        file_backed = section_type != 8  # ELF SHT_NOBITS sections have no payload in the file.
        raw = (
            elf[section["offset"]:section["offset"] + section["size"]]
            if file_backed else b""
        )
        entry = {
            "name": name, "program_id": program_id, "line": int(line), "chunk": int(chunk),
            "ee_address": ee_addr, "vu_address": vu_addr, "section_type": section_type,
            "file_backed": file_backed, "allocated_bytes": section["size"],
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "data": raw,
        }
        entries.append({k: v for k, v in entry.items() if k != "data"})
        groups.setdefault(program_id, []).append(entry)
    programs = []
    for program_id, chunks in sorted(groups.items(), key=lambda item: int(item[0])):
        chunks.sort(key=lambda x: x["chunk"])
        start = chunks[0]["vu_address"]
        expected = start
        contiguous = True
        combined = bytearray()
        for chunk in chunks:
            if chunk["vu_address"] != expected:
                contiguous = False
            combined.extend(chunk["data"])
            expected = chunk["vu_address"] + chunk["allocated_bytes"]
        programs.append({
            "program_id": program_id, "vu_start": start,
            "chunk_count": len(chunks),
            "allocated_bytes": sum(item["allocated_bytes"] for item in chunks),
            "file_backed_bytes": len(combined),
            "bytes": len(combined),
            "contiguous": contiguous, "chunks": [
                {k: v for k, v in item.items() if k != "data"} for item in chunks
            ], "data": bytes(combined),
        })
    return {
        "table_entries": len(tab_data) // 12,
        "table_link": table["link"],
        "linked_string_section": linked_strings["name"],
        "entries": entries,
        "programs": programs,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = parse_dvp_overlays(args.elf.read_bytes())
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for program in report["programs"]:
        filename = f"program_{program['program_id']}_vu_{program['vu_start']:04X}.bin"
        (args.out_dir / filename).write_bytes(program.pop("data"))
        program["file"] = filename
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"DVP overlay table: {report['table_entries']} entries, "
        f"{len(report['programs'])} grouped programs, {len(report['errors'])} errors"
    )
    for program in report["programs"]:
        print(
            f"VU 0x{program['vu_start']:04X}: program {program['program_id']}, "
            f"{program['chunk_count']} chunks, {program['allocated_bytes']} allocated bytes, "
            f"{program['file_backed_bytes']} file-backed bytes, "
            f"contiguous={program['contiguous']}"
        )
        for chunk in program["chunks"]:
            print(
                f"  chunk {chunk['chunk']}: EE=0x{chunk['ee_address']:08X}, "
                f"VU=0x{chunk['vu_address']:04X}, allocated={chunk['allocated_bytes']}, "
                f"file_backed={chunk['file_backed']}, sh_type={chunk['section_type']}, "
                f"name={chunk['name']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
