import json
import struct
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import declared_checks
import png_pixels
import schema_lite

SCORES_SCHEMA = json.loads((ROOT / "schemas/scores.schema.json").read_text(encoding="utf-8"))
BATCH_SCHEMA = json.loads((ROOT / "schemas/image_batch.schema.json").read_text(encoding="utf-8"))


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def make_png(path: Path, width: int, height: int, rgba, colour_type: int = 6, palette=None) -> None:
    """Encode RGBA rows into a PNG of the requested colour type (filter 0 rows)."""
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            r, g, b, a = rgba(x, y)
            if colour_type == 6:
                raw += bytes((r, g, b, a))
            elif colour_type == 2:
                raw += bytes((r, g, b))
            elif colour_type == 0:
                raw += bytes((g,))
            elif colour_type == 4:
                raw += bytes((g, a))
            else:
                index = palette.index((r, g, b))
                raw += bytes((index,))
    body = b"".join(
        [
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, colour_type, 0, 0, 0)),
            chunk(b"PLTE", palette and b"".join(bytes(c) for c in palette) or b""),
            chunk(b"IDAT", zlib.compress(bytes(raw))),
            chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + body)


class DecoderTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_decodes_rgba_rgb_grey_and_palette(self) -> None:
        def pattern(x, y):
            return (x * 40 % 256, y * 40 % 256, 17, 255)

        palette = [(0, 0, 0), (120, 80, 17)]
        expected = pattern(3, 2)
        for colour_type in (6, 2, 0, 3, 4):
            with self.subTest(colour_type=colour_type):
                target = self.base / f"t{colour_type}.png"
                if colour_type == 3:
                    make_png(target, 8, 8, lambda x, y: (120, 80, 17, 255),
                             colour_type=colour_type, palette=palette)
                else:
                    make_png(target, 8, 8, pattern, colour_type=colour_type)
                width, height, pixels = png_pixels.decode_png(target)
                self.assertEqual((width, height), (8, 8))
                got = png_pixels.rgb_at(width, pixels, 3, 2)
                if colour_type == 3:
                    self.assertEqual(got, (120, 80, 17))
                elif colour_type == 4:
                    self.assertEqual(got, expected[1:2] * 3)
                elif colour_type == 0:
                    grey = expected[1]
                    self.assertEqual(got, (grey, grey, grey))
                else:
                    self.assertEqual(got, expected[:3])

    def test_filter_round_trip(self) -> None:
        """Encode with filters 1-4 applied, decode, and compare against filter-0 truth."""
        width = height = 6
        truth = [bytes((x * 30 % 256, y * 20 % 256, 9, 255)) for y in range(height) for x in range(width)]
        stride = width * 4

        def encode(filt: int) -> bytes:
            raw = bytearray()
            previous = bytearray(stride)
            for y in range(height):
                line = bytearray(b"".join(truth[y * width + x] for x in range(width)))
                coded = bytearray(stride)
                for i in range(stride):
                    a = line[i - 4] if i >= 4 else 0
                    b = previous[i]
                    c = previous[i - 4] if i >= 4 else 0
                    if filt == 1:
                        coded[i] = (line[i] - a) & 0xFF
                    elif filt == 2:
                        coded[i] = (line[i] - b) & 0xFF
                    elif filt == 3:
                        coded[i] = (line[i] - ((a + b) >> 1)) & 0xFF
                    elif filt == 4:
                        p = a + b - c
                        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                        predictor = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                        coded[i] = (line[i] - predictor) & 0xFF
                    else:
                        coded[i] = line[i]
                raw.append(filt)
                raw += coded
                previous = line
            return b"\x89PNG\r\n\x1a\n" + b"".join([
                chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
                chunk(b"IDAT", zlib.compress(bytes(raw))),
                chunk(b"IEND", b""),
            ])

        for filt in (0, 1, 2, 3, 4):
            with self.subTest(filter=filt):
                _width, _height, pixels = png_pixels.decode_png_from_bytes(encode(filt))
                got = [bytes(pixels[i * 4:i * 4 + 4]) for i in range(width * height)]
                self.assertEqual(got, truth)

    def test_unsupported_shapes_fail_closed(self) -> None:
        bad = b"\x89PNG\r\n\x1a\n" + chunk(
            b"IHDR", struct.pack(">IIBBBBB", 4, 4, 16, 6, 0, 0, 0)
        ) + chunk(b"IDAT", zlib.compress(b"\x00" * 64)) + chunk(b"IEND", b"")
        with self.assertRaises(png_pixels.UnsupportedPNGError):
            png_pixels.decode_png_from_bytes(bad)
        truncated = b"\x89PNG\r\n\x1a\n" + chunk(b"IEND", b"")
        with self.assertRaises(png_pixels.UnsupportedPNGError):
            png_pixels.decode_png_from_bytes(truncated)


class DeclaredCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        # white background, deep-emerald square in the middle (25% margins)
        def pattern(x, y):
            inside = 10 <= x <= 21 and 10 <= y <= 23
            return (2, 106, 78, 255) if inside else (255, 255, 255, 255)

        self.white_target = self.base / "white.png"
        make_png(self.white_target, 32, 32, pattern)
        def dark(x, y):
            inside = 10 <= x <= 21 and 10 <= y <= 23
            return (2, 106, 78, 255) if inside else (0, 0, 0, 255)
        self.black_target = self.base / "black.png"
        make_png(self.black_target, 32, 32, dark)

    def test_corner_check_passes_and_fails(self) -> None:
        check = [{"kind": "corner-colour", "r": 255, "g": 255, "b": 255, "tolerance": 10}]
        rows = declared_checks.evaluate_checks(check, self.white_target)
        self.assertTrue(rows[0]["passed"])
        rows = declared_checks.evaluate_checks(check, self.black_target)
        self.assertFalse(rows[0]["passed"])
        self.assertIn("(0, 0, 0)", rows[0]["measured"])
        self.assertIn("255", rows[0]["expected"])

    def test_margin_and_ink_checks(self) -> None:
        margin = [{"kind": "min-margin", "min_ratio": 0.2}]
        self.assertTrue(declared_checks.evaluate_checks(margin, self.white_target)[0]["passed"])
        too_tight = [{"kind": "min-margin", "min_ratio": 0.4}]
        self.assertFalse(declared_checks.evaluate_checks(too_tight, self.white_target)[0]["passed"])
        ink = [{"kind": "ink-colour", "r": 2, "g": 106, "b": 78, "tolerance": 30}]
        self.assertTrue(declared_checks.evaluate_checks(ink, self.white_target)[0]["passed"])
        off = [{"kind": "ink-colour", "r": 200, "g": 150, "b": 40, "tolerance": 30}]
        self.assertFalse(declared_checks.evaluate_checks(off, self.white_target)[0]["passed"])

    def test_declaration_validation_is_closed(self) -> None:
        self.assertIsNone(declared_checks.validate_check(
            {"kind": "corner-colour", "r": 255, "g": 255, "b": 255, "tolerance": 10}
        ))
        for bad in (
            {"kind": "vibes"},
            {"kind": "corner-colour", "r": 300, "g": 0, "b": 0, "tolerance": 10},
            {"kind": "corner-colour", "r": 1, "g": 1, "b": 1, "tolerance": 1, "extra": 2},
            {"kind": "min-margin", "min_ratio": 0.9},
            {"kind": "min-margin"},
            "not an object",
        ):
            with self.subTest(check=bad):
                self.assertIsNotNone(declared_checks.validate_check(bad))


class GateIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.destination = self.base / "out"
        self.destination.mkdir()

    def test_declared_failure_joins_the_deterministic_tier(self) -> None:
        import evaluator

        artifact = self.destination / "dark.png"
        make_png(artifact, 32, 32, lambda x, y: (0, 0, 0, 255))
        receipt = {
            "path": artifact.name,
            "sha256": __import__("hashlib").sha256(artifact.read_bytes()).hexdigest(),
        }

        class Item:
            id = "item-01"
            pixel_checks = ({"kind": "corner-colour", "r": 255, "g": 255, "b": 255, "tolerance": 10},)

        result = evaluator.evaluate_batch(
            batch_id="portrait-study",
            round_number=1,
            items=[Item()],
            receipts={"item-01": receipt},
            destination_dir=self.destination,
            min_dimension=16,
            reject_duplicates=False,
            pass_threshold=0.8,
            advisory_enabled=True,
            require_human_labels=False,
            advisory={"item-01": {"score": 0.95, "reason": "flawless", "dimensions": [
                {"name": "composition", "score": 0.95, "evidence": "centred"},
            ]}},
        )
        row = result.scores["deterministic_gates"]["per_item"][0]
        self.assertFalse(row["passed"])
        self.assertIn("failed_pixel_check", row["failures"])
        self.assertEqual(row["pixel_checks"][0]["measured"], "worst corner RGB (0, 0, 0)")
        self.assertEqual(result.scores["decision"], "fail",
                         "a declared pixel check outranks a perfect advisory")
        self.assertEqual(schema_lite.validate(result.scores, SCORES_SCHEMA), [])

    def test_undeclared_items_stay_untouched(self) -> None:
        import evaluator

        artifact = self.destination / "dark.png"
        make_png(artifact, 32, 32, lambda x, y: (0, 0, 0, 255))
        receipt = {
            "path": artifact.name,
            "sha256": __import__("hashlib").sha256(artifact.read_bytes()).hexdigest(),
        }

        class Item:
            id = "item-01"
            pixel_checks = ()

        result = evaluator.evaluate_batch(
            batch_id="portrait-study",
            round_number=1,
            items=[Item()],
            receipts={"item-01": receipt},
            destination_dir=self.destination,
            min_dimension=16,
            reject_duplicates=False,
            pass_threshold=0.8,
            advisory_enabled=False,
            require_human_labels=False,
        )
        row = result.scores["deterministic_gates"]["per_item"][0]
        self.assertTrue(row["passed"])
        self.assertNotIn("pixel_checks", row)
        self.assertEqual(result.scores["decision"], "pass")

    def test_schema_versions_are_current(self) -> None:
        self.assertEqual(BATCH_SCHEMA["properties"]["schema_version"]["const"], "1.6.0")
        self.assertEqual(SCORES_SCHEMA["properties"]["schema_version"]["const"], "1.4.0")


if __name__ == "__main__":
    unittest.main()
