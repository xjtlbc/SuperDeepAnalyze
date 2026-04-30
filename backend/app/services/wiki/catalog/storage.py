"""Catalog tree storage to SQLite and filesystem."""

from __future__ import annotations
import json
from pathlib import Path
from app.config import settings


def save_catalog(kb_id: str, catalog_tree: dict) -> None:
    """Save catalog tree to both SQLite and filesystem."""
    kb_dir = settings.KB_DIR / kb_id
    wiki_dir = kb_dir / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    # Save to filesystem
    catalog_path = wiki_dir / "catalog.json"
    catalog_path.write_text(json.dumps(catalog_tree, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save to SQLite
    from app.models.database import get_connection
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM wiki_catalog WHERE kb_id = ?", (kb_id,))
        # Insert root node (parent_id is NULL for tree root)
        root_id = _save_node(conn, kb_id, catalog_tree, parent_id=None)
        conn.commit()
    finally:
        conn.close()


def _save_node(conn, kb_id: str, node: dict, parent_id: str | None) -> str:
    """Recursively save a catalog node. Returns the generated node_id."""
    import uuid
    node_id = str(uuid.uuid4())[:8]
    if parent_id is None:
        conn.execute(
            """INSERT INTO wiki_catalog (id, kb_id, title, path, parent_id, node_order, node_type, description)
               VALUES (?, ?, ?, ?, NULL, ?, ?, ?)""",
            (
                node_id, kb_id, node["title"], node.get("path", ""),
                node.get("order", 0), node.get("node_type", "page"),
                node.get("description", ""),
            ),
        )
    else:
        conn.execute(
            """INSERT INTO wiki_catalog (id, kb_id, title, path, parent_id, node_order, node_type, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                node_id, kb_id, node["title"], node.get("path", ""),
                parent_id, node.get("order", 0), node.get("node_type", "page"),
                node.get("description", ""),
            ),
        )
    for child in node.get("children", []):
        _save_node(conn, kb_id, child, parent_id=node_id)
    return node_id


def load_catalog(kb_id: str) -> dict | None:
    """Load catalog tree from filesystem (primary source)."""
    catalog_path = settings.KB_DIR / kb_id / "wiki" / "catalog.json"
    if not catalog_path.exists():
        return None
    return json.loads(catalog_path.read_text(encoding="utf-8"))


def get_leaf_pages(catalog_tree: dict) -> list[dict]:
    """Extract all leaf (page) nodes from catalog tree."""
    leaves = []
    def _walk(node, path=""):
        current_path = f"{path}/{node['path']}" if path else node["path"]
        children = node.get("children", [])
        if not children or node.get("node_type") == "page":
            leaves.append({**node, "full_path": current_path})
        else:
            for child in children:
                _walk(child, current_path)
    _walk(catalog_tree)
    return leaves
