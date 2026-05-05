"""L2 compiler: saves chunks to filesystem, creates FAISS and FTS5 indexes."""

import json
import logging
import os
import re
from pathlib import Path

import faiss
import numpy as np

from app.config import settings
from app.models.database import get_connection
from app.services.parsing.chunking import Chunk, estimate_tokens

logger = logging.getLogger("app.compilation.l2")

# Excel row batching
_EXCEL_ROWS_PER_CHUNK = 50


class L2Compiler:
    """Compile L2 layer: original text chunks with vector and full-text search."""

    def __init__(self, embedding_provider=None):
        self._embedding_provider = embedding_provider

    def save_chunks(self, chunks: list[Chunk], kb_id: str, doc_id: str) -> Path:
        """Save chunks to filesystem as individual markdown files."""
        chunks_dir = settings.KB_DIR / kb_id / "documents" / doc_id / "l2_chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)

        for chunk in chunks:
            chunk_file = chunks_dir / f"{chunk.chunk_id}.md"
            with open(chunk_file, "w", encoding="utf-8") as f:
                f.write(f"# Chunk: {chunk.chunk_id}\n\n")
                f.write(f"**Doc ID:** {chunk.doc_id}\n")
                f.write(f"**KB ID:** {chunk.kb_id}\n")
                f.write(f"**Token Count:** {chunk.token_count}\n")
                f.write(f"**Is Overlap:** {chunk.is_overlap}\n\n")
                f.write("---\n\n")
                f.write(chunk.content)

        return chunks_dir

    def save_excel_chunks(
        self,
        l2_markdown: str,
        analysis: dict,
        doc_id: str,
        kb_id: str,
        file_hash: str,
        rows_per_chunk: int = _EXCEL_ROWS_PER_CHUNK,
    ) -> tuple[list[Chunk], Path]:
        """Create and save Excel-specific L2 chunks that preserve sheet boundaries.

        Each chunk is tagged with sheet_name and row_range in its heading and
        content.  The method splits the enriched L2 markdown produced by
        ``excel_processor.process_excel()`` into row-batched chunks, one sheet
        at a time, so sheet boundaries are never crossed.

        Returns (chunks, chunks_dir).
        """
        # Split by sheet headings
        sheet_sections = re.split(r"(?=# Sheet: )", l2_markdown)
        if not sheet_sections:
            sheet_sections = [l2_markdown]

        chunks: list[Chunk] = []
        idx = 0

        for section in sheet_sections:
            section = section.strip()
            if not section:
                continue

            # Extract sheet name
            sheet_match = re.match(r"# Sheet: (.+)", section)
            sheet_name = sheet_match.group(1).strip() if sheet_match else ""

            # Collect banner lines
            banner_lines = []
            body_lines: list[str] = []
            in_banners = True
            for line in section.split("\n"):
                if in_banners and line.startswith("## Banner:"):
                    banner_lines.append(line)
                else:
                    in_banners = False
                    body_lines.append(line)

            banner_prefix = "\n".join(banner_lines) + "\n\n" if banner_lines else ""

            # Find the table part (header, separator, data rows)
            header_line = None
            sep_line = None
            data_rows = []

            for line in body_lines:
                if header_line is None and line.startswith("|"):
                    header_line = line
                elif sep_line is None and line.startswith("|") and "---" in line:
                    sep_line = line
                elif line.startswith("|"):
                    data_rows.append(line)

            if not header_line or not data_rows:
                # Single chunk for the whole section
                content = section
                chunks.append(Chunk(
                    chunk_id=f"{doc_id}_chunk_{idx + 1:03d}",
                    doc_id=doc_id,
                    kb_id=kb_id,
                    content=content,
                    token_count=estimate_tokens(content),
                    file_hash=file_hash,
                ))
                idx += 1
                continue

            # Batch data rows preserving sheet boundary
            pos = 0
            while pos < len(data_rows):
                batch = data_rows[pos:pos + rows_per_chunk]
                batch_start = pos + 1  # 1-based data row
                batch_end = pos + len(batch)

                row_range = f"rows {batch_start}-{batch_end}" if batch_end > batch_start else f"row {batch_start}"
                heading = f"## {sheet_name} / {row_range}" if sheet_name else f"## {row_range}"

                # Include banner prefix only in the first chunk of each sheet
                prefix = banner_prefix if pos == 0 else ""
                table_content = prefix + heading + "\n\n" + header_line + "\n" + sep_line + "\n" + "\n".join(batch)

                chunk = Chunk(
                    chunk_id=f"{doc_id}_chunk_{idx + 1:03d}",
                    doc_id=doc_id,
                    kb_id=kb_id,
                    content=table_content,
                    token_count=estimate_tokens(table_content),
                    file_hash=file_hash,
                )
                # Store sheet metadata as extra fields for downstream consumers
                chunk._sheet_name = sheet_name  # type: ignore[attr-defined]
                chunk._row_range = row_range     # type: ignore[attr-defined]
                chunks.append(chunk)
                idx += 1
                pos += rows_per_chunk

        # Save to filesystem
        chunks_dir = settings.KB_DIR / kb_id / "documents" / doc_id / "l2_chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)

        for chunk in chunks:
            chunk_file = chunks_dir / f"{chunk.chunk_id}.md"
            with open(chunk_file, "w", encoding="utf-8") as f:
                f.write(f"# Chunk: {chunk.chunk_id}\n\n")
                f.write(f"**Doc ID:** {chunk.doc_id}\n")
                f.write(f"**KB ID:** {chunk.kb_id}\n")
                sheet_name = getattr(chunk, "_sheet_name", "")
                row_range = getattr(chunk, "_row_range", "")
                if sheet_name:
                    f.write(f"**Sheet:** {sheet_name}\n")
                if row_range:
                    f.write(f"**Row Range:** {row_range}\n")
                f.write(f"**Token Count:** {chunk.token_count}\n")
                f.write(f"**Is Overlap:** {chunk.is_overlap}\n\n")
                f.write("---\n\n")
                f.write(chunk.content)

        # Persist analysis JSON alongside chunks for L1 to consume later
        analysis_path = chunks_dir / "excel_analysis.json"
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)

        logger.info(
            "Excel L2: %d chunks saved for doc %s (%d sheets)",
            len(chunks), doc_id, len(sheet_sections),
        )
        return chunks, chunks_dir

    async def build_and_save_faiss(self, chunks: list[Chunk], kb_id: str, doc_id: str) -> None:
        """Build embeddings and add to the shared FAISS index via FAISSIndexManager."""
        if not chunks:
            return

        # Generate embeddings
        texts = [c.content for c in chunks]
        embeddings = await self._embedding_provider.embed(texts)

        # Use FAISSIndexManager to add vectors to the shared l2.index
        from app.services.retrieval.faiss_index import FAISSIndexManager
        mgr = FAISSIndexManager()
        vectors = [list(map(float, e)) for e in embeddings]
        mgr.add_vectors(kb_id, "l2", vectors, doc_id)
        logger.info("FAISS: added %d vectors for doc %s", len(vectors), doc_id)

    def build_fts_index(self, chunks: list[Chunk]) -> None:
        """Build FTS5 full-text search index for chunks."""
        conn = get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            for chunk in chunks:
                conn.execute(
                    "INSERT OR REPLACE INTO fts_content (doc_id, chunk_id, content) VALUES (?, ?, ?)",
                    (chunk.doc_id, chunk.chunk_id, chunk.content),
                )
            conn.commit()
        finally:
            conn.close()

    async def compile(self, chunks: list[Chunk], kb_id: str, doc_id: str) -> Path:
        """Full L2 compilation: save chunks, build indexes."""
        # Save chunks to filesystem
        chunks_dir = self.save_chunks(chunks, kb_id, doc_id)

        # Build FAISS index via shared index manager
        if self._embedding_provider:
            try:
                await self.build_and_save_faiss(chunks, kb_id, doc_id)
            except Exception as e:
                logger.warning(
                    "FAISS index build failed (embedding API error): %s. "
                    "Continuing with keyword-only search.", e,
                )

        # Build FTS5 index
        self.build_fts_index(chunks)

        return chunks_dir
