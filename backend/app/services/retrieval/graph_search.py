"""Graph-based entity relationship search using NetworkX.

Replaces the crude string matching in ProgressiveSearchTool's L0 search
with proper graph traversal on the entity relationship graph.
"""

import json
from pathlib import Path
from typing import Optional

import networkx as nx

from app.config import settings
from app.utils.logging_config import get_logger

logger = get_logger("app.retrieval.graph_search")


class EntityGraphSearch:
    """Search the L0 entity relationship graph using NetworkX."""

    def __init__(self, kb_id: str):
        self._kb_id = kb_id
        self._graph: Optional[nx.Graph] = None
        self._entities_by_name: dict[str, dict] = {}
        self._entities_by_id: dict[str, dict] = {}

    def _load(self) -> None:
        """Lazy-load the entity graph from L0 data."""
        if self._graph is not None:
            return

        self._graph = nx.Graph()
        l0_dir = settings.KB_DIR / self._kb_id / "l0"
        entities_path = l0_dir / "entities.json"

        if not entities_path.exists():
            return

        with open(entities_path, "r", encoding="utf-8") as f:
            entities = json.load(f)

        for entity in entities:
            eid = entity.get("id", "")
            name = entity.get("name", "")
            etype = entity.get("type", "")

            # Add node with full entity data
            self._graph.add_node(eid, **entity)
            self._entities_by_id[eid] = entity
            if name:
                self._entities_by_name[name] = entity

            # Add edges from relations
            for rel in entity.get("relations", []):
                target_id = rel.get("target_id", "")
                if target_id and target_id != eid:
                    self._graph.add_edge(
                        eid, target_id,
                        relation_type=rel.get("type", ""),
                        confidence=rel.get("confidence", 0.5),
                        description=rel.get("description", ""),
                    )

    def find_entity(self, name: str) -> Optional[dict]:
        """Find an entity by name (exact or fuzzy match)."""
        self._load()

        # Exact match
        if name in self._entities_by_name:
            return self._entities_by_name[name]

        # Fuzzy: contains
        for ename, entity in self._entities_by_name.items():
            if name in ename or ename in name:
                return entity

        # ID match
        if name in self._entities_by_id:
            return self._entities_by_id[name]

        return None

    def get_neighbors(self, entity_id: str, max_depth: int = 1) -> list[dict]:
        """Get neighboring entities with their relationships."""
        self._load()

        if not self._graph or entity_id not in self._graph:
            return []

        if max_depth == 1:
            # Direct neighbors
            results = []
            for neighbor in self._graph.neighbors(entity_id):
                edge_data = self._graph.edges[entity_id, neighbor]
                node_data = self._graph.nodes[neighbor]
                results.append({
                    "entity_id": neighbor,
                    "entity_name": node_data.get("name", neighbor),
                    "entity_type": node_data.get("type", ""),
                    "relation_type": edge_data.get("relation_type", ""),
                    "confidence": edge_data.get("confidence", 0),
                    "description": edge_data.get("description", ""),
                })
            return results

        # BFS for deeper search
        results = []
        visited = {entity_id}
        queue = [(entity_id, 0)]

        while queue:
            current, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            for neighbor in self._graph.neighbors(current):
                if neighbor in visited:
                    continue
                visited.add(neighbor)

                edge_data = self._graph.edges[current, neighbor]
                node_data = self._graph.nodes[neighbor]
                results.append({
                    "entity_id": neighbor,
                    "entity_name": node_data.get("name", neighbor),
                    "entity_type": node_data.get("type", ""),
                    "relation_type": edge_data.get("relation_type", ""),
                    "confidence": edge_data.get("confidence", 0),
                    "description": edge_data.get("description", ""),
                    "distance": depth + 1,
                })
                queue.append((neighbor, depth + 1))

        return results

    def find_path(self, source_id: str, target_id: str) -> list[dict]:
        """Find the shortest relationship path between two entities."""
        self._load()

        if not self._graph:
            return []
        if source_id not in self._graph or target_id not in self._graph:
            return []

        try:
            path = nx.shortest_path(self._graph, source_id, target_id)
        except nx.NetworkXNoPath:
            return []

        # Build path with edge details
        result = []
        for i, node_id in enumerate(path):
            node_data = self._graph.nodes[node_id]
            step = {
                "entity_id": node_id,
                "entity_name": node_data.get("name", node_id),
                "entity_type": node_data.get("type", ""),
            }
            if i > 0:
                prev_id = path[i - 1]
                edge_data = self._graph.edges[prev_id, node_id]
                step["relation_from_previous"] = edge_data.get("relation_type", "")
                step["confidence"] = edge_data.get("confidence", 0)
            result.append(step)

        return result

    def search_entities(self, query: str, top_k: int = 10) -> list[dict]:
        """Search entities by matching query against names and descriptions."""
        self._load()

        if not self._graph:
            return []

        query_lower = query.lower()
        keywords = set(query_lower.split())

        scored = []
        for node_id in self._graph.nodes:
            node_data = self._graph.nodes[node_id]
            name = node_data.get("name", "").lower()
            description = node_data.get("description", "").lower()
            etype = node_data.get("type", "").lower()

            # Score: name match is highest
            score = 0.0
            for kw in keywords:
                if kw in name:
                    score += 3.0
                if kw in description:
                    score += 1.0
                if kw in etype:
                    score += 2.0

            # Also check direct substring
            if query_lower in name:
                score += 5.0
            if query_lower in description:
                score += 2.0

            if score > 0:
                scored.append((node_id, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for node_id, score in scored[:top_k]:
            node_data = self._graph.nodes[node_id]
            results.append({
                **node_data,
                "relevance_score": round(score / 10.0, 2),  # Normalize to 0-1
            })

        return results

    def get_subgraph(self, entity_ids: list[str]) -> dict:
        """Extract a subgraph containing the specified entities and their connections."""
        self._load()

        if not self._graph:
            return {"nodes": [], "edges": []}

        valid_ids = [eid for eid in entity_ids if eid in self._graph]
        if not valid_ids:
            return {"nodes": [], "edges": []}

        # Get induced subgraph
        sub = self._graph.subgraph(valid_ids).copy()

        # Also add direct neighbors
        for eid in list(valid_ids):
            for neighbor in self._graph.neighbors(eid):
                sub.add_node(neighbor, **self._graph.nodes[neighbor])
                if self._graph.has_edge(eid, neighbor):
                    sub.add_edge(eid, neighbor, **self._graph.edges[eid, neighbor])

        nodes = []
        for nid in sub.nodes:
            nd = sub.nodes[nid]
            nodes.append({
                "id": nid,
                "name": nd.get("name", nid),
                "type": nd.get("type", ""),
            })

        edges = []
        for u, v in sub.edges:
            ed = sub.edges[u, v]
            edges.append({
                "source": u,
                "target": v,
                "relation": ed.get("relation_type", ""),
                "confidence": ed.get("confidence", 0),
            })

        return {"nodes": nodes, "edges": edges}
