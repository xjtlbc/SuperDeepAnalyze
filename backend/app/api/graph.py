"""Graph data API."""

import json

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models.database import get_connection

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/{kb_id}")
async def get_graph_data(kb_id: str):
    """Get graph data for force-directed visualization."""
    entities_path = settings.KB_DIR / kb_id / "l0" / "entities.json"
    timeline_path = settings.KB_DIR / kb_id / "l0" / "timeline.json"
    graph_path = settings.KB_DIR / kb_id / "l0" / "event_graph.json"

    nodes = []
    edges = []

    # Load entities as nodes
    if entities_path.exists():
        with open(entities_path, "r", encoding="utf-8") as f:
            entities = json.load(f)
        type_colors = {
            "person": "#6366f1",
            "organization": "#f59e0b",
            "location": "#10b981",
            "event": "#ef4444",
            "unknown": "#8b5cf6",
        }
        for e in entities:
            nodes.append({
                "id": e["id"],
                "label": e["name"],
                "type": e.get("type", "unknown"),
                "color": type_colors.get(e.get("type", "unknown"), "#8b5cf6"),
                "aliases": e.get("aliases", []),
                "attributes": e.get("attributes", {}),
            })
            # Add edges for relations
            for rel in e.get("relations", []):
                edges.append({
                    "source": e["id"],
                    "target": rel,
                    "label": e.get("type", "related"),
                })

    # Load timeline events as nodes
    if timeline_path.exists():
        with open(timeline_path, "r", encoding="utf-8") as f:
            events = json.load(f)
        for ev in events:
            nodes.append({
                "id": ev["id"],
                "label": ev.get("time", "")[:10] + " " + ev.get("description", "")[:30],
                "type": "event",
                "color": "#ef4444",
                "time": ev.get("time", ""),
                "description": ev.get("description", ""),
                "participants": ev.get("participants", []),
            })
            # Connect events to participant entities
            for pid in ev.get("participants", []):
                edges.append({
                    "source": ev["id"],
                    "target": pid,
                    "label": "participant",
                })

    # Load event graph edges
    if graph_path.exists():
        with open(graph_path, "r", encoding="utf-8") as f:
            event_graph = json.load(f)
        for edge in event_graph.get("edges", []):
            edges.append({
                "source": edge.get("from", ""),
                "target": edge.get("to", ""),
                "label": edge.get("relation", ""),
            })

    return {"nodes": nodes, "edges": edges}


@router.get("/{kb_id}/entities/{entity_id}")
async def get_entity_detail(kb_id: str, entity_id: str):
    """Get detailed entity information."""
    entities_path = settings.KB_DIR / kb_id / "l0" / "entities.json"
    if not entities_path.exists():
        raise HTTPException(status_code=404, detail="No entity data found")

    with open(entities_path, "r", encoding="utf-8") as f:
        entities = json.load(f)

    entity = next((e for e in entities if e["id"] == entity_id), None)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Find L1 mentions
    l1_dir = settings.KB_DIR / kb_id / "documents"
    mentions = []
    if l1_dir.exists():
        for doc_dir in l1_dir.iterdir():
            l1_path = doc_dir / "l1_summaries.json"
            if l1_path.exists():
                with open(l1_path, "r", encoding="utf-8") as f:
                    summaries = json.load(f)
                    for s in summaries:
                        if entity["name"] in s.get("entities_mentioned", []):
                            mentions.append({
                                "doc_id": doc_dir.name,
                                "chunk_ids": s.get("chunk_ids", []),
                                "summary": s.get("summary", ""),
                            })

    entity["mentions"] = mentions
    return entity
