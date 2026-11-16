import json
import tempfile
import unittest
from pathlib import Path

from ps2_resource_probe import inspect_prefix


class Ps2ResourceProbeTests(unittest.TestCase):
    def test_decodes_little_endian_words_and_ascii_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive.bin"
            archive.write_bytes(
                bytes.fromhex("00401380 08000000") + b"HELLO_RESOURCE" + b"\\0" * 8
            )
            entry = {
                "index": "7", "path": "CARS\\TEST\\GEOMETRY.BIN",
                "archive_id": "0", "byte_offset": "0", "size": "34",
            }
            result = inspect_prefix(entry, {0: archive}, sample_size=64)
            self.assertEqual(result["words_le_u32"][0]["hex"], "0x80134000")
            self.assertEqual(result["words_le_u32"][1]["u32"], 8)
            self.assertIn(
                {"offset": 8, "text": "HELLO_RESOURCE"},
                result["ascii_strings"],
            )
            self.assertEqual(result["sampled_bytes"], 34)


if __name__ == "__main__":
    unittest.main()
