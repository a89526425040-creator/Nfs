import csv
import tempfile
import unittest
from pathlib import Path

from ps2_texture_probe import inspect_texture_resources


class TextureProbeTests(unittest.TestCase):
    def test_inspects_texture_resource_and_finds_embedded_signature(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "archive.bin"
            # One valid leaf chunk followed by an embedded TIM2 marker.
            payload = (
                (0x00123456).to_bytes(4, "little")
                + (12).to_bytes(4, "little")
                + b"ABCDTIM2WXYZ"
            )
            archive.write_bytes(b"prefix" + payload)
            catalogue = root / "catalogue.csv"
            with catalogue.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=["path", "resolution", "archive_id", "byte_offset", "size"],
                )
                writer.writeheader()
                writer.writerow({
                    "path": r"CARS\RX7\TEXTURES.BIN",
                    "resolution": "resolved",
                    "archive_id": 0,
                    "byte_offset": 6,
                    "size": len(payload),
                })
            result = inspect_texture_resources(catalogue, {0: archive})
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["path"], r"CARS\RX7\TEXTURES.BIN")
            self.assertEqual(result[0]["file_size"], len(payload))
            self.assertEqual(result[0]["signatures"], [{"format": "TIM2", "offset": 12}])
            self.assertEqual(result[0]["chunk_count"], 1)
            self.assertEqual(result[0]["chunk_errors"], [])

    def test_ignores_non_texture_resources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "archive.bin"
            archive.write_bytes(b"")
            catalogue = root / "catalogue.csv"
            with catalogue.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=["path", "resolution", "archive_id", "byte_offset", "size"],
                )
                writer.writeheader()
                writer.writerow({
                    "path": r"CARS\RX7\GEOMETRY.BIN",
                    "resolution": "resolved",
                    "archive_id": 0,
                    "byte_offset": 0,
                    "size": 0,
                })
            self.assertEqual(inspect_texture_resources(catalogue, {0: archive}), [])


if __name__ == "__main__":
    unittest.main()
