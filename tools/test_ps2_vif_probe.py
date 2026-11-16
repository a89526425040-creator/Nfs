import unittest

from ps2_vif_probe import parse_vif_stream


class Ps2VifProbeTests(unittest.TestCase):
    def test_parses_unpack_commands_and_payload_lengths(self):
        data = (
            b"\x11" * 8
            + bytes.fromhex("0080016E 0B020700")
            + bytes.fromhex("01C0016C")
            + bytes(16)
            + bytes.fromhex("02C00268")
            + bytes(24)
        )
        result = parse_vif_stream(data)
        self.assertEqual(result["command_count"], 3)
        self.assertEqual(result["unpack_vector_count"], 4)
        self.assertEqual(result["unpack_data_bytes"], 44)
        self.assertEqual(result["padding_bytes"], 8)
        self.assertEqual(result["consumed_bytes"], len(data))
        self.assertEqual(result["unpack_format_counts"], {
            "0x8": 1, "0xC": 1, "0xE": 1
        })


if __name__ == "__main__":
    unittest.main()
