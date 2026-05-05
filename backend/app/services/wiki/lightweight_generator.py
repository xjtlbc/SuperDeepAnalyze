"""Lightweight wiki generator using existing L0/L1 data without LLM extraction.

Builds wiki pages directly from entities.json, timeline.json, relations.json,
and L1 summaries — no additional LLM calls needed.
"""
import json
import logging
from pathlib import Path

from app.config import settings
from app.models.database import get_connection

logger = logging.getLogger("app.wiki.lightweight")


async def generate_wiki_lightweight(kb_id: str) -> dict:
    """Generate wiki pages and catalog from existing L0/L1 data.

    Returns {"status": "completed", "pages": int, "catalog": dict}
    """
    l0_dir = settings.KB_DIR / kb_id / "l0"
    wiki_dir = settings.KB_DIR / kb_id / "wiki"
    pages_dir = wiki_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    # Load L0 data
    entities = _load_json(l0_dir / "entities.json", [])
    timeline = _load_json(l0_dir / "timeline.json", [])
    relations = _load_json(l0_dir / "relations.json", [])
    event_graph = _load_json(l0_dir / "event_graph.json", {})

    # Build entity index by name
    entity_by_name: dict[str, dict] = {}
    for e in entities:
        entity_by_name[e["name"]] = e

    # Build relations index per entity
    entity_relations: dict[str, list[dict]] = {}
    for rel in relations:
        if isinstance(rel, dict):
            subj = rel.get("subject", "")
            obj = rel.get("object", "")
            pred = rel.get("predicate", rel.get("relation_type", "相关"))
            for name in (subj, obj):
                if name:
                    entity_relations.setdefault(name, []).append({
                        "related_to": obj if name == subj else subj,
                        "relation": pred,
                    })

    # Build timeline index per entity
    entity_timeline: dict[str, list[dict]] = {}
    for evt in timeline:
        participants = evt.get("participants", [])
        for p in participants:
            if isinstance(p, dict):
                pname = p.get("name", "")
            else:
                pname = str(p)
            if pname:
                entity_timeline.setdefault(pname, []).append({
                    "date": evt.get("date", evt.get("time", "")),
                    "title": evt.get("title", evt.get("description", ""))[:80],
                    "description": evt.get("description", "")[:200],
                })

    # ── Create entity pages ──
    page_count = 0
    entity_type_labels = {
        "person": "人物", "organization": "组织", "location": "地点",
        "event": "事件", "object": "物品", "evidence": "证据",
        "concept": "概念", "document": "文档",
    }

    for ent in entities:
        name = ent.get("name", "")
        etype = ent.get("type", "unknown")
        aliases = ent.get("aliases", [])
        attributes = ent.get("attributes", {})
        ent_id = ent.get("id", "")
        mentions = ent.get("mention_count", 1)
        type_label = entity_type_labels.get(etype, etype)

        # Build markdown content
        lines = [
            "---",
            f"type: {etype}",
            f"title: {name}",
            f"entity_id: {ent_id}",
            "---",
            "",
            f"# {name}",
            "",
            f"**类型**: {type_label}",
            f"**出现次数**: {mentions} 次",
        ]

        if aliases:
            lines.append(f"**别名**: {', '.join(aliases)}")

        if attributes:
            lines.append("")
            lines.append("## 属性")
            lines.append("")
            for k, v in attributes.items():
                lines.append(f"- **{k}**: {v}")

        # Relations section
        rels = entity_relations.get(name, [])
        if rels:
            lines.append("")
            lines.append(f"## 关联实体 ({len(rels)})")
            lines.append("")
            for r in rels[:20]:
                linked = r["related_to"]
                entity_page = _slugify(linked)
                lines.append(f"- → [[{entity_page}|{linked}]] ({r['relation']})")

        # Timeline section
        tl_events = entity_timeline.get(name, [])
        if tl_events:
            lines.append("")
            lines.append(f"## 时间线 ({len(tl_events)})")
            lines.append("")
            # Sort by date
            tl_events.sort(key=lambda e: e.get("date", ""))
            for evt in tl_events[:15]:
                d = evt.get("date", "")
                title = evt.get("title", "")
                lines.append(f"- **{d}** {title}")

        page_path = pages_dir / f"{_slugify(name)}.md"
        page_path.write_text("\n".join(lines), encoding="utf-8")
        page_count += 1

    # ── Build catalog ──
    entities_by_type: dict[str, list[dict]] = {}
    for e in entities:
        t = e.get("type", "unknown")
        entities_by_type.setdefault(t, []).append(e)

    catalog_children = []
    type_order = ["person", "organization", "location", "event", "object", "concept", "unknown"]
    for t in type_order:
        if t not in entities_by_type:
            continue
        type_label = entity_type_labels.get(t, t)
        type_children = []
        for e in entities_by_type[t][:20]:  # Top 20 per type
            type_children.append({
                "title": e["name"],
                "path": _slugify(e["name"]),
                "node_type": "page",
                "description": f"{type_label}: {e.get('mention_count', 1)} 次提及",
                "children": [],
            })
        catalog_children.append({
            "title": f"{type_label} ({len(entities_by_type[t])})",
            "path": f"type-{t}",
            "node_type": "category",
            "description": f"所有{type_label}类型实体",
            "children": type_children,
        })

    catalog = {
        "title": "知识库 Wiki",
        "path": "",
        "node_type": "category",
        "description": f"包含 {len(entities)} 个实体, {len(timeline)} 个时间线事件",
        "children": catalog_children,
    }

    with open(wiki_dir / "catalog.json", "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    # ── Save analysis report ──
    analysis = {
        "entities_count": len(entities),
        "timeline_count": len(timeline),
        "relations_count": len(relations),
        "type_counts": {t: len(el) for t, el in entities_by_type.items()},
        "contradictions": [],
        "knowledge_gaps": [],
        "narrative_threads": [],
    }
    with open(wiki_dir / "analysis_report.json", "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    logger.info("Lightweight wiki generated: %d pages, %d catalog categories", page_count, len(catalog_children))

    return {"status": "completed", "pages": page_count, "catalog_categories": len(catalog_children)}


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _slugify(name: str) -> str:
    """Create a URL-safe slug from a name."""
    import re
    # Keep Chinese chars, alphanumeric, and hyphens
    slug = re.sub(r"[^\w一-鿿-]", "-", name.strip())
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-") or "unknown"
