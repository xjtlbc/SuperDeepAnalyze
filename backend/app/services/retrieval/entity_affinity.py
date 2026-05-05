"""Entity affinity scoring using co-occurrence and Adamic-Adar.

Inspired by LLM Wiki's 4-signal knowledge graph relevance scoring.
Computes entity affinity based on document co-occurrence and
common neighbor analysis.
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

import networkx as nx

from app.config import settings
from app.utils.logging_config import get_logger

logger = get_logger("app.retrieval.entity_affinity")


class EntityAffinityScorer:
    """Score entity affinity based on co-occurrence patterns."""

    def __init__(self, kb_id: str):
        self._kb_id = kb_id
        self._cooccurrence: dict[tuple[str, str], int] = defaultdict(int)
        self._entity_docs: dict[str, set[str]] = defaultdict(set)
        self._graph: Optional[nx.Graph] = None
        self._loaded = False

    def _load(self) -> None:
        """Lazy-load co-occurrence data from L1 summaries."""
        if self._loaded:
            return
        self._loaded = True

        # Build co-occurrence from L1 summaries
        docs_dir = settings.KB_DIR / self._kb_id / "documents"
        if not docs_dir.exists():
            return

        for doc_dir in docs_dir.iterdir():
            if not doc_dir.is_dir():
                continue
            doc_id = doc_dir.name
            l1_path = doc_dir / "l1_summaries.json"
            if not l1_path.exists():
                continue

            try:
                with open(l1_path, "r", encoding="utf-8") as f:
                    summaries = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            for summary in summaries:
                raw_entities = summary.get("entities_mentioned", [])
                entities = [e if isinstance(e, str) else e.get("name", "") for e in raw_entities]
                entities = [e for e in entities if e]
                for entity in entities:
                    self._entity_docs[entity].add(doc_id)

                # Build co-occurrence pairs
                for i, e1 in enumerate(entities):
                    for e2 in entities[i + 1:]:
                        pair = tuple(sorted([e1, e2]))
                        self._cooccurrence[pair] += 1

        # Build graph from co-occurrence
        self._graph = nx.Graph()
        for (e1, e2), count in self._cooccurrence.items():
            if count >= 1:
                self._graph.add_edge(e1, e2, weight=count)

    def get_affinity(self, entity1: str, entity2: str) -> float:
        """Get affinity score between two entities (0.0 - 1.0)."""
        self._load()

        if not self._graph:
            return 0.0

        # Direct co-occurrence
        if self._graph.has_edge(entity1, entity2):
            weight = self._graph.edges[entity1, entity2]["weight"]
            # Normalize: weight 1 = 0.3, weight 5+ = 0.8
            score = min(0.3 + weight * 0.1, 0.8)
        else:
            score = 0.0

        # Adamic-Adar score for common neighbors
        try:
            if entity1 in self._graph and entity2 in self._graph:
                aa_score = next(nx.adamic_adar_index(
                    self._graph, [(entity1, entity2)]
                ))[2]
                if aa_score > 0:
                    score = max(score, min(aa_score / 5.0, 0.6))
        except (StopIteration, ZeroDivisionError):
            pass

        # Source overlap (shared documents)
        docs1 = self._entity_docs.get(entity1, set())
        docs2 = self._entity_docs.get(entity2, set())
        if docs1 and docs2:
            overlap = len(docs1 & docs2) / min(len(docs1), len(docs2))
            score = max(score, overlap * 0.7)

        return min(score, 1.0)

    def boost_results(
        self, results: list[dict], query_entities: list[str]
    ) -> list[dict]:
        """Boost search results that contain entities with high affinity to query entities."""
        self._load()

        if not query_entities or not self._graph:
            return results

        for result in results:
            # Extract entities mentioned in result
            content = str(result.get("content", "")) + str(result.get("summary", ""))
            result_entities = []
            for entity in self._entity_docs:
                if entity in content:
                    result_entities.append(entity)

            # Calculate max affinity
            max_affinity = 0.0
            for qe in query_entities:
                for re_ent in result_entities:
                    aff = self.get_affinity(qe, re_ent)
                    max_affinity = max(max_affinity, aff)

            # Apply boost to score
            if max_affinity > 0:
                base_score = result.get("relevance_score", result.get("score", result.get("rrf_score", 0)))
                if isinstance(base_score, (int, float)):
                    result["affinity_boost"] = max_affinity
                    result["boosted_score"] = base_score * (1 + max_affinity * 0.3)

        return results
