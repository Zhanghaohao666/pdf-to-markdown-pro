# Engine Selection

## Quick Decision Table

| PDF type | First choice | Fallbacks | Notes |
|---|---|---|---|
| Native text, simple layout | PyMuPDF4LLM | MarkItDown, pypdf | Fastest useful path for most reports and manuals. |
| Mixed Office/PDF inputs | MarkItDown | PyMuPDF4LLM, Docling | Broad format coverage, good for LLM ingestion. |
| Complex tables or multi-column papers | Docling | Marker, PyMuPDF4LLM | Better structure and reading order. |
| Scanned PDF or image-heavy PDF | MinerU | Marker OCR, Docling, PyMuPDF4LLM OCR | OCR quality matters more than speed. |
| Chinese/Japanese/Korean academic PDF | MinerU | Docling, Marker, PyMuPDF4LLM | Prefer MinerU when available. |
| No ML dependencies allowed | PyMuPDF4LLM | MarkItDown, pypdf | Keep output caveats visible. |

## Install Commands

Minimal:

```bash
python -m pip install pymupdf pymupdf4llm markitdown[pdf] pypdf
```

Embedded image OCR:

```bash
python -m pip install rapidocr-onnxruntime pillow opencv-python
```

High accuracy:

```bash
python -m pip install docling
```

OCR/CJK:

```bash
python -m pip install "mineru[all]"
```

Marker:

```bash
python -m pip install marker-pdf
```

## Quality Checks

After conversion, check:

- The Markdown is not empty.
- Page order is readable.
- Tables are not flattened into incoherent lines.
- CJK text is not garbled.
- Images referenced in Markdown exist when image export was requested.
- The JSON report lists the engine and warnings.

If output quality is poor, rerun with `--mode accurate`, `--mode ocr`, or `--mode cjk` based on the source PDF.

For pure text output with image contents converted to text, rerun with:

```bash
python scripts/convert_pdf.py input.pdf --pure-text --ocr-engine rapidocr
```

When the input PDF comes from a volatile path such as WeChat `RWTemp` or system `Temp`, either pass a stable `--output` path or let the router write to `./pdf-to-markdown-output/` in the current working directory.
