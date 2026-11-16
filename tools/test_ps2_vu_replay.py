import json
import struct
import tempfile
import unittest
from pathlib import Path

from ps2_vu_replay import (
    build_vif_state, make_mpg_upload, make_vutext_program,
    parse_gif_capture, rewrite_mscal, vu_program_stats,
)


class Ps2VuReplayTests(unittest.TestCase):
    def test_counts_e_bit_and_xgkick_instruction_pairs(self):
        lower = (0x40 << 25) | (0x6C << 4)
        upper = 1 << 30
        raw = struct.pack("<II", lower, upper) + bytes(8)
        stats = vu_program_stats(raw)
        self.assertEqual(stats["instruction_pairs"], 2)
        self.assertEqual(stats["ebit_instructions"], 1)
        self.assertEqual(stats["xgkick_instructions"], 1)

    def test_builds_one_mpg_command_per_dvp_chunk(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = bytes(range(16))
            (root / "program.bin").write_bytes(raw)
            program = {
                "program_id": "77",
                "file": "program.bin",
                "bytes": 16,
                "chunks": [
                    {"bytes": 8, "vu_address": 0},
                    {"bytes": 8, "vu_address": 8},
                ],
            }
            result = make_mpg_upload(program, root)
            first, second = struct.unpack_from("<I", result, 0)[0], struct.unpack_from("<I", result, 12)[0]
            self.assertEqual(first, (0x4A << 24) | (1 << 16) | 0)
            self.assertEqual(second, (0x4A << 24) | (1 << 16) | 1)
            self.assertEqual(result[4:12], raw[:8])
            self.assertEqual(result[16:24], raw[8:])

    def test_builds_vutext_chunks_at_the_declared_vu_address(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "code.bin").write_bytes(bytes(2056))
            program = make_vutext_program(
                {"index": 0, "vu": 0x800, "bytes": 2056, "file": "code.bin"},
                root,
            )
            self.assertEqual(program["vu_start"], 0x800)
            self.assertEqual(
                program["chunks"],
                [
                    {"bytes": 2048, "vu_address": 0x800},
                    {"bytes": 8, "vu_address": 0x1000},
                ],
            )

    def test_initializes_vif_top_state(self):
        words = struct.unpack("<IIIII", build_vif_state(638, 320))
        self.assertEqual(words, (
            0x01000101, 0x05000000, 0x0300027E, 0x02000140, 0x0400027E
        ))

    def test_rewrites_only_mscal_commands(self):
        raw = struct.pack("<III", 0x14000000, 0x00000000, 0x14000000)
        meta = {
            "commands": [
                {"offset": 0, "label": "MSCAL"},
                {"offset": 8, "label": "MSCAL"},
            ]
        }
        rewritten, count = rewrite_mscal(raw, meta, 0x100)
        self.assertEqual(count, 2)
        self.assertEqual(struct.unpack("<III", rewritten), (
            0x14000100, 0x00000000, 0x14000100
        ))

    def test_parses_a_single_gif_eop_tag(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tag_lo = (1 << 15) | (1 << 60)  # EOP, NLOOP=0, NREG=1
            (root / "gif-packets.bin").write_bytes(struct.pack("<QQ", tag_lo, 0))
            (root / "gif-segments.tsv").write_text("1\t1\t0\n", encoding="utf-8")
            report = parse_gif_capture(root)
            self.assertEqual(report["gif_tag_count"], 1)
            self.assertEqual(report["gif_eop_packets"], 1)
            self.assertEqual(report["gif_parse_errors"], 0)
            self.assertEqual(report["path1_qwc"], 1)


if __name__ == "__main__":
    unittest.main()
