# PDF to Markdown Pro

> A lightweight Claude Code / Codex skill for converting PDFs into clean Markdown, with optional OCR for embedded images and text-only output.

English | [中文](README.zh-CN.md)

## What It Does

`pdf-to-markdown-pro` helps coding agents read PDFs reliably by converting them to Markdown first. It is designed for Claude Code, Codex, and other skill-compatible agents.

Key features:

- Converts PDF files to clean Markdown.
- Automatically routes across installed engines.
- Handles Chinese / English PDFs.
- Extracts embedded images when requested.
- OCRs embedded images into Markdown text.
- Supports pure text output with no image links.
- Avoids writing output into volatile temp paths such as WeChat `RWTemp`.
- Writes a JSON conversion report for debugging.

## Why Use This Skill

Most agents are better at reading Markdown than binary PDF files. This skill gives the agent a stable workflow:

1. Probe the PDF.
2. Pick the best available local conversion engine.
3. Convert the PDF to Markdown.
4. Optionally OCR embedded images.
5. Read the Markdown instead of the PDF.

## Repository Layout

```text
pdf-to-markdown-pro/
  SKILL.md
  agents/
    openai.yaml
  scripts/
    convert_pdf.py
    probe_pdf.py
  references/
    engine-selection.md
```

## Install

### Claude Code

Clone this repository, then copy it into your Claude skills directory:

```powershell
git clone https://github.com/Zhanghaohao666/pdf-to-markdown-pro.git
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills" | Out-Null
Copy-Item -Recurse -Force .\pdf-to-markdown-pro "$env:USERPROFILE\.claude\skills\pdf-to-markdown-pro"
```

Then use it in Claude Code:

```text
Use $pdf-to-markdown-pro to convert this PDF into clean Markdown.
```

### Codex

Clone this repository, then copy it into your Codex skills directory:

```powershell
git clone https://github.com/Zhanghaohao666/pdf-to-markdown-pro.git
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force .\pdf-to-markdown-pro "$env:USERPROFILE\.codex\skills\pdf-to-markdown-pro"
```

Then use it in Codex:

```text
Use $pdf-to-markdown-pro to read this PDF and summarize the key points.
```

## Dependencies

The skill is intentionally lightweight. It only uses engines that are already installed.

Recommended minimal stack:

```bash
python -m pip install pymupdf pymupdf4llm markitdown[pdf] pypdf
```

Embedded image OCR:

```bash
python -m pip install rapidocr-onnxruntime pillow opencv-python
```

More accurate layout parsing:

```bash
python -m pip install docling
```

Optional heavy OCR / CJK parsing:

```bash
python -m pip install "mineru[all]"
```

Optional Marker support:

```bash
python -m pip install marker-pdf
```

## Usage

Run commands from the repository or skill directory.

### Probe a PDF

```bash
python scripts/probe_pdf.py "document.pdf"
```

This reports:

- Page count
- Sampled text amount
- CJK ratio
- Image density
- Available conversion engines
- Suggested route

### Convert a PDF to Markdown

```bash
python scripts/convert_pdf.py "document.pdf"
```

By default, output is written next to the PDF. If the PDF comes from a volatile temp/cache path, output is written to `./pdf-to-markdown-output/` unless `--output` is provided.

### Choose an output path

```bash
python scripts/convert_pdf.py "document.pdf" --output "document.md"
```

### Fast mode

```bash
python scripts/convert_pdf.py "document.pdf" --mode fast
```

Best for native text PDFs.

### Accurate mode

```bash
python scripts/convert_pdf.py "document.pdf" --mode accurate
```

Best for complex tables, multi-column documents, and layout-sensitive PDFs.

### CJK mode

```bash
python scripts/convert_pdf.py "document.pdf" --mode cjk
```

Best for Chinese, Japanese, Korean, academic, and scanned technical documents.

### Export images

```bash
python scripts/convert_pdf.py "document.pdf" --images
```

This keeps Markdown image links when the selected engine supports image export.

### OCR embedded images

```bash
python scripts/convert_pdf.py "document.pdf" --ocr-images --ocr-engine rapidocr
```

This keeps image links and adds recognized text near each image.

### Pure text Markdown

```bash
python scripts/convert_pdf.py "document.pdf" --pure-text --ocr-engine rapidocr
```

This mode:

- Extracts PDF text.
- Extracts embedded images.
- OCRs images into text.
- Removes all Markdown image links.
- Produces text-only Markdown.

Use this when you want a Markdown file that contains only readable text.

### Convert selected pages

```bash
python scripts/convert_pdf.py "document.pdf" --pages 1-3,7
```

Page numbers are 1-based.

## Engine Routing

`--mode auto` is the default.

| Mode | Best for | Route |
|---|---|---|
| `fast` | Native text PDFs | PyMuPDF4LLM, MarkItDown, pypdf |
| `accurate` | Layout, tables, multi-column PDFs | Docling, Marker, PyMuPDF4LLM |
| `ocr` | Scanned or image-heavy PDFs | MinerU, Marker, Docling, PyMuPDF4LLM |
| `cjk` | Chinese/Japanese/Korean PDFs | MinerU, Docling, Marker, PyMuPDF4LLM |
| `auto` | General use | Probes the PDF and chooses a route |

## Reports

Every conversion writes a report:

```text
document.conversion-report.json
```

The report includes:

- Selected engine
- Attempted engines
- Warnings
- Output path
- Probe data
- Image OCR results

Use the report to understand why a fallback engine was used.

## Troubleshooting

### The Markdown is empty

Check the report first. Common causes:

- The PDF is scanned and no OCR engine is installed.
- The input PDF was in a temporary folder that got deleted.
- The chosen engine failed and no fallback succeeded.

For scanned or image-heavy PDFs, try:

```bash
python scripts/convert_pdf.py "document.pdf" --pure-text --ocr-engine rapidocr
```

### The PDF came from WeChat `RWTemp`

WeChat temp directories may be cleaned automatically. The router detects volatile paths and writes default output to:

```text
./pdf-to-markdown-output/
```

For important files, always pass an explicit stable output path:

```bash
python scripts/convert_pdf.py "document.pdf" --output "D:/Documents/document.md" --pure-text
```

### PyMuPDF4LLM ONNX error on Windows

Some Windows environments trigger an ONNXRuntime type error in the new layout path. The script automatically retries PyMuPDF4LLM in legacy non-layout mode.

### Image OCR is slow

Image OCR is slower than native text extraction. For best speed, use `--pure-text` only when image text is actually needed.

## Privacy

The default workflow is local. PDFs are not uploaded anywhere by this skill. If you install and use external cloud-based engines yourself, their own policies apply.

## License

MIT
