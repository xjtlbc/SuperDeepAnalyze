"""Wiki page file storage."""

from __future__ import annotations
import json
from pathlib import Path
from app.config import settings


def save_page(kb_id: str, catalog_path: str, content: str, frontmatter: dict) -> Path:
    """Save a wiki page to filesystem."""
    wiki_dir = settings.KB_DIR / kb_id / "wiki" / "pages"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    safe_name = catalog_path.replace("/", "_").replace("\\", "_")
    page_path = wiki_dir / f"{safe_name}.md"

    page_path.write_text(content, encoding="utf-8")

    # Also save metadata to SQLite
    from app.models.database import get_connection
    import uuid
    conn = get_connection()
    try:
        page_id = str(uuid.uuid4())[:8]
        conn.execute(
            """INSERT OR REPLACE INTO wiki_pages
               (id, kb_id, catalog_path, title, page_type, content, frontmatter, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'completed')""",
            (
                page_id, kb_id, catalog_path,
                frontmatter.get("title", ""), frontmatter.get("type", ""),
                content, json.dumps(frontmatter, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return page_path


def load_page(kb_id: str, catalog_path: str) -> str | None:
    """Load a wiki page from filesystem."""
    wiki_dir = settings.KB_DIR / kb_id / "wiki" / "pages"
    safe_name = catalog_path.replace("/", "_").replace("\\", "_")
    page_path = wiki_dir / f"{safe_name}.md"

    if not page_path.exists():
        return None
    return page_path.read_text(encoding="utf-8")


def list_pages(kb_id: str) -> list[dict]:
    """List all wiki pages for a KB."""
    wiki_dir = settings.KB_DIR / kb_id / "wiki" / "pages"
    if not wiki_dir.exists():
        return []

    pages = []
    for f in wiki_dir.glob("*.md"):
        content = f.read_text(encoding="utf-8")
        fm = {}
        if content.startswith("---"):
            try:
                end = content.index("---", 3)
                import yaml
                fm = yaml.safe_load(content[3:end]) or {}
            except (ValueError, Exception):
                pass
        pages.append({
            "path": f.stem,
            "title": fm.get("title", f.stem),
            "type": fm.get("type", "unknown"),
            "frontmatter": fm,
        })
    return pages
