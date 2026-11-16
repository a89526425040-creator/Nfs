import unittest

from ps2_vif_probe import parse_vif_stream


class Ps2VifProbeTests(unittest.TestCase):
    def test_parses_unpack_commands_and_payload_lengths(self):
        data = (
            bytes.fromhex("0080016E 0B020700")
            + bytes.fromhex("01C0016C")
            + bytes(16)
            + bytes.fromhex("02C00268")
            + bytes(24)
        )
        result = parse_vif_stream(data)
        self.assertEqual(result["command_count"], 3)
        self.assertEqual(result["unpack_vector_count"], 4)
        self.assertEqual(result["unpack_data_bytes"], 44)
        self.assertEqual(result["padding_bytes"], 0)
        self.assertEqual(result["consumed_bytes"], len(data))
        self.assertEqual(result["unpack_format_counts"], {
            "0x8": 1, "0xC": 1, "0xE": 1
        })

    def test_rejects_zero_direct_count_when_payload_is_absent(self):
        with self.assertRaisesRegex(ValueError, "needs 1048576 data bytes"):
            parse_vif_stream(bytes.fromhex("00000050"))

    def test_v3_16_vectors_are_packed_before_word_alignment(self):
        data = bytes.fromhex("0B800369") + bytes([0x22]) * 18 + b"\x00\x00" + bytes(4)
        result = parse_vif_stream(data)
        self.assertEqual(result["command_count"], 2)
        self.assertEqual(result["unpack_data_bytes"], 20)
        self.assertEqual(result["command_counts"], {"NOP": 1, "UNPACK_3x16": 1})

    def test_preserves_0x11_inside_vif_command_immediate(self):
        data = bytes.fromhex("11800361") + bytes(8) + bytes(4)
        result = parse_vif_stream(data)
        self.assertEqual(result["command_count"], 2)
        self.assertEqual(result["command_counts"], {"NOP": 1, "UNPACK_1x16": 1})


if __name__ == "__main__":
    unittest.main()
