import csv
import tempfile
import unittest
from pathlib import Path

from zdir_probe import probe_catalogue


class ZdirProbeTests(unittest.TestCase):
    def test_reads_only_header_and_deduplicates_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "zzdata.bin"
            archive.write_bytes(b"\x01\x02\x03\x04" + b"x" * 100)
            catalogue = root / "catalogue.csv"
            fields = [
                "index", "path", "resolution", "archive_id",
                "byte_offset", "size",
            ]
            with catalogue.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow({
                    "index": 0, "path": "CARS\\TEST\\GEOMETRY.BIN",
                    "resolution": "resolved", "archive_id": 0,
                    "byte_offset": 0, "size": 104,
                })
                writer.writerow({
                    "index": 1, "path": "CARS\\TEST\\GEOMETRY.BIN",
                    "resolution": "resolved", "archive_id": 0,
                    "byte_offset": 4, "size": 100,
                })
            rows = probe_catalogue(catalogue, {0: archive}, limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["header_hex"], (b"\x01\x02\x03\x04" + b"x" * 60).hex().upper())
            self.assertEqual(rows[0]["status"], "probed")


if __name__ == "__main__":
    unittest.main()
