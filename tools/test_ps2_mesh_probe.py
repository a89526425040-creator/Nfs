import struct
import tempfile
import unittest
from pathlib import Path

from ps2_mesh_probe import probe_leaf


class Ps2MeshProbeTests(unittest.TestCase):
    def test_reads_bounded_numeric_prefix_and_stride_candidates(self):
        payload = bytes.fromhex("0000803F 00000040") + b"\x00" * 8
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resource = root / "resource.bin"
            resource.write_bytes(struct.pack("<II", 0x00134A02, len(payload)) + payload)
            data = resource.read_bytes()
            result = probe_leaf(data, {
                "offset": 0, "size": len(payload), "id": "0x00134A02"
            })
        self.assertEqual(result["payload_size"], 16)
        self.assertEqual(result["first_f32_candidates"][0]["value"], 1.0)
        self.assertEqual(result["first_f32_candidates"][1]["value"], 2.0)


if __name__ == "__main__":
    unittest.main()
