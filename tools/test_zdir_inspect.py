import struct
import unittest

from zdir_inspect import inspect, parse_index


class ZdirInspectorTests(unittest.TestCase):
    def record(self, archive_id=0, sector=1, size=100):
        return struct.pack("<IiIIiI", 0x12345678, archive_id, sector, 0, size, 0xAABBCCDD)

    def test_parses_24_byte_little_endian_record(self):
        rows = parse_index(self.record())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name_hash"], "12345678")
        self.assertEqual(rows[0]["byte_offset"], 2048)
        self.assertEqual(rows[0]["size"], 100)

    def test_checks_entry_against_archive_boundary(self):
        summary, _ = inspect(self.record(), {0: 2148})
        self.assertEqual(summary["problem_count"], 0)

        summary, _ = inspect(self.record(), {0: 2147})
        self.assertEqual(summary["problem_count"], 1)

    def test_rejects_invalid_archive_id(self):
        summary, _ = inspect(self.record(archive_id=4), {})
        self.assertEqual(summary["problem_count"], 1)
        self.assertIn("invalid archive id", summary["problems"][0])

    def test_rejects_negative_file_size(self):
        summary, _ = inspect(self.record(size=-1), {})
        self.assertEqual(summary["problem_count"], 1)
        self.assertIn("negative size", summary["problems"][0])

    def test_rejects_partial_record(self):
        with self.assertRaises(ValueError):
            parse_index(self.record()[:-1])


if __name__ == "__main__":
    unittest.main()
