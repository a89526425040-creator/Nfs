import struct
import unittest

from ps2_tpk_probe import DATA, HEADER, INDEX, INFO, ROOT, STREAM, VRAM_DATA, VRAM_HEADER, parse_tpk


def chunk(chunk_id, payload):
    return struct.pack("<II", chunk_id, len(payload)) + payload


def make_tpk():
    name_hash = 0x1234ABCD
    texture_header = bytearray(0x7C)
    struct.pack_into("<I", texture_header, 0, 5)
    texture_header[4:15] = b"CARTEXTURES"
    texture_header[0x20:0x27] = b"car.tpk"
    struct.pack_into("<I", texture_header, 0x60, 0x87654321)

    index_chunk = chunk(INDEX, struct.pack("<II", name_hash, 0))
    stream_placeholder = struct.pack("<IIiiBBHI", name_hash, 0, 16, 32, 0, 1, 0, 0)
    info_children = (
        chunk(HEADER, bytes(texture_header))
        + index_chunk
        + chunk(STREAM, stream_placeholder)
    )
    info_chunk = chunk(INFO, info_children)

    pad = chunk(0, bytes(0x30))
    jdlz = b"JDLZ" + bytes([2, 0x10]) + struct.pack("<HII", 0, 32, 16)
    vram_header = chunk(VRAM_HEADER, bytes(0x18))
    vram_data_size = 0x78 + len(jdlz)
    b332_header_offset = 8 + len(pad) + len(info_chunk)
    vram_data_payload_offset = b332_header_offset + 8 + len(vram_header) + 8
    blob_offset = vram_data_payload_offset + 0x78

    stream = struct.pack("<IIiiBBHI", name_hash, blob_offset, len(jdlz), 32, 0, 1, 0, 0)
    info_children = (
        chunk(HEADER, bytes(texture_header))
        + index_chunk
        + chunk(STREAM, stream)
    )
    info_chunk = chunk(INFO, info_children)
    vram_data = chunk(VRAM_DATA, bytes([0x11]) * 0x78 + jdlz)
    b332_chunk = chunk(DATA, vram_header + vram_data)
    return chunk(ROOT, pad + info_chunk + b332_chunk)


class TpkProbeTests(unittest.TestCase):
    def test_parses_nested_streaming_tpk_and_jdlz_entry(self):
        report = parse_tpk(make_tpk())
        self.assertEqual(report["header"]["version"], 5)
        self.assertEqual(report["header"]["name"], "CARTEXTURES")
        self.assertEqual(report["header"]["filename"], "car.tpk")
        self.assertEqual(report["index_count"], 1)
        self.assertEqual(report["stream_count"], 1)
        self.assertEqual(report["blob_checks"][0]["blob_magic"], "JDLZ")
        self.assertTrue(report["blob_checks"][0]["index_hash_matches"])
        self.assertEqual(report["blob_checks"][0]["compression_header"]["uncompressed_bytes"], 32)
        self.assertEqual(report["stream_entries"][0]["descriptor_word_4"], 0x100)
        self.assertEqual(report["stream_entries"][0]["descriptor_word_5"], 0)
        self.assertEqual(report["errors"], [])

    def test_rejects_non_tpk_root(self):
        with self.assertRaisesRegex(ValueError, "expected B3300000"):
            parse_tpk(chunk(0x12345678, b""))

    def test_rejects_root_past_end_of_file(self):
        with self.assertRaisesRegex(ValueError, "root ends"):
            parse_tpk(struct.pack("<II", ROOT, 100) + bytes(8))


if __name__ == "__main__":
    unittest.main()
