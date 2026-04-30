"""InformationTracker: Track information gain across tool calls.

Replaces the old _is_information_saturated() which only checked result length.
This tracker measures whether new entities, relations, or documents are being
discovered — short results that contain new findings do NOT trigger saturation.
"""

import json
import re
from collections import deque

from app.services.agent.utils import extract_entities


class InformationTracker:
    """Tracks information gain to detect when the Agent has exhausted useful searches."""

    def __init__(self, min_recent_calls: int = 5):
        self.all_entities: set[str] = set()
        self.all_relations: set[str] = set()
        self.all_docs: set[str] = set()  # docs referenced in any tool result
        self.docs_read: set[str] = set()  # docs actually opened via read_l1/read_l2
        self.contradictions: set[str] = set()  # detected contradictions
        self.recent_gains: deque[int] = deque(maxlen=min_recent_calls)
        self._min_recent_calls = min_recent_calls

    def record_gain(self, tool_name: str, result_text: str) -> int:
        """Record information gain from a tool call.

        Returns the delta (number of new items discovered).
        """
        new_entities = self._extract_entities(result_text)
        new_relations = self._extract_relations(result_text)
        new_docs = self._extract_docs(result_text)
        new_contradictions = self._extract_contradictions(result_text)

        delta_entities = new_entities - self.all_entities
        delta_relations = new_relations - self.all_relations
        delta_docs = new_docs - self.all_docs

        delta = len(delta_entities) + len(delta_relations) + len(delta_docs)

        self.all_entities |= delta_entities
        self.all_relations |= delta_relations
        self.all_docs |= delta_docs
        self.contradictions |= new_contradictions
        self.recent_gains.append(delta)

        return delta

    def is_saturated(self) -> bool:
        """Return True if the last N calls yielded zero total information gain."""
        if len(self.recent_gains) < self._min_recent_calls:
            return False
        return sum(self.recent_gains) == 0

    def record_doc_read(self, doc_id: str) -> None:
        """Record that a document was actually opened for reading (read_l1/read_l2)."""
        if doc_id:
            self.docs_read.add(doc_id)

    def recent_gain_rate(self) -> float:
        """Average information gain per call in recent window."""
        if not self.recent_gains:
            return 0.0
        return sum(self.recent_gains) / len(self.recent_gains)

    def get_stats(self) -> dict:
        """Return current tracking statistics."""
        return {
            "total_entities": len(self.all_entities),
            "total_relations": len(self.all_relations),
            "total_docs": len(self.all_docs),
            "docs_read": len(self.docs_read),
            "contradictions": len(self.contradictions),
            "recent_gains": list(self.recent_gains),
        }

    # --- Extraction helpers ---

    def _extract_entities(self, result_text: str) -> set[str]:
        """Extract entity names from tool result.

        Tries JSON parsing first (structured), falls back to regex.
        """
        entities = set()

        # Try structured extraction first
        try:
            data = json.loads(result_text)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        entities.update(self._json_extract_entities(item))
            elif isinstance(data, dict):
                entities.update(self._json_extract_entities(data))
            return entities
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: regex on plain text
        entities.update(extract_entities(result_text))
        return entities

    def _extract_relations(self, result_text: str) -> set[str]:
        """Extract relation patterns from tool result."""
        relations = set()
        try:
            data = json.loads(result_text)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        relations.update(self._json_extract_relations(item))
            elif isinstance(data, dict):
                relations.update(self._json_extract_relations(data))
        except (json.JSONDecodeError, ValueError):
            pass
        return relations

    def _extract_docs(self, result_text: str) -> set[str]:
        """Extract doc_id references from tool result."""
        docs = set()
        try:
            data = json.loads(result_text)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        docs.update(self._json_extract_docs(item))
            elif isinstance(data, dict):
                docs.update(self._json_extract_docs(data))
        except (json.JSONDecodeError, ValueError):
            # Look for doc_id patterns in text
            for match in re.finditer(r'(?:doc_|doc_id["\s:]+)(\S+)', result_text):
                docs.add(match.group(1).strip('",: '))
        return docs

    def _extract_contradictions(self, result_text: str) -> set[str]:
        """Extract contradiction indicators from tool result."""
        contradictions = set()
        try:
            data = json.loads(result_text)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                for key, value in item.items():
                    lk = key.lower()
                    if isinstance(value, (list, str)):
                        vals = value if isinstance(value, list) else [value]
                        if any(k in lk for k in ["contradict", "矛盾", "conflict", "不一致"]):
                            for v in vals:
                                if isinstance(v, str) and len(v) > 2:
                                    contradictions.add(v)
        except (json.JSONDecodeError, ValueError):
            pass
        return contradictions

    # --- JSON extraction ---

    def _json_extract_entities(self, item: dict) -> set[str]:
        entities = set()
        for key, value in item.items():
            lower_key = key.lower()
            if isinstance(value, str) and 2 <= len(value) <= 30:
                if any(k in lower_key for k in ["name", "entity", "person", "title", "label"]):
                    entities.add(value)
            elif isinstance(value, list):
                for v in value:
                    if isinstance(v, str) and 2 <= len(v) <= 30:
                        if any(k in lower_key for k in ["entities", "names", "persons", "mentioned"]):
                            entities.add(v)
        return entities

    def _json_extract_relations(self, item: dict) -> set[str]:
        relations = set()
        for key, value in item.items():
            lower_key = key.lower()
            if isinstance(value, str):
                if any(k in lower_key for k in ["relation", "role", "type", "connection", "predicate"]):
                    relations.add(value)
        return relations

    def _json_extract_docs(self, item: dict) -> set[str]:
        docs = set()
        for key, value in item.items():
            lower_key = key.lower()
            if isinstance(value, str):
                if any(k in lower_key for k in ["doc_id", "document_id", "source", "doc"]):
                    docs.add(value)
        return docs

    # --- Text extraction (uses shared extract_entities from utils.py) ---

