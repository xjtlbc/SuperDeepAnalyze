"""Result enricher: add context, entity links, and confidence to search results."""

import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.services.agent.retrieval_engine.confidence import (
    ConfidenceLevel,
    add_confidence_to_results,
)
from app.utils.logging_config import get_logger

logger = get_logger("app.retrieval.result_enricher")

# Context window size (chars before and after match)
_CONTEXT_BEFORE = 100
_CONTEXT_AFTER = 100


class ResultEnricher:
    """Enrich search results with additional metadata."""

    def __init__(self, kb_id: str):
        self._kb_id = kb_id

    def enrich(
        self,
        results: list[dict],
        add_context: bool = True,
        add_entities: bool = True,
        add_confidence: bool = True,
    ) -> list[dict]:
        """Enrich a list of search results with additional metadata."""
        enriched = []
        for result in results:
            r = dict(result)

            if add_context:
                r = self._add_context_window(r)

            if add_entities:
                r = self._add_entity_links(r)

            if add_confidence:
                r = self._add_confidence(r)

            r["source_layer"] = self._detect_source_layer(r)
            enriched.append(r)

        return enriched

    def _add_context_window(self, result: dict) -> dict:
        """Add surrounding context for the matched content."""
        content = result.get("content", "")
        if not content or len(content) < 50:
            return result

        # Use first 200 chars as context snippet
        result["context_snippet"] = content[:200]

        # If we have a doc_id and chunk_id, try to get surrounding chunks
        doc_id = result.get("doc_id", "")
        chunk_id = result.get("chunk_id", "")
        if doc_id and chunk_id:
            surrounding = self._get_surrounding_chunks(doc_id, chunk_id)
            if surrounding:
                result["surrounding_context"] = surrounding

        return result

    def _add_entity_links(self, result: dict) -> dict:
        """Add links to related entities mentioned in the result."""
        content = str(result.get("content", ""))

        # Try to load L0 entities to find mentions
        entities_path = settings.KB_DIR / self._kb_id / "l0" / "entities.json"
        if not entities_path.exists():
            return result

        try:
            with open(entities_path, "r", encoding="utf-8") as f:
                all_entities = json.load(f)
        except (json.JSONDecodeError, OSError):
            return result

        mentioned = []
        for entity in all_entities[:100]:  # Limit scan
            name = entity.get("name", "")
            if name and name in content:
                mentioned.append({
                    "id": entity.get("id", ""),
                    "name": name,
                    "type": entity.get("type", ""),
                })

        if mentioned:
            result["mentioned_entities"] = mentioned

        return result

    def _add_confidence(self, result: dict) -> dict:
        """Add confidence level based on relevance score."""
        score = result.get("relevance_score", result.get("score", 0))
        if isinstance(score, (int, float)):
            if score > 0.7:
                result["confidence"] = ConfidenceLevel.EXTRACTED.value
            elif score > 0.3:
                result["confidence"] = ConfidenceLevel.INFERRED.value
            else:
                result["confidence"] = ConfidenceLevel.AMBIGUOUS.value
        return result

    def _detect_source_layer(self, result: dict) -> str:
        """Detect which knowledge layer this result comes from."""
        chunk_id = result.get("chunk_id", "")
        if not chunk_id:
            return "unknown"
        if chunk_id.startswith("l0_"):
            return "L0"
        if chunk_id.startswith("l1_"):
            return "L1"
        if chunk_id.startswith("l2_") or "_" in chunk_id:
            return "L2"
        return "unknown"

    def _get_surrounding_chunks(self, doc_id: str, chunk_id: str) -> Optional[dict]:
        """Get chunks adjacent to the given chunk."""
        # Parse chunk number from chunk_id (e.g., "chunk_042" -> 42)
        try:
            parts = chunk_id.split("_")
            chunk_num = int(parts[-1])
        except (ValueError, IndexError):
            return None

        result = {}
        for offset, key in [(-1, "before"), (1, "after")]:
            adj_id = f"{'_'.join(parts[:-1])}_{chunk_num + offset:03d}"
            chunk_path = (
                settings.KB_DIR / self._kb_id / "documents" / doc_id
                / "l2_chunks" / f"{adj_id}.md"
            )
            if chunk_path.exists():
                try:
                    content = chunk_path.read_text(encoding="utf-8")
                    result[key] = content[:_CONTEXT_AFTER]
                except OSError:
                    pass

        return result if result else None
