import struct
import unittest

from ps2_dvp_overlay_probe import parse_dvp_overlays


def make_elf(table_payload=None):
    overlay_name = b".DVP.overlay..0x0.12345.44.0\\0"
    section_names = (
        b"\\0.shstrtab\\0.DVP.ovlytab\\0.DVP.ovlystrtab\\0"
        + overlay_name
    )
    name_off = section_names.index(overlay_name)
    overlay_strings = overlay_name
    table_payload = table_payload if table_payload is not None else struct.pack("<III", 0, 0x00100000, 0)
    sections_data = bytearray(52)
    offsets = {}
    for key, payload in (
        ("shstr", section_names),
        ("table", table_payload),
        ("strings", overlay_strings),
        ("overlay", bytes(16)),
    ):
        while len(sections_data) % 4:
            sections_data.append(0)
        offsets[key] = len(sections_data)
        sections_data.extend(payload)
    while len(sections_data) % 4:
        sections_data.append(0)
    shoff = len(sections_data)
    shstr_name = section_names.index(b".shstrtab")
    table_name = section_names.index(b".DVP.ovlytab")
    strings_name = section_names.index(b".DVP.ovlystrtab")
    overlay_shname = name_off
    headers = [
        bytes(40),
        struct.pack("<IIIIIIIIII", shstr_name, 3, 0, 0, offsets["shstr"], len(section_names), 0, 0, 1, 0),
        struct.pack("<IIIIIIIIII", table_name, 0x7FFFF420, 0, 0, offsets["table"], len(table_payload), 3, 0, 4, 12),
        struct.pack("<IIIIIIIIII", strings_name, 3, 0, 0, offsets["strings"], len(overlay_strings), 0, 0, 1, 0),
        struct.pack("<IIIIIIIIII", overlay_shname, 0x7FFFF421, 5, 0, offsets["overlay"], 16, 0, 0, 1, 0),
    ]
    sections_data.extend(b"".join(headers))
    ident = bytes.fromhex("7f454c46010101") + bytes(9)
    header = struct.pack(
        "<16sHHIIIIIHHHHHH",
        ident, 2, 8, 1, 0, 0, shoff, 0, 52, 0, 0, 40, 5, 1
    )
    sections_data[:52] = header
    return bytes(sections_data)


class DvpOverlayProbeTests(unittest.TestCase):
    def test_groups_overlay_from_dvp_table(self):
        report = parse_dvp_overlays(make_elf())
        self.assertEqual(report["table_entries"], 1)
        self.assertEqual(report["errors"], [])
        self.assertEqual(len(report["programs"]), 1)
        program = report["programs"][0]
        self.assertEqual(program["program_id"], "12345")
        self.assertEqual(program["vu_start"], 0)
        self.assertEqual(program["bytes"], 16)
        self.assertTrue(program["contiguous"])

    def test_rejects_table_with_wrong_entry_stride(self):
        with self.assertRaisesRegex(ValueError, "not divisible by 12"):
            parse_dvp_overlays(make_elf(b"bad"))


if __name__ == "__main__":
    unittest.main()
