"""Wiki-style knowledge browsing API."""

import json
import logging

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models.database import get_connection

logger = logging.getLogger("app.wiki")
router = APIRouter(prefix="/api/wiki", tags=["wiki"])


def _check_kb_wiki_ready(kb_id: str) -> None:
    """Verify KB exists and has been compiled. Raises appropriate HTTP errors.

    404 = KB not found
    503 = KB exists but compilation not completed (wiki not available)
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT compile_status, wiki_status FROM knowledge_bases WHERE id = ?", (kb_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        if row["compile_status"] not in ("completed", "partial"):
            raise HTTPException(
                status_code=503,
                detail=f"Wiki not available — KB compilation status is '{row['compile_status']}'. Run compilation first.",
            )
    finally:
        conn.close()


@router.get("/{kb_id}/status")
async def get_wiki_status(kb_id: str):
    """Get Wiki generation status for a knowledge base."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT compile_status, wiki_status FROM knowledge_bases WHERE id = ?", (kb_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        return {
            "kb_id": kb_id,
            "compile_status": row["compile_status"],
            "wiki_status": row["wiki_status"],
        }
    finally:
        conn.close()


@router.get("/{kb_id}")
async def get_wiki_overview(kb_id: str):
    """Get structured wiki overview for a knowledge base."""
    _check_kb_wiki_ready(kb_id)

    l0_dir = settings.KB_DIR / kb_id / "l0"
    entities_path = l0_dir / "entities.json"
    timeline_path = l0_dir / "timeline.json"

    if not entities_path.exists() and not timeline_path.exists():
        raise HTTPException(status_code=404, detail="No wiki data found")

    # Get wiki_status from DB
    wiki_status = "pending"
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT wiki_status FROM knowledge_bases WHERE id = ?", (kb_id,)
        ).fetchone()
        if row:
            wiki_status = row["wiki_status"]
    finally:
        conn.close()

    wiki = {
        "entities": [],
        "entity_count": 0,
        "timeline_count": 0,
        "relation_count": 0,
        "contradiction_count": 0,
        "type_counts": {},
        "confidence_distribution": {"EXTRACTED": 0, "INFERRED": 0, "AMBIGUOUS": 0},
        "top_entities": [],
        "wiki_status": wiki_status,
    }

    if entities_path.exists():
        with open(entities_path, "r", encoding="utf-8") as f:
            entities = json.load(f)
        wiki["entities"] = [
            {
                "id": e["id"],
                "name": e["name"],
                "type": e.get("type", "unknown"),
                "aliases": e.get("aliases", []),
            }
            for e in entities
        ]
        wiki["entity_count"] = len(entities)
        # Count by type
        type_counts: dict[str, int] = {}
        for e in entities:
            t = e.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        wiki["type_counts"] = type_counts

        # Confidence distribution (EXTRACTED / INFERRED / AMBIGUOUS)
        for e in entities:
            conf = e.get("confidence", "")
            if conf in wiki["confidence_distribution"]:
                wiki["confidence_distribution"][conf] += 1

        # Top 10 entities by importance (fallback to confidence ordinal)
        conf_rank = {"EXTRACTED": 3, "INFERRED": 2, "AMBIGUOUS": 1}
        sorted_entities = sorted(
            entities,
            key=lambda e: (
                e.get("importance", 0),
                conf_rank.get(e.get("confidence", ""), 0),
            ),
            reverse=True,
        )[:10]
        wiki["top_entities"] = [
            {
                "id": e["id"],
                "name": e["name"],
                "type": e.get("type", "unknown"),
                "confidence": e.get("confidence", ""),
                "importance": e.get("importance", 0),
            }
            for e in sorted_entities
        ]

    # Load relation_count from top-level relations array
    relations_path = l0_dir / "relations.json"
    if relations_path.exists():
        with open(relations_path, "r", encoding="utf-8") as f:
            relations = json.load(f)
        wiki["relation_count"] = len(relations)

    # Load contradiction_count from cross_refs
    cross_refs_path = l0_dir / "cross_refs.json"
    if cross_refs_path.exists():
        with open(cross_refs_path, "r", encoding="utf-8") as f:
            cross_refs = json.load(f)
        wiki["contradiction_count"] = sum(
            1 for cr in cross_refs if cr.get("contradiction") is True
        )

    if timeline_path.exists():
        with open(timeline_path, "r", encoding="utf-8") as f:
            events = json.load(f)
        wiki["timeline_count"] = len(events)

    return wiki


@router.get("/{kb_id}/entity/{entity_id}")
async def get_wiki_entity(kb_id: str, entity_id: str):
    """Get entity wiki page with relations, mentions, and events."""
    l0_dir = settings.KB_DIR / kb_id / "l0"
    entities_path = l0_dir / "entities.json"

    if not entities_path.exists():
        raise HTTPException(status_code=404, detail="No entity data found")

    with open(entities_path, "r", encoding="utf-8") as f:
        entities = json.load(f)

    entity = next((e for e in entities if e["id"] == entity_id), None)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    result = {
        "id": entity["id"],
        "name": entity["name"],
        "type": entity.get("type", "unknown"),
        "aliases": entity.get("aliases", []),
        "attributes": entity.get("attributes", {}),
        "relations": entity.get("relations", []),
    }

    # Find timeline events involving this entity
    timeline_path = l0_dir / "timeline.json"
    if timeline_path.exists():
        with open(timeline_path, "r", encoding="utf-8") as f:
            events = json.load(f)
        # Handle both old (string list) and new (dict list) participant formats
        def _entity_in_participants(entity_name: str, participants: list) -> bool:
            for p in participants:
                if isinstance(p, str):
                    if p == entity_name:
                        return True
                elif isinstance(p, dict):
                    if p.get("name") == entity_name:
                        return True
            return False

        result["events"] = [
            ev for ev in events if _entity_in_participants(entity["name"], ev.get("participants", []))
        ]

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
                        em = s.get("entities_mentioned", [])
                        ent_names = [e if isinstance(e, str) else e.get("name", "") for e in em]
                        if entity["name"] in ent_names:
                            mentions.append({
                                "doc_id": doc_dir.name,
                                "chunk_ids": s.get("chunk_ids", []),
                                "summary": s.get("summary", ""),
                            })
    result["mentions"] = mentions

    return result


@router.get("/{kb_id}/timeline")
async def get_wiki_timeline(kb_id: str):
    """Get timeline events for wiki display."""
    l0_dir = settings.KB_DIR / kb_id / "l0"
    timeline_path = l0_dir / "timeline.json"

    if not timeline_path.exists():
        raise HTTPException(status_code=404, detail="No timeline data found")

    with open(timeline_path, "r", encoding="utf-8") as f:
        events = json.load(f)

    return {"events": events, "count": len(events)}


@router.get("/{kb_id}/types/{entity_type}")
async def get_entities_by_type(kb_id: str, entity_type: str):
    """Get entities filtered by type."""
    l0_dir = settings.KB_DIR / kb_id / "l0"
    entities_path = l0_dir / "entities.json"

    if not entities_path.exists():
        raise HTTPException(status_code=404, detail="No entity data found")

    with open(entities_path, "r", encoding="utf-8") as f:
        entities = json.load(f)

    filtered = [e for e in entities if e.get("type", "unknown") == entity_type]
    return {
        "type": entity_type,
        "entities": [
            {"id": e["id"], "name": e["name"], "aliases": e.get("aliases", [])}
            for e in filtered
        ],
        "count": len(filtered),
    }


@router.get("/{kb_id}/catalog")
async def get_wiki_catalog(kb_id: str):
    """Get wiki catalog tree."""
    from app.services.wiki.catalog.storage import load_catalog
    catalog = load_catalog(kb_id)
    if not catalog:
        raise HTTPException(status_code=404, detail="No catalog found")
    return catalog


@router.get("/{kb_id}/page")
async def get_wiki_page(kb_id: str, path: str):
    """Get a specific wiki page by catalog path."""
    from app.services.wiki.pages.storage import load_page
    content = load_page(kb_id, path)
    if not content:
        raise HTTPException(status_code=404, detail=f"Page not found: {path}")

    fm = {}
    body = content
    if content.startswith("---"):
        try:
            end = content.index("---", 3)
            import yaml
            fm = yaml.safe_load(content[3:end]) or {}
            body = content[end + 3:]
        except (ValueError, Exception):
            pass

    return {"frontmatter": fm, "content": body}


@router.get("/{kb_id}/pages")
async def list_wiki_pages(kb_id: str):
    """List all wiki pages."""
    from app.services.wiki.pages.storage import list_pages
    pages = list_pages(kb_id)
    return {"pages": pages, "count": len(pages)}


@router.get("/{kb_id}/analysis")
async def get_wiki_analysis(kb_id: str):
    """Get the analysis report."""
    from app.config import settings
    from fastapi.responses import JSONResponse
    wiki_dir = settings.KB_DIR / kb_id / "wiki"
    report_path = wiki_dir / "analysis_report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="No analysis report found")
    raw = report_path.read_text(encoding="utf-8")
    return JSONResponse(content=json.loads(raw))


@router.get("/{kb_id}/cross_refs")
async def get_cross_refs(kb_id: str):
    """Get cross-document contradictions from L0 cross_refs.json."""
    cross_refs_path = settings.KB_DIR / kb_id / "l0" / "cross_refs.json"
    if not cross_refs_path.exists():
        return {"cross_refs": []}

    with open(cross_refs_path, "r", encoding="utf-8") as f:
        cross_refs = json.load(f)

    # Build doc_id pattern -> doc_id mapping
    doc_patterns = {}
    docs_dir = settings.KB_DIR / kb_id / "documents"
    if docs_dir.exists():
        for doc_dir in docs_dir.iterdir():
            if not doc_dir.is_dir():
                continue
            doc_patterns[doc_dir.name] = doc_dir.name

    # Enrich cross refs with document info from source/target patterns
    for ref in cross_refs:
        source_doc = ref.get("source", "")
        target_doc = ref.get("target", "")
        src_doc_id = None
        tgt_doc_id = None
        for doc_id in doc_patterns:
            if source_doc.startswith(doc_id):
                src_doc_id = doc_id
            if target_doc.startswith(doc_id):
                tgt_doc_id = doc_id
        ref["source_doc"] = src_doc_id
        ref["target_doc"] = tgt_doc_id

    return {"cross_refs": cross_refs}


@router.get("/{kb_id}/source-lookup")
async def get_source_lookup(kb_id: str):
    """Build index mapping source citation patterns to document IDs."""
    lookup = {}
    docs_dir = settings.KB_DIR / kb_id / "documents"
    if not docs_dir.exists():
        return {"lookup": {}}

    for doc_dir in docs_dir.iterdir():
        if not doc_dir.is_dir():
            continue
        l1_path = doc_dir / "l1_summaries.json"
        if l1_path.exists():
            with open(l1_path, "r", encoding="utf-8") as f:
                l1_data = json.load(f)
            for i, entry in enumerate(l1_data):
                title = entry.get("summary", "")[:30]
                citation_key = f"doc-{doc_dir.name}-{i}"
                lookup[citation_key] = {
                    "doc_id": doc_dir.name,
                    "l1_index": i,
                    "summary_preview": title,
                }

    return {"lookup": lookup}


@router.post("/{kb_id}/generate")
async def trigger_wiki_generation(kb_id: str, mode: str = "lightweight"):
    """Manually trigger wiki generation (for re-generation).

    Args:
        mode: "lightweight" (fast, from L0 data) or "full" (LLM extraction + pages).
    """
    # Update status to generating
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE knowledge_bases SET wiki_status = 'generating' WHERE id = ?",
            (kb_id,),
        )
        conn.commit()
    finally:
        conn.close()

    try:
        if mode == "full":
            from app.models.crud import load_model_configs
            from app.models.router import ModelRouter
            from app.services.llm.client import LLMClient
            from app.services.wiki.pipeline import WikiPipeline

            db_configs = load_model_configs()
            if not db_configs:
                raise RuntimeError("No model configuration found")

            router_obj = ModelRouter()
            router_obj.register(db_configs)
            llm_client = LLMClient(router_obj)

            pipeline = WikiPipeline(llm_client, kb_id)
            result = await pipeline.run()
            result_dict = {"status": "completed", "result": str(result)}
        else:
            from app.services.wiki.lightweight_generator import generate_wiki_lightweight
            result_dict = await generate_wiki_lightweight(kb_id)

        conn = get_connection()
        try:
            conn.execute(
                "UPDATE knowledge_bases SET wiki_status = 'completed' WHERE id = ?",
                (kb_id,),
            )
            conn.commit()
        finally:
            conn.close()

        return {"kb_id": kb_id, **result_dict}
    except Exception as e:
        logger.error("Wiki generation failed for KB %s: %s", kb_id, e)
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE knowledge_bases SET wiki_status = 'failed' WHERE id = ?",
                (kb_id,),
            )
            conn.commit()
        finally:
            conn.close()
        raise HTTPException(status_code=500, detail=f"Wiki generation failed: {e}")


@router.get("/{kb_id}/surprises")
async def get_surprises(kb_id: str):
    """Get surprise detection results: rare entities, contradictions, temporal anomalies."""
    from app.services.wiki.analysis.surprise import detect_surprises
    return detect_surprises(kb_id)


@router.get("/{kb_id}/health")
async def get_wiki_health(kb_id: str):
    """Run wiki health check and return report."""
    from app.services.wiki.health_checker import WikiHealthChecker
    checker = WikiHealthChecker()
    report = checker.run_full_check(kb_id)
    return {
        "kb_id": report.kb_id,
        "score": report.score,
        "total_pages": report.total_pages,
        "total_entities": report.total_entities,
        "issues": {
            "orphan_pages": report.orphan_pages,
            "sparse_communities": report.sparse_communities,
            "broken_links": report.broken_links,
            "missing_relations": report.missing_relations,
        },
        "issue_count": (
            len(report.orphan_pages) + len(report.sparse_communities) +
            len(report.broken_links) + len(report.missing_relations)
        ),
    }


@router.get("/{kb_id}/search")
async def search_wiki(kb_id: str, q: str = "", limit: int = 20):
    """Search wiki pages and entities by keyword."""
    if not q or len(q.strip()) < 2:
        return {"results": [], "total": 0}

    query = q.strip()
    results = []

    # Search entities from L0
    entities_path = settings.KB_DIR / kb_id / "l0" / "entities.json"
    if entities_path.exists():
        with open(entities_path, "r", encoding="utf-8") as f:
            entities = json.load(f)
        for e in entities:
            name = e.get("name", "")
            aliases = e.get("aliases", [])
            attrs = e.get("attributes", {})
            if (query.lower() in name.lower() or
                any(query.lower() in a.lower() for a in aliases) or
                any(query.lower() in str(v).lower() for v in attrs.values())):
                results.append({
                    "type": "entity",
                    "id": e["id"],
                    "title": name,
                    "snippet": f"{e.get('type', '')} | aliases: {', '.join(aliases[:3])}",
                })

    # Search wiki pages from catalog
    catalog_path = settings.KB_DIR / kb_id / "wiki" / "catalog.json"
    if catalog_path.exists():
        with open(catalog_path, "r", encoding="utf-8") as f:
            catalog = json.load(f)
        _search_catalog_node(catalog, query, results)

    return {"results": results[:limit], "total": len(results)}


def _search_catalog_node(node: dict, query: str, results: list, depth: int = 0):
    """Recursively search catalog tree nodes."""
    if depth > 10:
        return
    title = node.get("title", "")
    desc = node.get("description", "")
    if query.lower() in title.lower() or query.lower() in desc.lower():
        results.append({
            "type": "page",
            "id": node.get("path", ""),
            "title": title,
            "snippet": desc[:100] if desc else "",
        })
    for child in node.get("children", []):
        _search_catalog_node(child, query, results, depth + 1)
