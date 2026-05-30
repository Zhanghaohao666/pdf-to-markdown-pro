import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import convert_pdf as c  # noqa: E402
import probe_pdf as p  # noqa: E402


def _has(mod: str) -> bool:
    return importlib.util.find_spec(mod) is not None


class ParsePagesTests(unittest.TestCase):
    def test_basic_and_ranges(self):
        self.assertIsNone(c.parse_pages(None))
        self.assertIsNone(c.parse_pages(""))
        self.assertEqual(c.parse_pages("1-3,7"), [0, 1, 2, 6])
        self.assertEqual(c.parse_pages("2,2,1"), [0, 1])  # dedup + sort

    def test_friendly_errors(self):
        with self.assertRaisesRegex(ValueError, "Invalid page number"):
            c.parse_pages("a")
        with self.assertRaisesRegex(ValueError, "Invalid page range"):
            c.parse_pages("1-b")
        with self.assertRaisesRegex(ValueError, "Invalid page range"):
            c.parse_pages("5-3")


class VolatileSourceTests(unittest.TestCase):
    def test_volatile_and_normal(self):
        self.assertTrue(c.is_volatile_source(Path("/tmp/x/doc.pdf")))
        self.assertFalse(c.is_volatile_source(Path("/home/user/docs/doc.pdf")))


class ImageLinkTests(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(c.extract_image_link("![a](img.png)"), ("![a](img.png)", "img.png"))
        self.assertIsNone(c.extract_image_link("plain text"))

    def test_resolve_relative(self):
        self.assertEqual(c.resolve_image_path("imgs/a.png", Path("/docs/out.md")), Path("/docs/imgs/a.png"))


class FormatOcrTests(unittest.TestCase):
    def test_blockquote_preserves_lines(self):
        block = c.format_ocr_text("line1\nline2", "fig.png", pure_text=False)
        self.assertEqual(block[0], "> *[Image OCR] fig.png*")
        self.assertIn("> line1", block)
        self.assertIn("> line2", block)

    def test_empty(self):
        self.assertEqual(c.format_ocr_text("", "fig.png", pure_text=False), [])
        self.assertTrue(c.format_ocr_text("", "fig.png", pure_text=True))


class PersistAssetsTests(unittest.TestCase):
    def test_copies_and_rewrites_relative_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "engine_out"
            (src / "images").mkdir(parents=True)
            (src / "images" / "f.png").write_bytes(b"PNG")
            out = root / "result.md"
            md = "![](images/f.png)\n![](http://x/y.png)\n"
            new_md = c.persist_cli_assets(md, src, out)
            self.assertIn("result_images/images/f.png", new_md)
            self.assertIn("http://x/y.png", new_md)  # remote link untouched
            self.assertTrue((root / "result_images" / "images" / "f.png").is_file())


class RouteTests(unittest.TestCase):
    def test_explicit_modes(self):
        self.assertEqual(c.route_for_mode("fast", None)[0], "pymupdf4llm")
        self.assertEqual(c.route_for_mode("cjk", None)[0], "mineru")

    def test_auto_cjk(self):
        self.assertEqual(c.route_for_mode("auto", {"likely_cjk": True})[0], "mineru")


class ProbeTests(unittest.TestCase):
    def test_count_cjk(self):
        self.assertEqual(p.count_cjk("abc"), 0)
        self.assertGreaterEqual(p.count_cjk("中文"), 2)


@unittest.skipUnless(_has("fitz") and _has("pymupdf4llm"), "needs pymupdf + pymupdf4llm")
class EndToEndTests(unittest.TestCase):
    def test_convert_pymupdf4llm(self):
        import fitz  # type: ignore

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "t.pdf"
            doc = fitz.open()
            doc.new_page().insert_text((72, 72), "Hello world from a test PDF.")
            doc.save(str(pdf))
            doc.close()
            out = root / "t.md"
            md, _ = c.convert_pymupdf4llm(pdf, out, None, False, "fast")
            self.assertTrue(c.markdown_ok(md))
            self.assertTrue(out.is_file())


if __name__ == "__main__":
    unittest.main()
