"""Graph structure retrieval for knowledge graph queries."""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import re

from app.config import settings
from app.models.database import get_connection


class GraphSearcher:
    """Knowledge graph-based retrieval."""

    def __init__(self, kb_id: str):
        self.kb_id = kb_id
        self._entities: Optional[List[Dict]] = None
        self._timeline: Optional[List[Dict]] = None
        self._event_graph: Optional[Dict] = None

    def _load_entities(self) -> List[Dict]:
        """Load entities from L0."""
        if self._entities is not None:
            return self._entities

        entities_path = settings.KB_DIR / self.kb_id / "l0" / "entities.json"
        if entities_path.exists():
            with open(entities_path, "r", encoding="utf-8") as f:
                self._entities = json.load(f)
        else:
            self._entities = []
        return self._entities

    def _load_timeline(self) -> List[Dict]:
        """Load timeline from L0."""
        if self._timeline is not None:
            return self._timeline

        timeline_path = settings.KB_DIR / self.kb_id / "l0" / "timeline.json"
        if timeline_path.exists():
            with open(timeline_path, "r", encoding="utf-8") as f:
                self._timeline = json.load(f)
        else:
            self._timeline = []
        return self._timeline

    def _load_event_graph(self) -> Dict:
        """Load event graph from L0."""
        if self._event_graph is not None:
            return self._event_graph

        graph_path = settings.KB_DIR / self.kb_id / "l0" / "event_graph.json"
        if graph_path.exists():
            with open(graph_path, "r", encoding="utf-8") as f:
                self._event_graph = json.load(f)
        else:
            self._event_graph = {"nodes": [], "edges": []}
        return self._event_graph

    def search_entity_relations(
        self,
        entity_name: str,
        relation_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for all relations involving a specific entity.

        Args:
            entity_name: Name of the entity to search
            relation_type: Optional filter by relation type

        Returns:
            List of relation dicts with entity info
        """
        entities = self._load_entities()
        event_graph = self._load_event_graph()

        # Find the entity
        entity = next(
            (e for e in entities if e.get('name', '').lower() == entity_name.lower()),
            None
        )
        if not entity:
            # Try partial match
            entity = next(
                (e for e in entities if entity_name.lower() in e.get('name', '').lower()),
                None
            )

        results = []

        # Search edges involving this entity
        edges = event_graph.get('edges', [])
        entity_id = entity.get('id') if entity else None

        for edge in edges:
            # Check if entity is involved in this edge
            if entity_id and (edge.get('source') == entity_id or edge.get('target') == entity_id):
                if relation_type and edge.get('type') != relation_type:
                    continue
                results.append({
                    "entity": entity,
                    "relation": edge,
                    "is_source": edge.get('source') == entity_id,
                })

        return results

    def search_connected_entities(
        self,
        entity_id: str,
        depth: int = 1
    ) -> List[Dict[str, Any]]:
        """Search for entities connected to a given entity.

        Args:
            entity_id: ID of the entity
            depth: Connection depth (1=direct, 2=secondary)

        Returns:
            List of connected entities with relationship info
        """
        entities = self._load_entities()
        event_graph = self._load_event_graph()

        # Build adjacency list
        edges = event_graph.get('edges', [])
        adjacency: Dict[str, List[Dict]] = {}

        for edge in edges:
            source = edge.get('source')
            target = edge.get('target')
            if source and target:
                if source not in adjacency:
                    adjacency[source] = []
                if target not in adjacency:
                    adjacency[target] = []
                adjacency[source].append({"node": target, "edge": edge})
                adjacency[target].append({"node": source, "edge": edge})

        # BFS to find connected entities
        visited = set()
        queue = [(entity_id, 0)]
        results = []
        entity_map = {e.get('id'): e for e in entities}

        while queue:
            current_id, current_depth = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)

            if current_depth > 0:  # Don't include the starting entity
                entity = entity_map.get(current_id)
                if entity:
                    results.append({
                        "entity": entity,
                        "depth": current_depth,
                    })

            if current_depth < depth and current_id in adjacency:
                for neighbor in adjacency[current_id]:
                    if neighbor["node"] not in visited:
                        queue.append((neighbor["node"], current_depth + 1))

        return results

    def search_by_type(self, entity_type: str) -> List[Dict[str, Any]]:
        """Search entities by type.

        Args:
            entity_type: Type of entity (person, organization, location, etc.)

        Returns:
            List of matching entities
        """
        entities = self._load_entities()
        return [
            e for e in entities
            if e.get('type', '').lower() == entity_type.lower()
        ]

    def search_timeline_events(
        self,
        entity_ids: Optional[List[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search timeline events, optionally filtered by entities and time range.

        Args:
            entity_ids: Optional list of entity IDs to filter
            start_time: Optional start time (ISO format or partial)
            end_time: Optional end time (ISO format or partial)

        Returns:
            List of timeline events
        """
        timeline = self._load_timeline()
        results = []

        for event in timeline:
            # Filter by entity IDs
            if entity_ids:
                event_entities = event.get('entity_ids', [])
                if not any(eid in entity_ids for eid in event_entities):
                    continue

            # Filter by time range
            event_time = event.get('time', '')
            if start_time and event_time < start_time:
                continue
            if end_time and event_time > end_time:
                continue

            results.append(event)

        return results

    def search_path(self, from_entity: str, to_entity: str) -> List[Dict[str, Any]]:
        """Search for relationship path between two entities.

        Args:
            from_entity: Starting entity name or ID
            to_entity: Target entity name or ID

        Returns:
            List representing the path of relationships
        """
        entities = self._load_entities()
        event_graph = self._load_event_graph()

        # Resolve entity IDs
        def resolve_entity(name_or_id: str) -> Optional[str]:
            for e in entities:
                if e.get('id') == name_or_id:
                    return e.get('id')
                if e.get('name', '').lower() == name_or_id.lower():
                    return e.get('id')
            return None

        from_id = resolve_entity(from_entity)
        to_id = resolve_entity(to_entity)

        if not from_id or not to_id:
            return []

        # Build adjacency list
        edges = event_graph.get('edges', [])
        adjacency: Dict[str, List[Dict]] = {}

        for edge in edges:
            source = edge.get('source')
            target = edge.get('target')
            if source and target:
                if source not in adjacency:
                    adjacency[source] = []
                if target not in adjacency:
                    adjacency[target] = []
                adjacency[source].append({"node": target, "edge": edge})
                adjacency[target].append({"node": source, "edge": edge})

        # BFS to find shortest path
        visited = {from_id}
        queue = [(from_id, [])]

        while queue:
            current_id, path = queue.pop(0)

            if current_id == to_id:
                return path

            if current_id in adjacency:
                for neighbor in adjacency[current_id]:
                    if neighbor["node"] not in visited:
                        visited.add(neighbor["node"])
                        new_path = path + [{
                            "from": current_id,
                            "to": neighbor["node"],
                            "relation": neighbor["edge"],
                        }]
                        queue.append((neighbor["node"], new_path))

        return []  # No path found


def extract_entity_name(query: str) -> str:
    """Extract entity name from a natural language query.

    Args:
        query: Natural language query containing entity name

    Returns:
        Extracted entity name
    """
    # Try to extract quoted names first
    quoted = re.search(r'["\']([^"\']+)["\']', query)
    if quoted:
        return quoted.group(1)

    # Try to extract names after keywords
    patterns = [
        r'(?:实体|人物|组织|地点|公司)["\s:]*([^\s，。]+)',
        r'([^\s，。]+)(?:的|之)(?:关系|关联)',
    ]
    for pattern in patterns:
        match = re.search(pattern, query)
        if match:
            return match.group(1)

    # Fallback: return the longest word-like sequence
    words = re.findall(r'[一-鿿]+|[a-zA-Z]+', query)
    return max(words, key=len) if words else query


def extract_entities(query: str) -> List[str]:
    """Extract multiple entity names from a query.

    Args:
        query: Natural language query containing multiple entities

    Returns:
        List of extracted entity names
    """
    # Try to extract from patterns like "A和B的关系" or "A到B的路径"
    patterns = [
        r'([^\s，。]+)(?:和|与|跟|同)([^\s，。]+)',
        r'([^\s，。]+)(?:到|至|->)([^\s，。]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, query)
        if match:
            return [match.group(1), match.group(2)]

    # Fallback: extract all word-like sequences
    words = re.findall(r'[一-鿿]+|[a-zA-Z]+', query)
    return words[:2] if len(words) >= 2 else words


async def graph_search(
    kb_id: str,
    query: str,
    search_type: str = 'relations'
) -> List[Dict[str, Any]]:
    """Graph structure retrieval tool.

    Args:
        kb_id: Knowledge base ID
        query: Natural language query
        search_type: Type of search (relations, connected, path, type, timeline)

    Returns:
        List of graph search results
    """
    searcher = GraphSearcher(kb_id)

    # Determine search type from query content
    query_lower = query.lower()

    if search_type == 'path' or '路径' in query or '到' in query:
        # Extract two entities for path search
        entities = extract_entities(query)
        if len(entities) >= 2:
            return searcher.search_path(entities[0], entities[1])
        return []

    elif search_type == 'connected' or '关联' in query or '连接' in query:
        entity_name = extract_entity_name(query)
        # First find the entity to get its ID
        entities = searcher._load_entities()
        entity = next(
            (e for e in entities if entity_name.lower() in e.get('name', '').lower()),
            None
        )
        if entity:
            depth = 2 if '二' in query or '深度' in query else 1
            return searcher.search_connected_entities(entity.get('id'), depth=depth)
        return []

    elif search_type == 'type' or '类型' in query or '所有' in query:
        # Extract entity type
        type_patterns = {
            '人物': 'person',
            '人物': 'person',
            '组织': 'organization',
            '公司': 'organization',
            '地点': 'location',
            '地点': 'location',
            '事件': 'event',
        }
        for cn_type, en_type in type_patterns.items():
            if cn_type in query:
                return searcher.search_by_type(en_type)
        return []

    elif search_type == 'timeline' or '时间' in query or '事件' in query:
        entity_name = extract_entity_name(query)
        entities = searcher._load_entities()
        entity = next(
            (e for e in entities if entity_name.lower() in e.get('name', '').lower()),
            None
        )
        entity_ids = [entity.get('id')] if entity else None
        return searcher.search_timeline_events(entity_ids=entity_ids)

    else:  # Default: relations search
        entity_name = extract_entity_name(query)
        relation_type = None
        if '关系类型' in query:
            rt_match = re.search(r'关系类型["\s:]*([^\s，。]+)', query)
            if rt_match:
                relation_type = rt_match.group(1)
        return searcher.search_entity_relations(entity_name, relation_type)