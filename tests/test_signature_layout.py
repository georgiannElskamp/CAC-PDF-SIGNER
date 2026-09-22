"""Signature appearance sizing and rotation tests."""

import io
import unittest

from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from signature_layout import ASCENT, DESCENT, signature_layout, text_width
from signing import sign_bytes
import test_signature_core


class SignatureLayoutTests(unittest.TestCase):
    def test_larger_rectangles_produce_proportionally_larger_type(self):
        details = "Digitally signed by Alex Example\nDate: 2026-09-21 13:45:00 -0500\nDoD ID: 0000000000"
        small = signature_layout(240, 60, "Alex Example", details)
        large = signature_layout(480, 120, "Alex Example", details)
        self.assertGreater(small[0].font_size, small[1].font_size)
        for first, second in zip(small, large):
            self.assertAlmostEqual(second.font_size, 2 * first.font_size, places=5)
            self.assertEqual(second.lines, first.lines)

    def test_every_line_fits_real_font_metrics_across_shapes(self):
        for name in (
            "Alex Example",
            "ALEXANDRA MONTGOMERY-EXAMPLE",
            "José Muñoz",
            "WILLIAM III",
        ):
            details = f"Digitally signed by {name}\nRank: Lt Col\nDate: 2026-09-21 13:45:00 -0500\nDoD ID: 0000000000"
            for width, height in (
                (370, 24),
                (280, 70),
                (120, 120),
                (75, 180),
                (100, 25),
                (20, 12),
            ):
                with self.subTest(name=name, size=(width, height)):
                    blocks = signature_layout(width, height, name, details)
                    for block in blocks:
                        for index, line in enumerate(block.lines):
                            baseline = block.first_baseline - index * block.leading
                            actual_width = stringWidth(
                                line, "Helvetica", block.font_size
                            )
                            self.assertAlmostEqual(
                                text_width(line, block.font_size),
                                actual_width,
                                places=5,
                            )
                            self.assertGreaterEqual(block.x, 0)
                            self.assertLessEqual(block.x + actual_width, width)
                            self.assertGreaterEqual(
                                baseline - DESCENT * block.font_size, 0
                            )
                            self.assertLessEqual(
                                baseline + ASCENT * block.font_size, height
                            )
                    self.assertEqual(
                        "".join(blocks[0].lines).replace(" ", ""), name.replace(" ", "")
                    )
                    self.assertEqual(
                        " ".join(blocks[1].lines), " ".join(details.split())
                    )
                    if width / height >= 1.45:
                        right_edge = blocks[0].x + max(
                            text_width(line, blocks[0].font_size)
                            for line in blocks[0].lines
                        )
                        self.assertLess(right_edge, blocks[1].x)
                    else:
                        name_bottom = (
                            blocks[0].first_baseline
                            - (len(blocks[0].lines) - 1) * blocks[0].leading
                            - DESCENT * blocks[0].font_size
                        )
                        detail_top = (
                            blocks[1].first_baseline + ASCENT * blocks[1].font_size
                        )
                        self.assertGreater(name_bottom, detail_top)

    def test_standard_font_does_not_silently_replace_unsupported_characters(self):
        with self.assertRaisesRegex(ValueError, "cannot display"):
            signature_layout(280, 70, "Example \u4e2d", "Digitally signed by Example")

    def test_unicode_certificate_names_use_embedded_fonts_and_preserve_integrity(self):
        for name in ("Łukasz Example", "Αλέξης Example", "Александр Example", "陳 小明"):
            with self.subTest(name=name):
                class Fixture(test_signature_core.SignatureTests):
                    common_name = name
                Fixture.setUpClass()
                signed = sign_bytes(Fixture.pdf, Fixture.signer, {"field": "First"})
                reader = PdfFileReader(io.BytesIO(signed))
                appearance = reader.embedded_signatures[0].sig_field["/AP"]["/N"]
                fonts = appearance["/Resources"]["/Font"]
                self.assertTrue(any(font.get_object()["/Subtype"] == "/Type0" for font in fonts.values()))
                self.assertIn(b"/ActualText", appearance.data)
                self.assertTrue(signed.startswith(Fixture.pdf))

    def test_rotated_fields_remain_signed_and_upright(self):
        Fixtures = test_signature_core.SignatureTests
        Fixtures.setUpClass()
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                writer = IncrementalPdfFileWriter(io.BytesIO(Fixtures.pdf))
                page_ref, _ = writer.find_page_for_modification(0)
                page_ref.get_object()[generic.pdf_name("/Rotate")] = (
                    generic.NumberObject(rotation)
                )
                writer.mark_update(page_ref)
                output = io.BytesIO()
                writer.write(output)
                original = output.getvalue()
                signed = sign_bytes(original, Fixtures.signer, {"field": "First"})
                self.assertTrue(signed.startswith(original))
                reader = PdfFileReader(io.BytesIO(signed))
                appearance = reader.embedded_signatures[0].sig_field["/AP"]["/N"]
                self.assertIn(b"/SignatureFont", appearance.data)
                self.assertIn(b"Digitally", appearance.data)
                self.assertIn(b"0000000000", appearance.data)
                box = tuple(appearance["/BBox"])
                self.assertEqual(
                    box, (0, 370, 98, 0) if rotation in (90, 270) else (0, 98, 370, 0)
                )
                if rotation:
                    self.assertIn("/Matrix", appearance)


if __name__ == "__main__":
    unittest.main()
