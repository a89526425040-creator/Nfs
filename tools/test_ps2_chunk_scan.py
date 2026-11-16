import struct
import unittest

from ps2_chunk_scan import flatten, scan_bytes


class Ps2ChunkScanTests(unittest.TestCase):
    def test_walks_nested_containers_and_padding(self):
        leaf = struct.pack("<II", 0x00134002, 4) + b"DATA"
        inner = struct.pack("<II", 0x80134001, len(leaf)) + leaf
        root_payload = struct.pack("<II", 0, 0) + inner
        data = struct.pack("<II", 0x80134000, len(root_payload)) + root_payload

        result = scan_bytes(data)
        nodes = list(flatten(result["nodes"]))
        self.assertEqual([node["id"] for node in nodes], [
            "0x80134000", "0x80134001", "0x00134002"
        ])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["padding"][0]["size"], 8)

    def test_rejects_chunk_past_parent_boundary(self):
        data = struct.pack("<II", 0x00134002, 100) + b"short"
        result = scan_bytes(data)
        self.assertEqual(len(result["nodes"]), 0)
        self.assertEqual(len(result["errors"]), 1)


if __name__ == "__main__":
    unittest.main()
