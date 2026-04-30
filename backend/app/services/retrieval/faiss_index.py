"""FAISS vector index manager for L0/L1/L2 layers."""

import json
import os
from pathlib import Path

import faiss
import numpy as np

from app.config import settings


class FAISSIndexManager:
    """Manage FAISS indexes for L0/L1/L2 layers."""

    def __init__(self):
        settings.FAISS_DIR.mkdir(parents=True, exist_ok=True)

    def _index_path(self, kb_id: str, layer: str) -> Path:
        """Get index file path for a KB and layer."""
        kb_dir = settings.FAISS_DIR / kb_id
        kb_dir.mkdir(parents=True, exist_ok=True)
        return kb_dir / f"{layer}.index"

    def _meta_path(self, kb_id: str, layer: str) -> Path:
        """Get metadata file path (stores doc_id -> index mapping)."""
        kb_dir = settings.FAISS_DIR / kb_id
        kb_dir.mkdir(parents=True, exist_ok=True)
        return kb_dir / f"{layer}_meta.json"

    def _load_meta(self, kb_id: str, layer: str) -> dict:
        """Load metadata mapping doc_id to index positions."""
        path = self._meta_path(kb_id, layer)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_meta(self, kb_id: str, layer: str, meta: dict) -> None:
        """Save metadata mapping."""
        path = self._meta_path(kb_id, layer)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def create_index(self, kb_id: str, layer: str, dimension: int) -> faiss.IndexFlatIP:
        """Create a new FAISS index for a KB layer."""
        index = faiss.IndexFlatIP(dimension)
        index_path = self._index_path(kb_id, layer)
        faiss.write_index(index, str(index_path))
        self._save_meta(kb_id, layer, {})
        return index

    def load_index(self, kb_id: str, layer: str) -> faiss.IndexFlatIP | None:
        """Load an existing FAISS index."""
        index_path = self._index_path(kb_id, layer)
        if not index_path.exists():
            return None
        return faiss.read_index(str(index_path))

    def add_vectors(self, kb_id: str, layer: str, vectors: list[list[float]], doc_id: str) -> None:
        """Add vectors to an index, tracking which doc_id they belong to."""
        index = self.load_index(kb_id, layer)
        if index is None:
            dimension = len(vectors[0])
            index = self.create_index(kb_id, layer, dimension)

        # Normalize and add
        arr = np.array(vectors, dtype=np.float32)
        faiss.normalize_L2(arr)

        start_idx = index.ntotal
        index.add(arr)

        # Update metadata
        meta = self._load_meta(kb_id, layer)
        if doc_id not in meta:
            meta[doc_id] = []
        meta[doc_id].extend(range(start_idx, start_idx + len(vectors)))
        self._save_meta(kb_id, layer, meta)

        # Save index
        faiss.write_index(index, str(self._index_path(kb_id, layer)))

    def remove_doc(self, kb_id: str, layer: str, doc_id: str) -> None:
        """Remove all vectors for a doc_id from the index."""
        index = self.load_index(kb_id, layer)
        if index is None:
            return

        meta = self._load_meta(kb_id, layer)
        if doc_id not in meta:
            return

        # Remove vectors by rebuilding index without them
        remove_indices = set(meta[doc_id])
        remaining = [i for i in range(index.ntotal) if i not in remove_indices]

        if remaining:
            vectors = index.reconstruct_batch(remaining)
            new_index = faiss.IndexFlatIP(index.d)
            new_index.add(vectors)
        else:
            new_index = faiss.IndexFlatIP(index.d)

        # Update metadata
        del meta[doc_id]
        self._save_meta(kb_id, layer, meta)

        # Save new index
        faiss.write_index(new_index, str(self._index_path(kb_id, layer)))

    def search(self, kb_id: str, layer: str, query_vector: list[float], top_k: int = 10) -> list[dict]:
        """Search the index for similar vectors."""
        index = self.load_index(kb_id, layer)
        if index is None or index.ntotal == 0:
            return []

        meta = self._load_meta(kb_id, layer)
        query = np.array([query_vector], dtype=np.float32)
        faiss.normalize_L2(query)

        actual_k = min(top_k, index.ntotal)
        scores, indices = index.search(query, actual_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            # Find which doc_id this index belongs to
            doc_id = None
            for did, idx_list in meta.items():
                if idx in idx_list:
                    doc_id = did
                    break
            results.append({
                "index": int(idx),
                "score": float(score),
                "doc_id": doc_id,
            })

        return results

    def delete_index(self, kb_id: str, layer: str) -> None:
        """Delete an entire index."""
        index_path = self._index_path(kb_id, layer)
        meta_path = self._meta_path(kb_id, layer)
        if index_path.exists():
            index_path.unlink()
        if meta_path.exists():
            meta_path.unlink()
