"""Content extraction from artifact files.

Extracts text content with provenance from supported file formats. Each extractor
returns structured content that preserves useful context (page numbers, sheet names,
slide order, table structure) so graders can reference specific parts.

Supported formats:
- .txt, .md: plain text
- .json: formatted JSON content
- .csv, .tsv: tabular content with headers and rows
- .pdf: text-layer extraction (no OCR)
- .docx: paragraphs and tables
- .xlsx: sheet names, cell values, and formula text (no recalculation)
- .pptx: slide text, tables, and speaker notes in slide order

This is content-based extraction, not visual assessment. Layout, figures, embedded
images, charts, and scanned PDF content that was not extracted are not supported.
Extraction errors are reported explicitly; unsupported content within an otherwise
readable file does not invalidate the extracted text.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003 — used at runtime in extraction functions


@dataclass(frozen=True)
class ExtractionResult:
    """The result of extracting content from an artifact file."""

    text: str
    format: str
    page_count: int | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractionError:
    """An error during content extraction."""

    detail: str


def extract_content(path: Path) -> ExtractionResult | ExtractionError:
    """Extract text content from a file at ``path``.

    Returns an ``ExtractionResult`` with the extracted text and provenance, or an
    ``ExtractionError`` when extraction fails. The caller is responsible for
    resolving the artifact path from the experiment root.
    """
    if not path.exists():
        return ExtractionError(detail=f"File not found: {path}")
    if not path.is_file():
        return ExtractionError(detail=f"Not a file: {path}")

    suffix = path.suffix.lower()
    extractors = {
        ".txt": _extract_text,
        ".md": _extract_text,
        ".json": _extract_json,
        ".csv": _extract_csv,
        ".tsv": _extract_tsv,
        ".pdf": _extract_pdf,
        ".docx": _extract_docx,
        ".xlsx": _extract_xlsx,
        ".pptx": _extract_pptx,
    }
    extractor = extractors.get(suffix)
    if extractor is None:
        return ExtractionError(
            detail=f"Unsupported file format: {suffix}. "
            f"Supported: {', '.join(sorted(extractors))}."
        )
    try:
        return extractor(path)
    except Exception as exc:
        return ExtractionError(
            detail=f"Extraction failed for {path.name} ({suffix}): "
            f"{type(exc).__name__}: {exc}"
        )


def _extract_text(path: Path) -> ExtractionResult:
    text = path.read_text(encoding="utf-8")
    return ExtractionResult(text=text, format="text")


def _extract_json(path: Path) -> ExtractionResult:
    raw = path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
    return ExtractionResult(text=formatted, format="json")


def _extract_csv(path: Path) -> ExtractionResult:
    return _extract_delimited(path, delimiter=",", format_name="csv")


def _extract_tsv(path: Path) -> ExtractionResult:
    return _extract_delimited(path, delimiter="\t", format_name="tsv")


def _extract_delimited(
    path: Path, *, delimiter: str, format_name: str
) -> ExtractionResult:
    raw = path.read_text(encoding="utf-8")
    reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return ExtractionResult(text="(empty table)", format=format_name)
    lines: list[str] = []
    for i, row in enumerate(rows):
        prefix = "Header" if i == 0 else f"Row {i}"
        lines.append(f"{prefix}: {delimiter.join(row)}")
    return ExtractionResult(
        text="\n".join(lines),
        format=format_name,
    )


def _extract_pdf(path: Path) -> ExtractionResult:
    import pymupdf

    doc = pymupdf.open(str(path))
    pages: list[str] = []
    warnings: list[str] = []
    for i in range(len(doc)):
        page = doc[i]
        text = str(page.get_text("text"))
        if text.strip():
            pages.append(f"--- Page {i + 1} ---\n{text.strip()}")
        else:
            warnings.append(f"Page {i + 1}: no extractable text (may be scanned/image)")
    doc.close()
    if not pages:
        return ExtractionError(  # type: ignore[return-value]
            detail="PDF contains no extractable text. OCR is not supported."
        )
    return ExtractionResult(
        text="\n\n".join(pages),
        format="pdf",
        page_count=len(pages),
        warnings=tuple(warnings),
    )


def _extract_docx(path: Path) -> ExtractionResult:
    import docx

    doc = docx.Document(str(path))
    parts: list[str] = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)
    for table in doc.tables:
        rows: list[str] = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows.append(" | ".join(cells))
        if rows:
            parts.append("[Table]\n" + "\n".join(rows))
    if not parts:
        return ExtractionResult(text="(empty document)", format="docx")
    return ExtractionResult(text="\n\n".join(parts), format="docx")


def _extract_xlsx(path: Path) -> ExtractionResult:
    import openpyxl

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=False)
    parts: list[str] = []
    warnings: list[str] = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        lines: list[str] = [f"--- Sheet: {sheet_name} ---"]
        has_content = False
        for row in ws.iter_rows():
            cells: list[str] = []
            for cell in row:
                if cell.value is not None:
                    has_content = True
                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        cells.append(f"[formula: {cell.value}]")
                    else:
                        value_str = str(cell.value)
                        cells.append(value_str)
                elif cell.data_type == "f":
                    cells.append("[formula: cached value unavailable]")
                    warnings.append(
                        f"Sheet '{sheet_name}': cell has formula with no cached value"
                    )
                else:
                    cells.append("")
            lines.append(" | ".join(cells))
        if has_content:
            parts.append("\n".join(lines))
    wb.close()
    if not parts:
        return ExtractionResult(
            text="(empty workbook)", format="xlsx", warnings=tuple(warnings)
        )
    return ExtractionResult(
        text="\n\n".join(parts),
        format="xlsx",
        warnings=tuple(warnings),
    )


def _extract_pptx(path: Path) -> ExtractionResult:
    from pptx import Presentation

    prs = Presentation(str(path))
    parts: list[str] = []
    for i, slide in enumerate(prs.slides):
        lines: list[str] = [f"--- Slide {i + 1} ---"]
        for shape in slide.shapes:
            if shape.has_text_frame:
                text = shape.text_frame.text.strip()  # type: ignore[union-attr]
                if text:
                    lines.append(text)
            if shape.has_table:
                tbl = shape.table  # type: ignore[union-attr]
                rows: list[str] = []
                for row in tbl.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    rows.append(" | ".join(cells))
                if rows:
                    lines.append("[Table]\n" + "\n".join(rows))
        if hasattr(slide, "notes_slide") and slide.notes_slide:
            notes = slide.notes_slide.notes_text_frame
            if notes and notes.text.strip():
                lines.append(f"[Speaker Notes]\n{notes.text.strip()}")
        if len(lines) > 1:
            parts.append("\n".join(lines))
    if not parts:
        return ExtractionResult(text="(empty presentation)", format="pptx")
    return ExtractionResult(text="\n\n".join(parts), format="pptx")
