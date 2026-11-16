import tempfile
import unittest
from pathlib import Path

from zdir_catalog import build_catalogue, nfs_name_hash


class ZdirCatalogueTests(unittest.TestCase):
    def test_hash_is_case_insensitive(self):
        self.assertEqual(nfs_name_hash("cars\CAR1.BGV"), nfs_name_hash("CARS\car1.bgv"))

    def test_hash_matches_reference_example(self):
        self.assertEqual(nfs_name_hash("GLOBAL\\FRONTENDMEMORYFILE.BIN"), 0xC08BE7BA)

    def test_resolves_unique_name_and_preserves_unknown(self):
        import struct
        records = b"".join([
            struct.pack("<IiIIiI", nfs_name_hash("CARS\\CAR1.BGV"), 0, 1, 0, 32, 0),
            struct.pack("<IiIIiI", 0x01020304, 1, 2, 0, 64, 0),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            names = Path(tmp) / "FileNames.list"
            names.write_text("CARS\\CAR1.BGV\n", encoding="utf-8")
            summary, rows = build_catalogue(records, names)
        self.assertEqual(summary["resolved"], 1)
        self.assertEqual(summary["unresolved"], 1)
        self.assertEqual(rows[0]["path"], "CARS\\CAR1.BGV")
        self.assertEqual(rows[1]["path"], "__Unknown/01020304")


if __name__ == "__main__":
    unittest.main()
