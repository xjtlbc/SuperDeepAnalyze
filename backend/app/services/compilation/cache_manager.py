"""Pre-compilation cache manager for cross-KB reuse."""

import sqlite3
import json
import shutil
from pathlib import Path
from datetime import datetime

from app.config import settings
from app.models.database import get_connection


class CacheManager:
    """Manage pre-compilation cache with SHA256 cross-KB reuse."""

    def check_cache(self, file_hash: str) -> dict | None:
        """Check if a pre-compiled result exists for the given file hash."""
        conn = get_connection()
        try:
            cursor = conn.execute(
                "SELECT doc_id, kb_id, data_path, created_at FROM precompile_cache WHERE file_hash = ?",
                (file_hash,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "doc_id": row["doc_id"],
                    "kb_id": row["kb_id"],
                    "data_path": row["data_path"],
                    "created_at": row["created_at"],
                }
            return None
        finally:
            conn.close()

    def save_cache(self, file_hash: str, doc_id: str, kb_id: str, data_path: str) -> None:
        """Save pre-compiled result to cache."""
        conn = get_connection()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO precompile_cache (file_hash, doc_id, kb_id, data_path, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (file_hash, doc_id, kb_id, data_path, datetime.now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    def reuse_cache(self, file_hash: str, target_kb_id: str, target_doc_id: str) -> bool:
        """Reuse cached pre-compilation results for a new document in a different KB."""
        cached = self.check_cache(file_hash)
        if not cached:
            return False

        # Copy cached data to new KB location
        cached_path = Path(cached["data_path"])
        if not cached_path.exists():
            return False

        target_dir = settings.KB_DIR / target_kb_id / "documents" / target_doc_id
        target_dir.mkdir(parents=True, exist_ok=True)

        if cached_path.is_dir():
            shutil.copytree(str(cached_path), str(target_dir), dirs_exist_ok=True)
        else:
            shutil.copy2(str(cached_path), str(target_dir))

        # Update cache entry for new KB
        self.save_cache(file_hash, target_doc_id, target_kb_id, str(target_dir))
        return True

    def invalidate_cache(self, file_hash: str) -> None:
        """Remove cache entry for a file hash."""
        conn = get_connection()
        try:
            conn.execute("DELETE FROM precompile_cache WHERE file_hash = ?", (file_hash,))
            conn.commit()
        finally:
            conn.close()

    def clear_all_cache(self) -> None:
        """Clear all pre-compilation cache."""
        conn = get_connection()
        try:
            conn.execute("DELETE FROM precompile_cache")
            conn.commit()
        finally:
            conn.close()

    def reuse_compiled_doc(
        self,
        file_hash: str,
        target_kb_id: str,
        target_doc_id: str,
        source_kb_id: str,
        source_doc_id: str,
    ) -> bool:
        """Reuse a fully compiled document from another KB.

        Copies L1/L2 data, FAISS index, and rebuilds FTS5 entries.
        """
        from app.config import settings
        from app.models.database import get_connection

        source_dir = settings.KB_DIR / source_kb_id / "documents" / source_doc_id
        target_dir = settings.KB_DIR / target_kb_id / "documents" / target_doc_id

        if not (source_dir / "l1_summaries.json").exists():
            return False

        # Copy document directory (parsed.md, l1_summaries.json, l2_chunks/)
        if source_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(source_dir), str(target_dir), dirs_exist_ok=True)

        # Copy FAISS index
        source_faiss = settings.FAISS_DIR / source_kb_id / f"l2_{source_doc_id}.index"
        target_faiss_dir = settings.FAISS_DIR / target_kb_id
        target_faiss = target_faiss_dir / f"l2_{target_doc_id}.index"
        if source_faiss.exists():
            target_faiss_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source_faiss), str(target_faiss))
        else:
            import logging
            logging.getLogger(__name__).warning(
                "FAISS index missing for source doc %s in KB %s, reusing without vector index",
                source_doc_id, source_kb_id
            )

        # Rebuild FTS5 entries from l2_chunks
        chunks_dir = target_dir / "l2_chunks"
        if chunks_dir.exists():
            conn = get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
                for chunk_file in chunks_dir.glob("*.md"):
                    chunk_id = chunk_file.stem
                    with open(chunk_file, "r", encoding="utf-8") as f:
                        # Skip YAML-like header, get content after ---
                        content = f.read()
                        sep_idx = content.find("\n---\n")
                        if sep_idx != -1:
                            content = content[sep_idx + 5:].strip()
                    conn.execute(
                        "INSERT OR REPLACE INTO fts_content (doc_id, chunk_id, content) VALUES (?, ?, ?)",
                        (target_doc_id, chunk_id, content),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        # Update precompile_cache
        self.save_cache(file_hash, target_doc_id, target_kb_id, str(target_dir))
        return True
