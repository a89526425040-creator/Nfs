#!/usr/bin/env python3
"""Replay PS2 VIF geometry through the VU1 program extracted from .vutext."""
from __future__ import annotations

import argparse
import json
import struct
import subprocess
from collections import Counter
from pathlib import Path


def vu_program_stats(raw: bytes) -> dict:
    if len(raw) % 8:
        raise ValueError("VU microprogram size is not a multiple of 8 bytes")
    ebit = xgkick = 0
    for offset in range(0, len(raw), 8):
        lower, upper = struct.unpack_from("<II", raw, offset)
        ebit += bool(upper & (1 << 30))
        special = (lower & 3) | ((lower >> 4) & 0x7C)
        if (lower >> 25) == 0x40 and special == 0x6C:
            xgkick += 1
    return {
        "instruction_pairs": len(raw) // 8,
        "ebit_instructions": ebit,
        "xgkick_instructions": xgkick,
    }


def make_mpg_upload(program: dict, binary_dir: Path) -> bytes:
    raw = (binary_dir / program["file"]).read_bytes()
    if len(raw) != program["bytes"]:
        raise ValueError(f"program {program['program_id']} binary size mismatch")
    commands = bytearray()
    cursor = 0
    for chunk in program["chunks"]:
        size = int(chunk["bytes"])
        part = raw[cursor:cursor + size]
        if len(part) != size or size % 8:
            raise ValueError(f"program {program['program_id']} has an invalid chunk size")
        address = int(chunk["vu_address"])
        if address % 8:
            raise ValueError(f"program {program['program_id']} chunk address is not 8-byte aligned")
        pairs = size // 8
        if pairs < 1 or pairs > 256:
            raise ValueError(f"program {program['program_id']} chunk has {pairs} pairs")
        num = 0 if pairs == 256 else pairs
        word = (0x4A << 24) | (num << 16) | ((address // 8) & 0xFFFF)
        commands.extend(struct.pack("<I", word))
        commands.extend(part)
        cursor += size
    if cursor != len(raw):
        raise ValueError(f"program {program['program_id']} chunks do not cover its binary")
    return bytes(commands)


def make_vutext_program(meta: dict, binary_dir: Path) -> dict:
    raw = (binary_dir / meta["file"]).read_bytes()
    if len(raw) != int(meta["bytes"]):
        raise ValueError(f".vutext program {meta['index']} binary size mismatch")
    start = int(meta["vu"])
    chunks = []
    cursor = 0
    while cursor < len(raw):
        size = min(2048, len(raw) - cursor)
        chunks.append({"bytes": size, "vu_address": start + cursor})
        cursor += size
    return {
        "program_id": f"vutext_{meta['index']}",
        "vu_start": start,
        "file": meta["file"],
        "bytes": len(raw),
        "chunks": chunks,
    }


def build_vif_state(base: int, offset: int) -> bytes:
    # STCYCL(1,1), STMOD(0), BASE, OFFSET, ITOP.
    words = (
        0x01000101,
        0x05000000,
        0x03000000 | (base & 0x3FF),
        0x02000000 | (offset & 0x3FF),
        0x04000000 | (base & 0x3FF),
    )
    return struct.pack("<" + "I" * len(words), *words)


def rewrite_mscal(stream_data: bytes, stream_meta: dict, immediate: int) -> tuple[bytes, int]:
    raw = bytearray(stream_data)
    changed = 0
    for command in stream_meta.get("commands", []):
        if command.get("label") != "MSCAL":
            continue
        offset = int(command["offset"])
        if offset < 0 or offset + 4 > len(raw):
            raise ValueError(f"MSCAL command offset outside stream: {offset}")
        word = struct.unpack_from("<I", raw, offset)[0]
        word = (word & 0xFFFF0000) | (immediate & 0xFFFF)
        struct.pack_into("<I", raw, offset, word)
        changed += 1
    return bytes(raw), changed


def parse_gif_capture(capture_dir: Path) -> dict:
    packet_path = capture_dir / "gif-packets.bin"
    segment_path = capture_dir / "gif-segments.tsv"
    data = packet_path.read_bytes() if packet_path.exists() else b""
    segments = []
    if segment_path.exists():
        for line in segment_path.read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) == 3:
                segments.append({
                    "path": int(fields[0]),
                    "qwc": int(fields[1]),
                    "offset": int(fields[2]),
                })
    path1_qwc = sum(s["qwc"] for s in segments if s["path"] == 1)
    path2_qwc = sum(s["qwc"] for s in segments if s["path"] == 2)
    tags = eop_packets = malformed = 0
    prims = Counter()
    for segment in segments:
        if segment["path"] != 1:
            continue
        start = segment["offset"]
        end = start + segment["qwc"] * 16
        if end > len(data):
            malformed += 1
            continue
        pos = start
        while pos + 16 <= end:
            lo, hi = struct.unpack_from("<QQ", data, pos)
            nloop = lo & 0x7FFF
            eop = (lo >> 15) & 1
            prim = (lo >> 47) & 0x7FF
            flg = (lo >> 58) & 3
            nreg = (lo >> 60) & 15 or 16
            payload_qwc = (
                nloop * nreg if flg == 0
                else (nloop * nreg + 1) // 2 if flg == 1
                else nloop
            )
            total = 16 + payload_qwc * 16
            if pos + total > end:
                malformed += 1
                break
            tags += 1
            prims[str(prim)] += 1
            pos += total
            if eop:
                eop_packets += 1
        if pos != end:
            malformed += 1
    return {
        "gif_bytes": len(data),
        "segment_count": len(segments),
        "path1_qwc": path1_qwc,
        "path2_qwc": path2_qwc,
        "gif_tag_count": tags,
        "gif_eop_packets": eop_packets,
        "gif_prim_histogram": dict(sorted(prims.items(), key=lambda item: int(item[0]))),
        "gif_parse_errors": malformed,
    }


def run_replay(
    harness: Path,
    prefix: bytes,
    stream_data: bytes,
    output_dir: Path,
    timeout: int,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    input_path = output_dir / "input.vif"
    input_path.write_bytes(prefix + stream_data)
    try:
        result = subprocess.run(
            [str(harness), str(input_path), str(output_dir)],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        (output_dir / "runner.log").write_text(
            result.stdout + "\n--- STDERR ---\n" + result.stderr,
            encoding="utf-8",
        )
        capture = parse_gif_capture(output_dir)
        return {
            "return_code": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-2000:],
            **capture,
            "vu_dump_files": sorted(
                p.name for p in output_dir.glob("*.bin")
                if p.name.startswith(("micro_", "mem_"))
            ),
            "has_register_dump": any(output_dir.glob("regs_*.txt")),
        }
    except subprocess.TimeoutExpired as exc:
        (output_dir / "runner.log").write_text(
            f"Timed out after {timeout} seconds\n{exc}",
            encoding="utf-8",
        )
        return {
            "timeout": True,
            "gif_bytes": 0,
            "gif_tag_count": 0,
            "gif_parse_errors": 0,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vutext-json", type=Path, required=True)
    parser.add_argument("--vutext-dir", type=Path, required=True)
    parser.add_argument("--vif-json", type=Path, required=True)
    parser.add_argument("--vif-dir", type=Path, required=True)
    parser.add_argument("--harness", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--vehicle", default="CARS\\RX7\\GEOMETRY.BIN")
    parser.add_argument("--mscal-override", type=lambda value: int(value, 0), default=0x100)
    parser.add_argument("--base", type=int, default=638)
    parser.add_argument("--offsets", default="0,256,320,512")
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    vutext = json.loads(args.vutext_json.read_text(encoding="utf-8"))
    vif = json.loads(args.vif_json.read_text(encoding="utf-8"))
    resource = next(
        (item for item in vif["resources"] if item["path"].upper() == args.vehicle.upper()),
        None,
    )
    if resource is None:
        parser.error(f"vehicle geometry resource not found: {args.vehicle}")
    streams = resource["streams"]
    if not streams:
        parser.error(f"no VIF streams found in {args.vehicle}")

    programs = [
        make_vutext_program(meta, args.vutext_dir)
        for meta in vutext["programs"]
    ]
    if not programs:
        parser.error("no raw .vutext MPG program blocks were exported")
    offsets = [int(value.strip(), 0) for value in args.offsets.split(",") if value.strip()]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for program in programs:
        raw_code = (args.vutext_dir / program["file"]).read_bytes()
        stats = vu_program_stats(raw_code)
        upload = make_mpg_upload(program, args.vutext_dir)
        for offset in offsets:
            prefix = build_vif_state(args.base, offset) + upload
            for stream_index, stream in enumerate(streams):
                raw_name = stream.get("raw_file")
                if not raw_name:
                    continue
                stream_path = args.vif_dir / raw_name
                stream_data, rewritten = rewrite_mscal(
                    stream_path.read_bytes(), stream, args.mscal_override
                )
                capture_dir = args.output_dir / (
                    f"{program['program_id']}_base_{args.base}_offset_{offset}_stream_{stream_index}"
                )
                result = run_replay(
                    args.harness, prefix, stream_data, capture_dir, args.timeout
                )
                results.append({
                    "program_id": program["program_id"],
                    "vu_start": program["vu_start"],
                    "program_bytes": program["bytes"],
                    "stream_index": stream_index,
                    "stream_offset": stream["chunk_offset"],
                    "stream_bytes": stream["stream_bytes"],
                    "instruction_pairs": stats["instruction_pairs"],
                    "ebit_instructions": stats["ebit_instructions"],
                    "xgkick_instructions": stats["xgkick_instructions"],
                    "mscal_override": args.mscal_override,
                    "mscals_rewritten": rewritten,
                    "base": args.base,
                    "offset": offset,
                    **result,
                })

    report = {
        "vehicle": resource["path"],
        "programs_loaded": [
            {
                "program_id": p["program_id"],
                "vu_start": p["vu_start"],
                "bytes": p["bytes"],
            }
            for p in programs
        ],
        "mscal_override": args.mscal_override,
        "base": args.base,
        "offsets_tested": offsets,
        "streams": len(streams),
        "replays": results,
    }
    (args.output_dir / "vu-replay-report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Replayed {len(results)} .vutext-program / VIF-stream / TOPS-offset combinations."
    )
    for item in results:
        print(
            f"{item['program_id']} stream {item['stream_index']} "
            f"BASE={item['base']} OFFSET={item['offset']}: "
            f"GIF {item.get('gif_bytes', 0)} bytes, "
            f"{item.get('gif_tag_count', 0)} tags, "
            f"{item.get('gif_eop_packets', 0)} EOP packets, "
            f"MSCALs={item['mscals_rewritten']}, "
            f"return={item.get('return_code', 'timeout')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
