#!/usr/bin/env python3
"""Inspect a PDF and report conversion hints for pdf-to-markdown-pro."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path


PY_ENGINES = {
    "pymupdf": "fitz",
    "pymupdf4llm": "pymupdf4llm",
    "markitdown": "markitdown",
    "docling": "docling",
    "pypdf": "pypdf",
    "marker": "marker",
}

CLI_ENGINES = {
    "mineru": "mineru",
    "marker_single": "marker_single",
}


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def engine_status() -> dict[str, bool | str | None]:
    status: dict[str, bool | str | None] = {}
    for label, module in PY_ENGINES.items():
        status[label] = has_module(module)
    for label, command in CLI_ENGINES.items():
        status[label] = bool(shutil.which(command))
    return status


def count_cjk(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff" or "\uac00" <= ch <= "\ud7af")


def inspect_with_pymupdf(path: Path, max_pages: int) -> dict:
    import fitz  # type: ignore

    doc = fitz.open(str(path))
    sampled_pages = min(len(doc), max_pages)
    text_chars = 0
    cjk_chars = 0
    image_count = 0
    drawings_count = 0
    samples: list[str] = []
    for index in range(sampled_pages):
        page = doc[index]
        text = page.get_text("text") or ""
        text_chars += len(text.strip())
        cjk_chars += count_cjk(text)
        image_count += len(page.get_images(full=True))
        try:
            drawings_count += len(page.get_drawings())
        except Exception:
            pass
        if text and len("".join(samples)) < 2000:
            samples.append(text[:500])
    metadata = dict(doc.metadata or {})
    page_count = len(doc)
    doc.close()
    avg_text_chars = int(text_chars / sampled_pages) if sampled_pages else 0
    cjk_ratio = (cjk_chars / text_chars) if text_chars else 0.0
    image_density = (image_count / sampled_pages) if sampled_pages else 0.0
    return {
        "backend": "pymupdf",
        "page_count": page_count,
        "sampled_pages": sampled_pages,
        "text_chars_sampled": text_chars,
        "avg_text_chars_per_sampled_page": avg_text_chars,
        "cjk_ratio": round(cjk_ratio, 4),
        "image_count_sampled": image_count,
        "image_density": round(image_density, 4),
        "drawings_count_sampled": drawings_count,
        "metadata": metadata,
        "likely_scanned": avg_text_chars < 30 and image_density >= 0.8,
        "likely_cjk": cjk_ratio >= 0.15,
        "sample_text": "\n".join(samples)[:2000],
    }


def inspect_with_pypdf(path: Path, max_pages: int) -> dict:
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(str(path))
    sampled_pages = min(len(reader.pages), max_pages)
    text_chars = 0
    cjk_chars = 0
    samples: list[str] = []
    for index in range(sampled_pages):
        text = reader.pages[index].extract_text() or ""
        text_chars += len(text.strip())
        cjk_chars += count_cjk(text)
        if text and len("".join(samples)) < 2000:
            samples.append(text[:500])
    avg_text_chars = int(text_chars / sampled_pages) if sampled_pages else 0
    cjk_ratio = (cjk_chars / text_chars) if text_chars else 0.0
    return {
        "backend": "pypdf",
        "page_count": len(reader.pages),
        "sampled_pages": sampled_pages,
        "text_chars_sampled": text_chars,
        "avg_text_chars_per_sampled_page": avg_text_chars,
        "cjk_ratio": round(cjk_ratio, 4),
        "image_count_sampled": None,
        "image_density": None,
        "drawings_count_sampled": None,
        "metadata": {},
        "likely_scanned": avg_text_chars < 30,
        "likely_cjk": cjk_ratio >= 0.15,
        "sample_text": "\n".join(samples)[:2000],
    }


def choose_hint(info: dict, engines: dict[str, bool | str | None]) -> str:
    if info.get("likely_cjk") or info.get("likely_scanned"):
        if engines.get("mineru"):
            return "cjk_or_ocr_mineru"
        if engines.get("docling"):
            return "cjk_or_ocr_docling"
        if engines.get("marker") or engines.get("marker_single"):
            return "cjk_or_ocr_marker"
    if engines.get("pymupdf4llm"):
        return "fast_pymupdf4llm"
    if engines.get("markitdown"):
        return "fast_markitdown"
    if engines.get("docling"):
        return "accurate_docling"
    if engines.get("pypdf"):
        return "basic_pypdf"
    return "install_minimal_stack"


def build_report(path: Path, max_pages: int) -> dict:
    engines = engine_status()
    base = {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else None,
        "available_engines": engines,
    }
    if not path.exists():
        base["error"] = "PDF not found"
        return base
    try:
        if engines.get("pymupdf"):
            detail = inspect_with_pymupdf(path, max_pages)
        elif engines.get("pypdf"):
            detail = inspect_with_pypdf(path, max_pages)
        else:
            detail = {
                "backend": None,
                "page_count": None,
                "sampled_pages": 0,
                "text_chars_sampled": None,
                "avg_text_chars_per_sampled_page": None,
                "cjk_ratio": None,
                "image_count_sampled": None,
                "image_density": None,
                "drawings_count_sampled": None,
                "metadata": {},
                "likely_scanned": None,
                "likely_cjk": None,
                "sample_text": "",
            }
        base.update(detail)
        base["route_hint"] = choose_hint(base, engines)
    except Exception as exc:
        base["error"] = f"{type(exc).__name__}: {exc}"
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe a PDF and list available conversion engines.")
    parser.add_argument("pdf", help="Path to PDF")
    parser.add_argument("--max-pages", type=int, default=5, help="Pages to sample")
    parser.add_argument("--no-sample", action="store_true", help="Omit sample text from output")
    args = parser.parse_args()

    report = build_report(Path(args.pdf).expanduser().resolve(), max(1, args.max_pages))
    if args.no_sample:
        report.pop("sample_text", None)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if report.get("exists") else 2


if __name__ == "__main__":
    raise SystemExit(main())
