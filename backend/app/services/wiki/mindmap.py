"""Mind map generator for Wiki knowledge base visualization.

Generates a tree-structured JSON from the Wiki catalog for
frontend rendering with React Flow or D3.js.
"""

import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.utils.logging_config import get_logger

logger = get_logger("app.services.wiki.mindmap")


def generate_mindmap(kb_id: str) -> Optional[dict]:
    """Generate mind map data from the Wiki catalog.

    Returns a tree-structured dict suitable for React Flow / D3.js rendering:
    {
        "id": "root",
        "label": "案件全景",
        "children": [
            {
                "id": "cat_1",
                "label": "人物关系",
                "children": [
                    {"id": "page_1", "label": "张三及其关联人"},
                    ...
                ]
            },
            ...
        ]
    }
    """
    catalog_path = settings.KB_DIR / kb_id / "wiki" / "catalog.json"
    if not catalog_path.exists():
        logger.warning("Catalog not found for mindmap: %s", catalog_path)
        return None

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    # Convert catalog tree to mindmap tree
    mindmap = _catalog_to_mindmap(catalog, kb_id)

    # Save mindmap data
    mindmap_path = settings.KB_DIR / kb_id / "wiki" / "mindmap.json"
    mindmap_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mindmap_path, "w", encoding="utf-8") as f:
        json.dump(mindmap, f, ensure_ascii=False, indent=2)

    return mindmap


def _catalog_to_mindmap(catalog: dict, kb_id: str) -> dict:
    """Convert a catalog tree node to a mindmap node."""
    return {
        "id": catalog.get("path", "root").replace("/", "_") or "root",
        "label": catalog.get("title", "案件全景"),
        "type": catalog.get("node_type", "category"),
        "path": catalog.get("path", ""),
        "description": catalog.get("description", ""),
        "children": [
            _catalog_to_mindmap(child, kb_id)
            for child in catalog.get("children", [])
        ],
    }


def load_mindmap(kb_id: str) -> Optional[dict]:
    """Load saved mindmap data."""
    mindmap_path = settings.KB_DIR / kb_id / "wiki" / "mindmap.json"
    if not mindmap_path.exists():
        return generate_mindmap(kb_id)
    with open(mindmap_path, "r", encoding="utf-8") as f:
        return json.load(f)


def mindmap_to_flat_nodes(mindmap: dict) -> list[dict]:
    """Convert mindmap tree to a flat list of nodes for React Flow.

    Returns nodes with positions calculated by tree depth and sibling index.
    """
    nodes = []
    edges = []

    def _traverse(node: dict, x: int, y: int, x_offset: int, depth: int):
        node_id = node["id"]
        nodes.append({
            "id": node_id,
            "label": node["label"],
            "type": node.get("type", "category"),
            "path": node.get("path", ""),
            "x": x,
            "y": y,
            "depth": depth,
        })

        children = node.get("children", [])
        if not children:
            return

        child_y = y + 120
        total_width = len(children) * x_offset
        start_x = x - total_width // 2 + x_offset // 2

        for i, child in enumerate(children):
            child_x = start_x + i * x_offset
            edges.append({
                "source": node_id,
                "target": child["id"],
            })
            _traverse(child, child_x, child_y, max(x_offset // 2, 150), depth + 1)

    _traverse(mindmap, 0, 0, 400, 0)
    return {"nodes": nodes, "edges": edges}
