"""Excel/CSV parser with enriched processing via pandas+openpyxl.

Primary: pandas+openpyxl ExcelProcessor (preserves formulas, comments,
hyperlinks, number formatting, merged cells, multi-sheet structure).
Fallback: python-calamine for basic extraction when openpyxl fails.

Row-batched chunking: each chunk = header row + N data rows (50 by default),
preserving full Markdown table structure. Multi-sheet aware.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path

from python_calamine import CalamineWorkbook

from app.services.parsing.types import Chunk, DocType, ParsedDocument
from app.services.parsing.docling_parser import compute_file_hash
from app.services.parsing.chunking import estimate_tokens

logger = logging.getLogger("app.parsing")

ROWS_PER_CHUNK = 50
CALAMINE_DATE_TYPES = (datetime,)


def _format_cell(value, fmt_date: bool = True) -> str:
    """Format a cell value for Markdown table output."""
    if value is None:
        return ""
    if fmt_date and isinstance(value, CALAMINE_DATE_TYPES):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return f"{value:.4g}"
    return str(value)


def _is_empty_row(row: list) -> bool:
    return all(c is None or str(c).strip() == "" for c in row)


def _find_header_start(rows: list[list]) -> int:
    for i, row in enumerate(rows):
        if not _is_empty_row(row):
            return i
    return -1


def _find_data_end(rows: list[list], header_idx: int) -> int:
    end = len(rows)
    while end > header_idx + 1 and _is_empty_row(rows[end - 1]):
        end -= 1
    return end


def _parse_rows_to_markdown(rows: list[list]) -> str:
    """Convert raw row data to a basic Markdown table (calamine fallback)."""
    if not rows:
        return ""

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


class _AnnotatedChunks(list):
    """A list of Chunk objects with an attached excel_analysis dict.

    Used to pass structured Excel analysis data alongside chunks through
    the compilation pipeline without modifying the Chunk dataclass.
    """
    def __init__(self, chunks, excel_analysis=None):
        super().__init__(chunks)
        self.excel_analysis = excel_analysis


class ExcelParser:
    """Parse XLSX/XLS/CSV files into Markdown tables with row-batched chunks.

    Uses pandas+openpyxl for enriched processing (formulas, comments,
    hyperlinks, number formatting). Falls back to python-calamine if
    the enriched processor fails.
    """

    rows_per_chunk: int = ROWS_PER_CHUNK

    def parse(self, file_path: str | Path, doc_id: str, kb_id: str) -> ParsedDocument:
        """Full parse returning a single ParsedDocument."""
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext == ".csv":
            rows_by_sheet = [self._read_csv(path)]
            sheet_names = None
            content = self._build_full_markdown_fallback(rows_by_sheet, sheet_names)
            metadata = {"source": "csv"}
        else:
            # Try enriched processor first
            content, metadata = self._try_enriched_parse(path)
            if content is not None and metadata.get("analysis"):
                self._save_analysis_json(metadata["analysis"], doc_id, kb_id)
            if content is None:
                # Fallback to calamine
                logger.info("Falling back to calamine for %s", path.name)
                rows_by_sheet, sheet_names = self._read_excel_sheets(path)
                content = self._build_full_markdown_fallback(rows_by_sheet, sheet_names)
                metadata = {"source": "calamine"}

        return ParsedDocument(
            doc_id=doc_id,
            kb_id=kb_id,
            filename=path.name,
            file_type=DocType.CSV if ext == ".csv" else DocType.XLSX,
            file_hash=compute_file_hash(path),
            content=content,
            metadata=metadata,
        )

    def parse_to_chunks(
        self,
        file_path: str | Path,
        doc_id: str,
        kb_id: str,
        file_hash: str,
    ) -> list[Chunk]:
        """Parse and return row-batched chunks directly.

        For Excel files processed via the enriched pipeline, the analysis JSON
        is attached to the returned list as ``chunks._excel_analysis`` so that
        downstream L1 compilation can use the compact analysis instead of the
        full L2 text.
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext == ".csv":
            rows_by_sheet = [self._read_csv(path)]
            sheet_names = None
            return self._build_chunks(rows_by_sheet, sheet_names, doc_id, kb_id, file_hash)

        # Try enriched parse — split by # Sheet: headings
        content, metadata = self._try_enriched_parse(path)
        if content is not None:
            chunks = self._enriched_content_to_chunks(content, doc_id, kb_id, file_hash)
            # Attach analysis for downstream L1 consumption via a container class
            analysis_data = metadata.get("analysis")
            if analysis_data is not None:
                self._save_analysis_json(analysis_data, doc_id, kb_id)
                chunks = _AnnotatedChunks(chunks, excel_analysis=analysis_data)
            return chunks

        # Fallback to calamine chunking
        rows_by_sheet, sheet_names = self._read_excel_sheets(path)
        return self._build_chunks(rows_by_sheet, sheet_names, doc_id, kb_id, file_hash)

    @staticmethod
    def _save_analysis_json(analysis: dict, doc_id: str, kb_id: str) -> None:
        """Persist the analysis JSON for Agent tools (search_excel)."""
        try:
            from app.config import settings
            import json
            doc_dir = settings.KB_DIR / kb_id / "documents" / doc_id
            doc_dir.mkdir(parents=True, exist_ok=True)
            with open(doc_dir / "excel_analysis.json", "w", encoding="utf-8") as f:
                json.dump(analysis, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── Enriched processing ──────────────────────────────────────

    def _try_enriched_parse(self, path: Path) -> tuple[str | None, dict]:
        """Try pandas+openpyxl enriched processing. Returns (content, metadata) or (None, {})."""
        try:
            from app.services.parsing.excel_processor import process_excel
            result = process_excel(path)
            return result.l2_markdown, {"source": "pandas+openpyxl", "analysis": result.analysis}
        except ImportError:
            logger.warning("pandas/openpyxl not available, using calamine fallback")
            return None, {}
        except Exception as e:
            logger.warning("Enriched Excel processing failed for %s: %s", path.name, e)
            return None, {}

    def _enriched_content_to_chunks(
        self, content: str, doc_id: str, kb_id: str, file_hash: str,
    ) -> list[Chunk]:
        """Split enriched L2 markdown into row-batched chunks.

        Handles ``## Banner:`` lines by including them in the first chunk of
        each sheet section, separate from the data table.
        """
        # Split by sheet headings
        import re
        sheet_sections = re.split(r"(?=# Sheet: )", content)
        if not sheet_sections:
            sheet_sections = [content]

        chunks = []
        idx = 0

        for section in sheet_sections:
            section = section.strip()
            if not section:
                continue

            # Extract sheet name
            sheet_match = re.match(r"# Sheet: (.+)", section)
            sheet_name = sheet_match.group(1).strip() if sheet_match else ""

            # Separate banner lines from table lines
            lines = section.split("\n")
            banner_lines = []
            table_lines = []
            in_banners = True

            for line in lines:
                if in_banners and line.startswith("## Banner:"):
                    banner_lines.append(line)
                elif line.startswith("# Sheet:"):
                    continue  # skip the sheet heading itself
                else:
                    in_banners = False
                    table_lines.append(line)

            banner_prefix = "\n".join(banner_lines) + "\n\n" if banner_lines else ""

            # Split table into header + data rows
            header_line = None
            sep_line = None
            data_rows = []

            for line in table_lines:
                if header_line is None and line.startswith("|"):
                    header_line = line
                elif sep_line is None and line.startswith("|") and "---" in line:
                    sep_line = line
                elif line.startswith("|"):
                    data_rows.append(line)

            if not header_line or not data_rows:
                # Single chunk for the whole section
                chunks.append(Chunk(
                    chunk_id=f"{doc_id}_chunk_{idx + 1:03d}",
                    doc_id=doc_id,
                    kb_id=kb_id,
                    content=section,
                    token_count=estimate_tokens(section),
                    file_hash=file_hash,
                ))
                idx += 1
                continue

            # Batch data rows
            pos = 0
            while pos < len(data_rows):
                batch = data_rows[pos:pos + self.rows_per_chunk]
                batch_start = pos + 1  # 1-based data row
                batch_end = pos + len(batch)

                range_str = f"第 {batch_start}-{batch_end} 行" if batch_end > batch_start else f"第 {batch_start} 行"
                heading = f"## {sheet_name} / {range_str}" if sheet_name else f"## {range_str}"

                # Include banner prefix only in the first chunk of this sheet
                prefix = banner_prefix if pos == 0 else ""
                table_content = prefix + heading + "\n\n" + header_line + "\n" + sep_line + "\n" + "\n".join(batch)
                chunks.append(Chunk(
                    chunk_id=f"{doc_id}_chunk_{idx + 1:03d}",
                    doc_id=doc_id,
                    kb_id=kb_id,
                    content=table_content,
                    token_count=estimate_tokens(table_content),
                    file_hash=file_hash,
                ))
                idx += 1
                pos += self.rows_per_chunk

        return chunks

    # ── CSV ──────────────────────────────────────────────────────

    @staticmethod
    def _read_csv(path: Path) -> list[list]:
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

    # ── Calamine fallback ────────────────────────────────────────

    @staticmethod
    def _read_excel_sheets(path: Path) -> tuple[list[list[list]], list[str] | None]:
        workbook = CalamineWorkbook.from_path(str(path))
        rows_by_sheet = []
        for name in workbook.sheet_names:
            sheet = workbook.get_sheet_by_name(name)
            rows_by_sheet.append(sheet.to_python())
        sheet_names = workbook.sheet_names if len(workbook.sheet_names) > 1 else None
        return rows_by_sheet, sheet_names

    def _build_full_markdown_fallback(
        self,
        rows_by_sheet: list[list[list]],
        sheet_names: list[str] | None,
    ) -> str:
        parts = []
        for si, rows in enumerate(rows_by_sheet):
            if sheet_names and si < len(sheet_names):
                parts.append(f"# Sheet: {sheet_names[si]}")
            parts.append(_parse_rows_to_markdown(rows))
        return "\n\n".join(parts)

    # ── Chunk building (calamine fallback) ────────────────────────

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
        if not rows:
            return []

        header_idx = _find_header_start(rows)
        if header_idx < 0:
            return []

        data_end = _find_data_end(rows, header_idx)
        header = rows[header_idx]
        data_start = header_idx + 1
        data_rows = rows[data_start:data_end]

        if not data_rows:
            return [self._make_chunk(
                rows=[header], sheet_label=sheet_label,
                row_start=header_idx, row_end=header_idx,
                doc_id=doc_id, kb_id=kb_id, file_hash=file_hash, idx=start_idx,
            )]

        chunks = []
        idx = start_idx
        pos = 0
        while pos < len(data_rows):
            batch_end = min(pos + self.rows_per_chunk, len(data_rows))
            batch = data_rows[pos:batch_end]
            chunks.append(self._make_chunk(
                rows=[header] + batch, sheet_label=sheet_label,
                row_start=data_start + pos, row_end=data_start + batch_end - 1,
                doc_id=doc_id, kb_id=kb_id, file_hash=file_hash, idx=idx,
            ))
            idx += 1
            pos = batch_end

        return chunks

    @staticmethod
    def _make_chunk(
        rows: list[list], sheet_label: str, row_start: int, row_end: int,
        doc_id: str, kb_id: str, file_hash: str, idx: int,
    ) -> Chunk:
        table_md = _parse_rows_to_markdown(rows)
        range_str = f"第 {row_start + 1} 行" if row_start == row_end else f"第 {row_start + 1}-{row_end + 1} 行"
        heading = f"## {sheet_label} / {range_str}" if sheet_label else f"## {range_str}"
        content = f"{heading}\n\n{table_md}"

        return Chunk(
            chunk_id=f"{doc_id}_chunk_{idx + 1:03d}",
            doc_id=doc_id, kb_id=kb_id,
            content=content, token_count=estimate_tokens(content), file_hash=file_hash,
        )
