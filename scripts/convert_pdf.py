#!/usr/bin/env python3
"""Route PDF to Markdown conversion across optional local engines."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from probe_pdf import build_report, engine_status
except Exception:
    build_report = None  # type: ignore
    engine_status = None  # type: ignore


INSTALL_HINTS = {
    "minimal": "python -m pip install pymupdf pymupdf4llm markitdown[pdf] pypdf",
    "docling": "python -m pip install docling",
    "mineru": 'python -m pip install "mineru[all]"',
    "marker": "python -m pip install marker-pdf",
}

_RAPIDOCR_ENGINE = None
_EASYOCR_READER = None


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def parse_pages(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    pages: set[int] = set()
    for part in spec.split(","):
        item = part.strip()
        if not item:
            continue
        if "-" in item:
            start_raw, end_raw = item.split("-", 1)
            start = int(start_raw)
            end = int(end_raw)
            if start < 1 or end < start:
                raise ValueError(f"Invalid page range: {item}")
            pages.update(range(start - 1, end))
        else:
            page = int(item)
            if page < 1:
                raise ValueError(f"Invalid page number: {item}")
            pages.add(page - 1)
    return sorted(pages)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def is_volatile_source(path: Path) -> bool:
    volatile_names = {"temp", "tmp", "rwtemp", "cache"}
    parts = {part.lower() for part in path.parts}
    if parts & volatile_names:
        return True
    path_text = str(path).lower()
    volatile_fragments = [
        "\\appdata\\local\\temp\\",
        "\\temp\\rwtemp\\",
        "\\rwtemp\\",
        "/tmp/",
        "/var/tmp/",
    ]
    return any(fragment in path_text for fragment in volatile_fragments)


def default_output_path(pdf: Path) -> Path:
    if is_volatile_source(pdf):
        return (Path.cwd() / "pdf-to-markdown-output" / f"{pdf.stem}.md").resolve()
    return pdf.with_suffix(".md")


def markdown_ok(text: str) -> bool:
    return bool(text and text.strip())


def resolve_image_path(raw_path: str, markdown_path: Path) -> Path:
    cleaned = raw_path.strip().strip('"').strip("'")
    if cleaned.startswith("file://"):
        cleaned = cleaned[7:]
    path = Path(cleaned)
    if not path.is_absolute():
        path = markdown_path.parent / path
    return path.resolve()


def extract_image_link(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    marker = "]("
    if not stripped.startswith("![") or marker not in stripped or not stripped.endswith(")"):
        return None
    start = stripped.find(marker) + len(marker)
    raw_path = stripped[start:-1]
    return stripped, raw_path


def ocr_with_rapidocr(image_path: Path, min_confidence: float) -> tuple[str, str]:
    from rapidocr_onnxruntime import RapidOCR  # type: ignore

    global _RAPIDOCR_ENGINE
    if _RAPIDOCR_ENGINE is None:
        _RAPIDOCR_ENGINE = RapidOCR()
    result, _ = _RAPIDOCR_ENGINE(str(image_path))
    lines: list[str] = []
    for item in result or []:
        if len(item) < 3:
            continue
        text = str(item[1]).strip()
        try:
            score = float(item[2])
        except Exception:
            score = 0.0
        if text and score >= min_confidence:
            lines.append(text)
    return "\n".join(lines).strip(), "rapidocr"


def ocr_with_easyocr(image_path: Path, min_confidence: float) -> tuple[str, str]:
    import easyocr  # type: ignore

    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        _EASYOCR_READER = easyocr.Reader(["ch_sim", "en"], gpu=False)
    result = _EASYOCR_READER.readtext(str(image_path))
    lines: list[str] = []
    for item in result or []:
        if len(item) < 3:
            continue
        text = str(item[1]).strip()
        try:
            score = float(item[2])
        except Exception:
            score = 0.0
        if text and score >= min_confidence:
            lines.append(text)
    return "\n".join(lines).strip(), "easyocr"


def ocr_with_tesseract(image_path: Path, min_confidence: float) -> tuple[str, str]:
    import pytesseract  # type: ignore

    text = pytesseract.image_to_string(str(image_path), lang="chi_sim+eng")
    return text.strip(), "tesseract"


def ocr_image(image_path: Path, engine: str, min_confidence: float) -> tuple[str, str, str | None]:
    candidates = [engine] if engine != "auto" else ["rapidocr", "tesseract", "easyocr"]
    errors: list[str] = []
    for candidate in candidates:
        try:
            if candidate == "rapidocr" and has_module("rapidocr_onnxruntime"):
                text, used = ocr_with_rapidocr(image_path, min_confidence)
            elif candidate == "tesseract" and has_module("pytesseract") and shutil.which("tesseract"):
                text, used = ocr_with_tesseract(image_path, min_confidence)
            elif candidate == "easyocr" and has_module("easyocr"):
                text, used = ocr_with_easyocr(image_path, min_confidence)
            else:
                errors.append(f"{candidate} unavailable")
                continue
            return text, used, None
        except Exception as exc:
            errors.append(f"{candidate}: {type(exc).__name__}: {exc}")
    return "", "none", "; ".join(errors) if errors else "no OCR engine available"


def format_ocr_text(text: str, image_label: str, pure_text: bool) -> list[str]:
    if not text.strip():
        return [f"[Image OCR: no text recognized in {image_label}]"] if pure_text else []
    header = f"[Image OCR: {image_label}]"
    return [header, text.strip()]


def extract_pdf_images(pdf: Path, image_dir: Path, pages: list[int] | None) -> list[Path]:
    import fitz  # type: ignore

    image_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf))
    page_indexes = pages if pages is not None else list(range(len(doc)))
    extracted: list[Path] = []
    for page_index in page_indexes:
        if page_index >= len(doc):
            continue
        page = doc[page_index]
        for image_index, image in enumerate(page.get_images(full=True)):
            xref = image[0]
            try:
                image_info = doc.extract_image(xref)
            except Exception:
                continue
            ext = image_info.get("ext", "png")
            data = image_info.get("image")
            if not data:
                continue
            target = image_dir / f"{pdf.stem}-page-{page_index + 1}-image-{image_index + 1}.{ext}"
            target.write_bytes(data)
            extracted.append(target)
    doc.close()
    return extracted


def postprocess_image_ocr(
    markdown_path: Path,
    pdf: Path,
    pages: list[int] | None,
    pure_text: bool,
    ocr_engine: str,
    min_confidence: float,
) -> dict:
    original = markdown_path.read_text(encoding="utf-8", errors="replace")
    lines = original.splitlines()
    processed: list[str] = []
    image_refs = 0
    ocr_items: list[dict] = []

    for line in lines:
        link = extract_image_link(line)
        if not link:
            processed.append(line)
            continue
        full_link, raw_path = link
        image_refs += 1
        image_path = resolve_image_path(raw_path, markdown_path)
        if not pure_text:
            processed.append(line)
        if image_path.exists() and ocr_engine != "none":
            text, used_engine, error = ocr_image(image_path, ocr_engine, min_confidence)
        else:
            text, used_engine, error = "", "none", "image not found or OCR disabled"
        label = image_path.name if image_path.name else raw_path
        block = format_ocr_text(text, label, pure_text)
        if block:
            if processed and processed[-1] != "":
                processed.append("")
            processed.extend(block)
            processed.append("")
        ocr_items.append({
            "image": str(image_path),
            "engine": used_engine,
            "chars": len(text),
            "error": error,
        })

    if image_refs == 0 and ocr_engine != "none":
        image_dir = markdown_path.with_suffix("")
        image_dir = image_dir.parent / f"{image_dir.name}_images"
        extracted = extract_pdf_images(pdf, image_dir, pages)
        if extracted:
            if processed and processed[-1] != "":
                processed.append("")
            processed.append("## Extracted Image OCR")
            processed.append("")
        for image_path in extracted:
            text, used_engine, error = ocr_image(image_path, ocr_engine, min_confidence)
            block = format_ocr_text(text, image_path.name, pure_text=True)
            processed.extend(block)
            processed.append("")
            ocr_items.append({
                "image": str(image_path),
                "engine": used_engine,
                "chars": len(text),
                "error": error,
            })

    result = "\n".join(processed).strip() + "\n"
    if pure_text:
        result = "\n".join(line for line in result.splitlines() if not extract_image_link(line)).strip() + "\n"
    write_text(markdown_path, result)
    return {
        "pure_text": pure_text,
        "ocr_engine_requested": ocr_engine,
        "image_links_seen": image_refs,
        "items": ocr_items,
        "output_chars": len(result),
    }


def convert_pymupdf4llm(pdf: Path, output: Path, pages: list[int] | None, images: bool, mode: str) -> tuple[str, list[str]]:
    import pymupdf4llm  # type: ignore

    warnings: list[str] = []
    kwargs = {}
    if pages is not None:
        kwargs["pages"] = pages
    if images:
        image_dir = output.with_suffix("")
        image_dir = image_dir.parent / f"{image_dir.name}_images"
        kwargs.update({"write_images": True, "image_path": str(image_dir), "image_format": "png"})
    if mode in {"ocr", "cjk"}:
        kwargs["force_ocr"] = True
    try:
        md = pymupdf4llm.to_markdown(str(pdf), **kwargs)
    except TypeError as exc:
        warnings.append(f"Retried PyMuPDF4LLM with fewer options after TypeError: {exc}")
        safe_kwargs = {k: v for k, v in kwargs.items() if k in {"pages"}}
        md = pymupdf4llm.to_markdown(str(pdf), **safe_kwargs)
    except Exception as exc:
        if not hasattr(pymupdf4llm, "use_layout"):
            raise
        warnings.append(f"Retried PyMuPDF4LLM in legacy non-layout mode after {type(exc).__name__}: {exc}")
        pymupdf4llm.use_layout(False)
        retry_kwargs = {k: v for k, v in kwargs.items() if k != "force_ocr"}
        md = pymupdf4llm.to_markdown(str(pdf), **retry_kwargs)
    write_text(output, md)
    return md, warnings


def convert_markitdown(pdf: Path, output: Path, pages: list[int] | None, images: bool, mode: str) -> tuple[str, list[str]]:
    from markitdown import MarkItDown  # type: ignore

    warnings: list[str] = []
    if pages is not None:
        warnings.append("MarkItDown engine ignores --pages; converted the full document.")
    if images:
        warnings.append("MarkItDown engine does not export PDF images through this router.")
    md = MarkItDown(enable_plugins=True).convert(str(pdf)).text_content
    write_text(output, md)
    return md, warnings


def convert_docling(pdf: Path, output: Path, pages: list[int] | None, images: bool, mode: str) -> tuple[str, list[str]]:
    from docling.document_converter import DocumentConverter  # type: ignore

    warnings: list[str] = []
    if pages is not None:
        warnings.append("Docling engine ignores --pages in this router; converted the full document.")
    if images:
        warnings.append("Docling Markdown image export is not customized by this router.")
    result = DocumentConverter().convert(str(pdf))
    md = result.document.export_to_markdown()
    write_text(output, md)
    return md, warnings


def convert_pypdf(pdf: Path, output: Path, pages: list[int] | None, images: bool, mode: str) -> tuple[str, list[str]]:
    from pypdf import PdfReader  # type: ignore

    warnings = ["pypdf fallback preserves text only; headings, tables, and images may be poor."]
    if images:
        warnings.append("pypdf fallback cannot export images.")
    reader = PdfReader(str(pdf))
    indexes = pages if pages is not None else list(range(len(reader.pages)))
    parts: list[str] = []
    for index in indexes:
        if index >= len(reader.pages):
            warnings.append(f"Skipped page {index + 1}; document has only {len(reader.pages)} pages.")
            continue
        text = reader.pages[index].extract_text() or ""
        parts.append(f"<!-- page {index + 1} -->\n\n{text.strip()}")
    md = "\n\n".join(parts).strip() + "\n"
    write_text(output, md)
    return md, warnings


def run_cli_engine(command: list[str], output: Path, label: str) -> tuple[str, list[str]]:
    with tempfile.TemporaryDirectory(prefix=f"{label}-pdf-md-") as tmp:
        command = [part.replace("{tmp}", tmp) for part in command]
        proc = subprocess.run(command, text=True, capture_output=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"{label} failed with exit {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}")
        tmp_path = Path(tmp)
        md_files = sorted(tmp_path.rglob("*.md"), key=lambda p: p.stat().st_size, reverse=True)
        if not md_files:
            raise RuntimeError(f"{label} completed but produced no Markdown file.")
        md = md_files[0].read_text(encoding="utf-8", errors="replace")
        write_text(output, md)
        warnings = []
        if proc.stderr.strip():
            warnings.append(proc.stderr.strip()[:1000])
        return md, warnings


def convert_mineru(pdf: Path, output: Path, pages: list[int] | None, images: bool, mode: str) -> tuple[str, list[str]]:
    warnings = []
    if pages is not None:
        warnings.append("MinerU engine ignores --pages in this router; converted the full document.")
    command = ["mineru", "-p", str(pdf), "-o", "{tmp}", "-b", "pipeline"]
    md, run_warnings = run_cli_engine(command, output, "mineru")
    return md, warnings + run_warnings


def convert_marker(pdf: Path, output: Path, pages: list[int] | None, images: bool, mode: str) -> tuple[str, list[str]]:
    warnings = []
    if pages is not None:
        page_spec = ",".join(str(page) for page in pages)
        warnings.append("Marker page selection uses zero-based page indexes.")
    command = ["marker_single", str(pdf), "--output_format", "markdown", "--output_dir", "{tmp}"]
    if pages is not None:
        command.extend(["--page_range", page_spec])
    if mode in {"ocr", "cjk"}:
        command.append("--force_ocr")
    if not images:
        command.append("--disable_image_extraction")
    md, run_warnings = run_cli_engine(command, output, "marker")
    return md, warnings + run_warnings


EngineFunc = Callable[[Path, Path, list[int] | None, bool, str], tuple[str, list[str]]]


ENGINE_FUNCS: dict[str, EngineFunc] = {
    "pymupdf4llm": convert_pymupdf4llm,
    "markitdown": convert_markitdown,
    "docling": convert_docling,
    "marker": convert_marker,
    "mineru": convert_mineru,
    "pypdf": convert_pypdf,
}


def available() -> dict[str, bool]:
    return {
        "pymupdf4llm": has_module("pymupdf4llm"),
        "markitdown": has_module("markitdown"),
        "docling": has_module("docling"),
        "marker": bool(shutil.which("marker_single")),
        "mineru": bool(shutil.which("mineru")),
        "pypdf": has_module("pypdf"),
        "ocr_rapidocr": has_module("rapidocr_onnxruntime"),
        "ocr_tesseract": has_module("pytesseract") and bool(shutil.which("tesseract")),
        "ocr_easyocr": has_module("easyocr"),
    }


def route_for_mode(mode: str, probe: dict | None, engines: dict[str, bool]) -> list[str]:
    routes = {
        "fast": ["pymupdf4llm", "markitdown", "pypdf", "docling"],
        "accurate": ["docling", "marker", "pymupdf4llm", "markitdown", "pypdf"],
        "ocr": ["mineru", "marker", "docling", "pymupdf4llm", "markitdown", "pypdf"],
        "cjk": ["mineru", "docling", "marker", "pymupdf4llm", "markitdown", "pypdf"],
    }
    if mode != "auto":
        return routes[mode]
    if probe and (probe.get("likely_cjk") or probe.get("likely_scanned")):
        return routes["cjk"]
    if probe and (probe.get("image_density") or 0) >= 1.5:
        return routes["accurate"]
    return ["pymupdf4llm", "markitdown", "docling", "marker", "mineru", "pypdf"]


def install_hint(mode: str, probe: dict | None) -> str:
    if mode in {"ocr", "cjk"} or (probe and (probe.get("likely_cjk") or probe.get("likely_scanned"))):
        return INSTALL_HINTS["mineru"]
    if mode == "accurate":
        return INSTALL_HINTS["docling"]
    return INSTALL_HINTS["minimal"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a PDF to clean Markdown using the best installed engine.")
    parser.add_argument("pdf", help="Input PDF path")
    parser.add_argument("--output", "-o", help="Output Markdown path")
    parser.add_argument("--mode", choices=["auto", "fast", "accurate", "ocr", "cjk"], default="auto")
    parser.add_argument("--pages", help="1-based pages or ranges, e.g. 1-3,7")
    parser.add_argument("--images", action="store_true", help="Request image export when the engine supports it")
    parser.add_argument("--ocr-images", action="store_true", help="OCR embedded or exported images and add recognized text")
    parser.add_argument("--pure-text", action="store_true", help="Produce text-only Markdown; implies --ocr-images and removes image links")
    parser.add_argument("--ocr-engine", choices=["auto", "rapidocr", "tesseract", "easyocr", "none"], default="auto")
    parser.add_argument("--ocr-min-confidence", type=float, default=0.45, help="Minimum OCR confidence for engines that expose scores")
    parser.add_argument("--report", help="Output JSON report path")
    parser.add_argument("--keep-going", action="store_true", default=True, help="Try fallback engines on failure")
    args = parser.parse_args()

    pdf = Path(args.pdf).expanduser().resolve()
    if not pdf.exists():
        print(f"PDF not found: {pdf}", file=sys.stderr)
        return 2
    output = Path(args.output).expanduser().resolve() if args.output else default_output_path(pdf)
    report_path = Path(args.report).expanduser().resolve() if args.report else output.with_suffix(".conversion-report.json")
    pages = parse_pages(args.pages)
    engines = available()
    probe = build_report(pdf, 5) if build_report else None
    route = route_for_mode(args.mode, probe, engines)
    extract_images = args.images or args.ocr_images or args.pure_text
    attempts: list[dict] = []
    selected = None
    final_warnings: list[str] = []

    for engine in route:
        if not engines.get(engine):
            attempts.append({"engine": engine, "status": "unavailable"})
            continue
        try:
            md, warnings = ENGINE_FUNCS[engine](pdf, output, pages, extract_images, args.mode)
            if markdown_ok(md):
                selected = engine
                final_warnings.extend(warnings)
                attempts.append({"engine": engine, "status": "ok", "chars": len(md), "warnings": warnings})
                break
            attempts.append({"engine": engine, "status": "empty_output", "warnings": warnings})
        except Exception as exc:
            attempts.append({"engine": engine, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
            if not args.keep_going:
                break

    image_ocr_report = None
    if selected and (args.ocr_images or args.pure_text):
        image_ocr_report = postprocess_image_ocr(
            output,
            pdf,
            pages,
            pure_text=args.pure_text,
            ocr_engine=args.ocr_engine,
            min_confidence=max(0.0, min(1.0, args.ocr_min_confidence)),
        )

    report = {
        "input": str(pdf),
        "output": str(output),
        "mode": args.mode,
        "source_was_volatile": is_volatile_source(pdf),
        "selected_engine": selected,
        "available_engines": engines,
        "route": route,
        "attempts": attempts,
        "warnings": final_warnings,
        "probe": probe,
        "image_ocr": image_ocr_report,
    }
    write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))

    if not selected:
        print("No available engine produced Markdown.", file=sys.stderr)
        print(f"Report: {report_path}", file=sys.stderr)
        print(f"Suggested install: {install_hint(args.mode, probe)}", file=sys.stderr)
        return 1

    print(f"Wrote Markdown: {output}")
    print(f"Engine: {selected}")
    print(f"Report: {report_path}")
    if final_warnings:
        print("Warnings:")
        for warning in final_warnings:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
