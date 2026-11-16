import csv
import tempfile
import unittest
from pathlib import Path

from ps2_texture_probe import inspect_texture_resources, inspect_image_headers


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


def make_bmp(width=64, height=32, bpp=24):
    pixel_offset = 54
    row_bytes = ((width * bpp + 31) // 32) * 4
    image_size = row_bytes * height
    total = pixel_offset + image_size
    return (b'BM' + total.to_bytes(4, 'little') + bytes(4) + pixel_offset.to_bytes(4, 'little')
            + (40).to_bytes(4, 'little') + width.to_bytes(4, 'little', signed=True)
            + height.to_bytes(4, 'little', signed=True) + (1).to_bytes(2, 'little')
            + bpp.to_bytes(2, 'little') + bytes(4) + image_size.to_bytes(4, 'little')
            + bytes(16) + bytes(image_size))


def make_jpeg(width=320, height=200):
    app = bytes.fromhex('FF E0 00 04 41 42')
    components = bytes([1, 0x11, 0, 2, 0x11, 0, 3, 0x11, 0])
    sof = (bytes.fromhex('FF C0') + (17).to_bytes(2, 'big') + bytes([8])
           + height.to_bytes(2, 'big') + width.to_bytes(2, 'big') + bytes([3]) + components)
    return bytes.fromhex('FF D8') + app + sof + bytes.fromhex('FF D9')


class EmbeddedImageHeaderTests(unittest.TestCase):
    def test_bmp_dimensions_and_layout(self):
        result = inspect_image_headers(b'prefix' + make_bmp())
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0]['width'], result[0]['height']), (64, 32))
        self.assertEqual(result[0]['bits_per_pixel'], 24)
        self.assertEqual(result[0]['offset'], 6)

    def test_jpeg_sof_dimensions(self):
        result = inspect_image_headers(make_jpeg())
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0]['width'], result[0]['height']), (320, 200))
        self.assertEqual(result[0]['components'], 3)

    def test_false_bmp_signature_is_rejected(self):
        self.assertEqual(inspect_image_headers(b'BM' + bytes(80)), [])

    def test_multiple_images_are_ordered(self):
        result = inspect_image_headers(make_jpeg() + b'gap' + make_bmp(8, 8))
        self.assertEqual([x['format'] for x in result], ['JPEG', 'BMP'])
        self.assertEqual([x['offset'] for x in result], sorted(x['offset'] for x in result))


if __name__ == "__main__":
    unittest.main()
