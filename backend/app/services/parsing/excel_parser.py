"""Excel/CSV parser using python-calamine and csv stdlib.

Row-batched chunking: each chunk = header row + N data rows (50 by default),
preserving full Markdown table structure. Multi-sheet aware: sheet name and
row range are included in every chunk heading.
"""

import csv
from datetime import datetime
from pathlib import Path

from python_calamine import CalamineWorkbook

from app.services.parsing.types import Chunk, DocType, ParsedDocument
from app.services.parsing.docling_parser import compute_file_hash
from app.services.parsing.chunking import estimate_tokens

ROWS_PER_CHUNK = 50

# Types that calamine's to_python() returns for date-like values
CALAMINE_DATE_TYPES = (datetime,)


def _format_cell(value, fmt_date: bool = True) -> str:
    """Format a cell value for Markdown table output.

    Dates -> YYYY-MM-DD, floats -> up to 4 significant digits,
    None/empty -> empty string.
    """
    if value is None:
        return ""
    if fmt_date and isinstance(value, CALAMINE_DATE_TYPES):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float):
        # Avoid excessive decimal places from floating-point
        if value == int(value):
            return str(int(value))
        return f"{value:.4g}"
    return str(value)


def _is_empty_row(row: list) -> bool:
    """Check if a row is entirely empty (all cells None or blank strings)."""
    return all(c is None or str(c).strip() == "" for c in row)


def _find_header_start(rows: list[list]) -> int:
    """Return the index of the first non-empty row (candidate header)."""
    for i, row in enumerate(rows):
        if not _is_empty_row(row):
            return i
    return -1


def _find_data_end(rows: list[list], header_idx: int) -> int:
    """Return the index after the last non-empty row following the header."""
    end = len(rows)
    while end > header_idx + 1 and _is_empty_row(rows[end - 1]):
        end -= 1
    return end


class ExcelParser:
    """Parse XLSX/XLS/CSV files into Markdown tables with row-batched chunks."""

    rows_per_chunk: int = ROWS_PER_CHUNK

    # ── Public API ──────────────────────────────────────────────

    def parse(self, file_path: str | Path, doc_id: str, kb_id: str) -> ParsedDocument:
        """Full parse returning a single ParsedDocument (backward-compatible).

        Content is the full Markdown (all sheets, all rows) for saved parsed.md.
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext == ".csv":
            rows_by_sheet = [self._read_csv(path)]
            sheet_names = None
        else:
            rows_by_sheet, sheet_names = self._read_excel_sheets(path)

        content = self._build_full_markdown(rows_by_sheet, sheet_names)

        return ParsedDocument(
            doc_id=doc_id,
            kb_id=kb_id,
            filename=path.name,
            file_type=DocType.CSV if ext == ".csv" else DocType.XLSX,
            file_hash=compute_file_hash(path),
            content=content,
            metadata={"source": "calamine/csv"},
        )

    def parse_to_chunks(
        self,
        file_path: str | Path,
        doc_id: str,
        kb_id: str,
        file_hash: str,
    ) -> list[Chunk]:
        """Parse and return row-batched chunks directly.

        Each chunk is a self-contained mini Markdown table:
        header row + up to rows_per_chunk data rows, with sheet name
        and row range in a heading.
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext == ".csv":
            rows_by_sheet = [self._read_csv(path)]
            sheet_names = None
        else:
            rows_by_sheet, sheet_names = self._read_excel_sheets(path)

        return self._build_chunks(rows_by_sheet, sheet_names, doc_id, kb_id, file_hash)

    # ── Reading ──────────────────────────────────────────────────

    @staticmethod
    def _read_csv(path: Path) -> list[list]:
        """Read CSV with encoding fallback chain."""
        rows = []
        for encoding in ("utf-8-sig", "gbk", "gb2312", "utf-8"):
            try:
                with open(path, encoding=encoding) as f:
                    reader = csv.reader(f)
                    for row in reader:
                        rows.append(row)
                break
            except UnicodeDecodeError:
                rows = []
        if not rows:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                reader = csv.reader(f)
                for row in reader:
                    rows.append(row)
        return rows

    @staticmethod
    def _read_excel_sheets(path: Path) -> tuple[list[list[list]], list[str] | None]:
        """Read all sheets.

        Returns:
            rows_by_sheet: one list[list] per sheet
            sheet_names: list of sheet names or None for single-sheet files
        """
        workbook = CalamineWorkbook.from_path(str(path))
        rows_by_sheet = []
        for name in workbook.sheet_names:
            sheet = workbook.get_sheet_by_name(name)
            rows_by_sheet.append(sheet.to_python())

        sheet_names = workbook.sheet_names if len(workbook.sheet_names) > 1 else None
        return rows_by_sheet, sheet_names

    # ── Full Markdown (for parsed.md) ────────────────────────────

    def _build_full_markdown(
        self,
        rows_by_sheet: list[list[list]],
        sheet_names: list[str] | None,
    ) -> str:
        parts = []
        for si, rows in enumerate(rows_by_sheet):
            if sheet_names and si < len(sheet_names):
                parts.append(f"## {sheet_names[si]}")
            parts.append(self._rows_to_markdown(rows))
        return "\n\n".join(parts)

    # ── Chunk building ───────────────────────────────────────────

    def _build_chunks(
        self,
        rows_by_sheet: list[list[list]],
        sheet_names: list[str] | None,
        doc_id: str,
        kb_id: str,
        file_hash: str,
    ) -> list[Chunk]:
        chunks: list[Chunk] = []
        chunk_idx = 0

        for si, rows in enumerate(rows_by_sheet):
            sheet_label = sheet_names[si] if sheet_names else ""
            sheet_chunks = self._sheet_to_chunks(
                rows, sheet_label, doc_id, kb_id, file_hash, chunk_idx
            )
            chunks.extend(sheet_chunks)
            chunk_idx += len(sheet_chunks)

        return chunks

    def _sheet_to_chunks(
        self,
        rows: list[list],
        sheet_label: str,
        doc_id: str,
        kb_id: str,
        file_hash: str,
        start_idx: int,
    ) -> list[Chunk]:
        """Convert one sheet's rows into row-batched chunks."""
        if not rows:
            return []

        # Find header and data boundaries
        header_idx = _find_header_start(rows)
        if header_idx < 0:
            return []

        data_end = _find_data_end(rows, header_idx)
        header = rows[header_idx]
        data_start = header_idx + 1
        data_rows = rows[data_start:data_end]

        if not data_rows:
            # Sheet has header but no data rows — produce one chunk with just the header
            return [self._make_chunk(
                rows=[header],
                sheet_label=sheet_label,
                row_start=header_idx,
                row_end=header_idx,
                doc_id=doc_id,
                kb_id=kb_id,
                file_hash=file_hash,
                idx=start_idx,
            )]

        chunks = []
        idx = start_idx
        pos = 0
        while pos < len(data_rows):
            batch_end = min(pos + self.rows_per_chunk, len(data_rows))
            batch = data_rows[pos:batch_end]
            chunks.append(self._make_chunk(
                rows=[header] + batch,
                sheet_label=sheet_label,
                row_start=data_start + pos,  # 1-based for display
                row_end=data_start + batch_end - 1,
                doc_id=doc_id,
                kb_id=kb_id,
                file_hash=file_hash,
                idx=idx,
            ))
            idx += 1
            pos = batch_end

        return chunks

    @staticmethod
    def _make_chunk(
        rows: list[list],
        sheet_label: str,
        row_start: int,
        row_end: int,
        doc_id: str,
        kb_id: str,
        file_hash: str,
        idx: int,
    ) -> Chunk:
        """Build a single Chunk with heading + Markdown table."""
        table_md = ExcelParser._rows_to_markdown(rows)

        # Build heading with positional metadata
        if row_start == row_end:
            range_str = f"第 {row_start + 1} 行"
        else:
            range_str = f"第 {row_start + 1}-{row_end + 1} 行"

        if sheet_label:
            heading = f"## {sheet_label} / {range_str}"
        else:
            heading = f"## {range_str}"

        content = f"{heading}\n\n{table_md}"

        return Chunk(
            chunk_id=f"{doc_id}_chunk_{idx + 1:03d}",
            doc_id=doc_id,
            kb_id=kb_id,
            content=content,
            token_count=estimate_tokens(content),
            file_hash=file_hash,
        )

    # ── Markdown table formatter ─────────────────────────────────

    @staticmethod
    def _rows_to_markdown(rows: list[list]) -> str:
        """Convert rows to a formatted Markdown table with type-aware cell values."""
        if not rows:
            return ""

        # Pad all rows to same column count
        max_len = max(len(r) for r in rows)
        padded = []
        for r in rows:
            pr = list(r)
            while len(pr) < max_len:
                pr.append("")
            padded.append(pr)

        header = padded[0]
        lines = [
            "| " + " | ".join(_format_cell(c) for c in header) + " |",
            "| " + " | ".join(["---"] * len(header)) + " |",
        ]
        for row in padded[1:]:
            lines.append("| " + " | ".join(_format_cell(c) for c in row) + " |")

        return "\n".join(lines)
