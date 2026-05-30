---
name: pdf-to-markdown-pro
description: Convert PDFs into clean Markdown for Claude Code, Codex, and other coding agents. Use when asked to read, load, analyze, summarize, OCR, extract, or convert PDF files, especially when preserving headings, tables, images, formulas, reading order, CJK text, or fallback behavior matters.
---

# PDF to Markdown Pro

## Overview

Convert PDF files to agent-friendly Markdown before analysis. Prefer the bundled `scripts/convert_pdf.py` router instead of asking the agent to read a binary PDF directly.

The router is lightweight: it does not require all engines up front. It detects installed tools and chooses the fastest reliable path, with fallbacks.

## Quick Start

Run from this skill directory:

```bash
python scripts/convert_pdf.py "/path/to/file.pdf"
```

Common options:

```bash
python scripts/convert_pdf.py "/path/to/file.pdf" --output "/path/to/file.md"
python scripts/convert_pdf.py "/path/to/file.pdf" --mode fast
python scripts/convert_pdf.py "/path/to/file.pdf" --mode accurate --images
python scripts/convert_pdf.py "/path/to/file.pdf" --mode cjk
python scripts/convert_pdf.py "/path/to/file.pdf" --pure-text
python scripts/convert_pdf.py "/path/to/file.pdf" --ocr-images --ocr-engine rapidocr
python scripts/probe_pdf.py "/path/to/file.pdf"
```

After conversion, read the generated `.md` file and use the conversion report for caveats.

Use `--pure-text` when the user wants a Markdown file with no image links. It implies image extraction plus OCR and replaces image links with recognized text blocks. Use `--ocr-images` when image links may remain but recognized image text should be added near them.

If the input PDF is in a volatile temp/cache path such as WeChat `RWTemp` or system `Temp`, the router writes the default Markdown output to `./pdf-to-markdown-output/` under the current working directory. Pass `--output` to choose an explicit stable destination.

## Engine Routing

Use `--mode auto` unless the user asks for a specific tradeoff.

- `fast`: native-text PDFs. Tries PyMuPDF4LLM, MarkItDown, pypdf, then Docling.
- `accurate`: layout, tables, multi-column, document structure. Tries Docling, Marker, PyMuPDF4LLM, MarkItDown, then pypdf.
- `ocr`: scanned or image-heavy PDFs. Tries MinerU, Marker, Docling, PyMuPDF4LLM, MarkItDown, then pypdf.
- `cjk`: Chinese/Japanese/Korean PDFs, scanned papers, formulas, dense tables. Tries MinerU, Docling, Marker, PyMuPDF4LLM, MarkItDown, then pypdf.
- `auto`: probes the PDF, then chooses the `cjk`, `accurate`, or `fast` route based on CJK ratio, image density, and selectable text.

## Dependency Policy

Do not install heavy engines unless the user needs them.

Recommended minimal stack:

```bash
python -m pip install pymupdf pymupdf4llm markitdown[pdf] pypdf
```

Recommended accuracy stack:

```bash
python -m pip install docling
```

Optional CJK/OCR stack:

```bash
python -m pip install "mineru[all]"
```

Optional layout/OCR stack:

```bash
python -m pip install marker-pdf
```

Optional embedded-image OCR stack:

```bash
python -m pip install rapidocr-onnxruntime pillow opencv-python
```

If no conversion engine is installed, report the missing dependency and suggest the smallest install command for the user's PDF type.

## Output Rules

- Prefer writing Markdown next to the source PDF unless `--output` is provided.
- For volatile temp/cache inputs, prefer `./pdf-to-markdown-output/` unless `--output` is provided.
- Preserve image references when `--images` is requested and the selected engine supports it.
- Remove image references and OCR embedded images when `--pure-text` is requested.
- Prefer RapidOCR for local Chinese/English image OCR. Fall back to Tesseract or EasyOCR only when available.
- Keep a JSON conversion report next to the Markdown.
- If the selected engine returns empty text, retry with the next engine.
- If all engines fail, report every attempted engine and the install command most likely to fix the case.

## Resources

- `scripts/probe_pdf.py`: inspect a PDF and list available engines.
- `scripts/convert_pdf.py`: route conversion across installed engines.
- `references/engine-selection.md`: engine tradeoffs and install notes.
