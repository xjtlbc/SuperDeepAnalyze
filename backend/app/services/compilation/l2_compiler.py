"""L2 compiler: saves chunks to filesystem, creates FAISS and FTS5 indexes."""

import json
import os
from pathlib import Path

import faiss
import numpy as np

from app.config import settings
from app.models.database import get_connection
from app.services.parsing.chunking import Chunk


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

    async def build_faiss_index(self, chunks: list[Chunk]) -> faiss.IndexFlatIP:
        """Build FAISS index from chunk embeddings."""
        if not chunks:
            return None

        # Generate embeddings
        texts = [c.content for c in chunks]
        embeddings = await self._embedding_provider.embed(texts)
        dim = len(embeddings[0])

        # Normalize embeddings for cosine similarity
        embeddings = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(embeddings)

        # Create FAISS index
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)

        return index

    def save_faiss_index(self, index: faiss.IndexFlatIP, kb_id: str, doc_id: str) -> None:
        """Save FAISS index to disk."""
        if index is None:
            return

        index_dir = settings.FAISS_DIR / kb_id
        index_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(index_dir / f"l2_{doc_id}.index"))

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

        # Build FAISS index
        if self._embedding_provider:
            index = await self.build_faiss_index(chunks)
            self.save_faiss_index(index, kb_id, doc_id)

        # Build FTS5 index
        self.build_fts_index(chunks)

        return chunks_dir
