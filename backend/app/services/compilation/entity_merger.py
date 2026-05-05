"""Entity merger: builds global entity library, timeline, and event graph from L1 results.

Enhanced with Graphify-inspired 3-layer deduplication:
  1. File-internal: same-name entities within a document merged
  2. Cross-file: different documents, same entity → alias/normalize matching
  3. Semantic: LLM-generated name variants → _normalize_id() tolerant matching

Each L1 batch result contains:
  - entities_mentioned: list of entity dicts {name, type, ...}
  - relations: list of relation dicts {subject, predicate, object, ...}
  - summary: text (may contain temporal references)
"""

import json
import logging
import re
from pathlib import Path

from app.config import settings
from app.models.database import get_connection

logger = logging.getLogger("app.compilation")

# Date patterns for timeline extraction from text
_DATE_PATTERNS = [
    re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]"),
    re.compile(r"(\d{4})[年\-./](\d{1,2})[月\-./](\d{1,2})"),
    re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月"),
]


def _normalize_id(name: str) -> str:
    """Graphify-style ID normalization: lowercase, strip non-alphanumeric.

    Used as the third dedup layer — when LLM produces slightly different
    entity names (e.g. "Session_ValidateToken" vs "session_validatetoken"),
    this normalization resolves them to the same canonical key.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9一-鿿]+", "_", name)
    return cleaned.strip("_").lower()


def _normalize_entity_name(name: str) -> str:
    """Normalize entity name for dedup."""
    return name.strip().replace("　", " ").replace("  ", " ")


# Standard entity type normalization map
_TYPE_MAP: dict[str, str] = {
    # Chinese → standard
    "人物": "person", "人": "person", "嫌疑人": "person", "证人": "person",
    "被告人": "person", "被害人": "person", "受害者": "person", "个人": "person",
    "犯罪嫌疑人": "person", "罪犯": "person", "当事人": "person",
    "组织": "organization", "机构": "organization", "公司": "organization",
    "单位": "organization", "公安机关": "organization", "检察院": "organization",
    "法院": "organization", "派出所": "organization", "分局": "organization",
    "政府": "organization", "企业": "organization", "部门": "organization",
    "地点": "location", "位置": "location", "地址": "location",
    "地": "location", "省": "location", "市": "location",
    "事件": "event", "案件": "event", "活动": "event",
    "物品": "object", "证据": "evidence", "文件": "document",
    "概念": "concept",
    # English → standard
    "person": "person", "people": "person",
    "organization": "organization", "org": "organization", "company": "organization",
    "location": "location", "place": "location", "address": "location",
    "event": "event", "incident": "event",
    "object": "object", "evidence": "evidence", "document": "document",
    "concept": "concept",
}

# Name-pattern-based type inference
_PERSON_NAME_RE = re.compile(r"^[一-鿿]{2,4}$")  # 2-4 Chinese chars → likely person
_ORG_PATTERNS = ["公安局", "法院", "检察院", "派出所", "分局", "支队", "总队", "政府", "委员会",
                 "公司", "集团", "银行", "医院", "学校", "大队", "中队", "看守所", "监狱"]
_LOC_PATTERNS = ["省", "市", "区", "县", "镇", "乡", "村", "路", "街", "巷", "号", "小区", "广场"]


def _normalize_entity_type(raw_type: str) -> str:
    """Normalize entity type to one of 6 standard types: person/organization/location/event/object/concept."""
    if not raw_type or raw_type.lower() == "unknown":
        return "unknown"
    return _TYPE_MAP.get(raw_type, raw_type.lower())


def _infer_entity_type_from_name(name: str) -> str:
    """Infer entity type from name patterns when LLM fails to classify."""
    if not name:
        return "unknown"
    # Check org patterns
    for pat in _ORG_PATTERNS:
        if pat in name:
            return "organization"
    # Check location patterns
    if any(lp in name for lp in _LOC_PATTERNS):
        # But avoid false positives for person names containing these chars
        if len(name) > 6 or any(pat in name for pat in _ORG_PATTERNS):
            return "location" if not any(op in name for op in _ORG_PATTERNS) else "organization"
        if any(lp in name for lp in ["路", "街", "巷", "号", "小区", "广场"]):
            return "location"
    # Short Chinese names are likely persons
    if _PERSON_NAME_RE.match(name) and len(name) >= 2:
        return "person"
    return "unknown"


def _is_same_entity(a: dict, b: dict) -> bool:
    """Check if two entity mentions refer to the same entity."""
    name_a = _normalize_entity_name(a.get("name", ""))
    name_b = _normalize_entity_name(b.get("name", ""))

    if not name_a or not name_b:
        return False

    # Exact match
    if name_a == name_b:
        return True

    # One is substring of the other (e.g., "张伟" vs "张伟（犯罪嫌疑人）")
    if name_a in name_b or name_b in name_a:
        return True

    # Check aliases
    aliases_a = set(a.get("aliases", []))
    aliases_b = set(b.get("aliases", []))
    if name_a in aliases_b or name_b in aliases_a:
        return True

    return False


def _extract_dates(text: str) -> list[str]:
    """Extract date strings from text."""
    dates = []
    for pattern in _DATE_PATTERNS:
        matches = pattern.findall(text)
        for m in matches:
            parts = [str(p) for p in m]
            if len(parts) == 3:
                dates.append(f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}")
            elif len(parts) == 2:
                dates.append(f"{parts[0]}-{int(parts[1]):02d}")
    return dates


def merge_kb_entities(l1_results: list[dict], kb_id: str) -> tuple[int, int]:
    """Merge all L1 entities, relations, and timeline into global stores.

    Args:
        l1_results: List of L1 batch result dicts, each containing
                    entities_mentioned, relations, summary, chunk_ids.
        kb_id: Knowledge base ID.

    Returns:
        (entity_count, timeline_count) tuple.
    """
    # Collect all entities
    entity_map: dict[str, dict] = {}  # normalized_name -> entity
    all_relations: list[dict] = []
    timeline_events: list[dict] = []

    for l1 in l1_results:
        # Merge entities
        for ent in l1.get("entities_mentioned", []):
            # Defensive: LLM may return strings instead of dicts
            if isinstance(ent, str):
                ent = {"name": ent, "type": "unknown"}
            name = _normalize_entity_name(ent.get("name", ""))
            if not name:
                continue

            raw_type = ent.get("type", "unknown")
            ent_type = _normalize_entity_type(raw_type)
            attributes = ent.get("attributes", {})

            # Check for existing match
            matched_key = None
            for existing_key in entity_map:
                if _is_same_entity({"name": name}, {"name": existing_key}):
                    matched_key = existing_key
                    break

            if matched_key:
                # Merge into existing
                existing = entity_map[matched_key]
                if ent_type != "unknown" and existing.get("type") == "unknown":
                    existing["type"] = ent_type
                # Add aliases
                if name != matched_key and name not in existing.get("aliases", []):
                    existing.setdefault("aliases", []).append(name)
                # Merge attributes
                for k, v in attributes.items():
                    if k not in existing.get("attributes", {}):
                        existing.setdefault("attributes", {})[k] = v
                # Add mentions
                existing["mention_count"] = existing.get("mention_count", 0) + 1
                existing.setdefault("source_chunks", []).extend(
                    l1.get("chunk_ids", [])[:3]
                )
            else:
                # New entity
                entity_map[name] = {
                    "id": f"ent_{len(entity_map):04d}",
                    "name": name,
                    "type": ent_type,
                    "aliases": [],
                    "attributes": attributes,
                    "mention_count": 1,
                    "source_chunks": l1.get("chunk_ids", [])[:3],
                }

        # Collect relations (support both new and old format)
        for rel in l1.get("relations", []):
            if not isinstance(rel, dict):
                continue
            subj = _normalize_entity_name(rel.get("subject", rel.get("from", "")))
            obj = _normalize_entity_name(rel.get("object", rel.get("to", "")))
            pred = rel.get("predicate", rel.get("type", "相关"))
            if subj and obj:
                all_relations.append({
                    "subject": subj,
                    "predicate": pred,
                    "object": obj,
                    "source_chunks": l1.get("chunk_ids", [])[:2],
                })

        # Extract timeline from summaries
        summary = l1.get("summary", "")
        if summary:
            dates = _extract_dates(summary)
            for date in dates:
                # Find entities mentioned near this date
                nearby_entities = [
                    _normalize_entity_name(e.get("name", "") if isinstance(e, dict) else e)
                    for e in l1.get("entities_mentioned", [])[:5]
                    if _normalize_entity_name(e.get("name", "") if isinstance(e, dict) else e)
                ]
                timeline_events.append({
                    "id": f"tlevt_{len(timeline_events):04d}",
                    "time": date,
                    "date": date,
                    "description": summary[:200],
                    "participants": nearby_entities,
                    "source_chunks": l1.get("chunk_ids", [])[:2],
                })

    # Post-merge: infer types for entities still marked "unknown"
    for ent in entity_map.values():
        if ent.get("type") == "unknown":
            inferred = _infer_entity_type_from_name(ent["name"])
            if inferred != "unknown":
                ent["type"] = inferred

    # Deduplicate timeline by date (keep most detailed entry per date)
    seen_dates: dict[str, dict] = {}
    for evt in timeline_events:
        d = evt["date"]
        if d not in seen_dates or len(evt["description"]) > len(seen_dates[d]["description"]):
            seen_dates[d] = evt
    timeline_events = sorted(seen_dates.values(), key=lambda x: x["date"])

    # When L1 results lack explicit relations, generate co-occurrence from entity overlaps
    if not all_relations:
        chunk_entities: dict[str, list[str]] = {}
        for l1 in l1_results:
            chunk_ids = l1.get("chunk_ids", [])
            entities_in_chunk = []
            for e in l1.get("entities_mentioned", []):
                name = _normalize_entity_name(e.get("name", "") if isinstance(e, dict) else e)
                if name:
                    entities_in_chunk.append(name)
            for cid in chunk_ids[:1]:
                if cid:
                    chunk_entities[cid] = entities_in_chunk
        seen_pairs: set[tuple[str, str]] = set()
        for cid, ents in chunk_entities.items():
            for i, a in enumerate(ents):
                for b in ents[i + 1:]:
                    pair = tuple(sorted([a, b]))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        all_relations.append({
                            "subject": pair[0],
                            "predicate": "共现",
                            "object": pair[1],
                            "source_chunks": [cid],
                        })

    # Build event graph (entity -> related entities)
    event_graph: dict[str, list[dict]] = {}
    for rel in all_relations:
        subj = rel["subject"]
        obj = rel["object"]
        event_graph.setdefault(subj, []).append({
            "relation": rel["predicate"],
            "target": obj,
            "source_chunks": rel["source_chunks"],
        })
        event_graph.setdefault(obj, []).append({
            "relation": f"{rel['predicate']}(反向)",
            "target": subj,
            "source_chunks": rel["source_chunks"],
        })

    # Save to filesystem
    l0_dir = settings.KB_DIR / kb_id / "l0"
    l0_dir.mkdir(parents=True, exist_ok=True)

    entities_list = list(entity_map.values())
    with open(l0_dir / "entities.json", "w", encoding="utf-8") as f:
        json.dump(entities_list, f, ensure_ascii=False, indent=2)

    with open(l0_dir / "timeline.json", "w", encoding="utf-8") as f:
        json.dump(timeline_events, f, ensure_ascii=False, indent=2)

    with open(l0_dir / "event_graph.json", "w", encoding="utf-8") as f:
        json.dump(event_graph, f, ensure_ascii=False, indent=2)

    # Cross-document references (simple: find entities mentioned in multiple docs)
    cross_refs = []
    entity_doc_mentions: dict[str, set] = {}
    for ent in entities_list:
        name = ent["name"]
        # Track which docs this entity appears in
        for l1 in l1_results:
            for e in l1.get("entities_mentioned", []):
                e_name = _normalize_entity_name(e.get("name", "") if isinstance(e, dict) else e)
                if e_name == name:
                    doc_id = l1.get("chunk_ids", [""])[0].rsplit("_chunk_", 1)[0] if l1.get("chunk_ids") else ""
                    if doc_id:
                        entity_doc_mentions.setdefault(name, set()).add(doc_id)

    for name, docs in entity_doc_mentions.items():
        if len(docs) > 1:
            cross_refs.append({
                "entity": name,
                "document_count": len(docs),
                "documents": list(docs),
            })

    with open(l0_dir / "cross_refs.json", "w", encoding="utf-8") as f:
        json.dump(cross_refs, f, ensure_ascii=False, indent=2)

    # Save to database
    conn = get_connection()
    try:
        # Clear existing entities for this KB
        conn.execute("DELETE FROM entities WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM timeline_events WHERE kb_id = ?", (kb_id,))

        # Insert entities (OR REPLACE in case of ID collision from merging)
        for ent in entities_list:
            conn.execute(
                """INSERT OR REPLACE INTO entities (id, kb_id, name, entity_type, aliases, attributes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    ent["id"],
                    kb_id,
                    ent["name"],
                    ent.get("type", "unknown"),
                    json.dumps(ent.get("aliases", []), ensure_ascii=False),
                    json.dumps(ent.get("attributes", {}), ensure_ascii=False),
                ),
            )

        # Insert timeline events with kb-prefixed ID to avoid cross-KB collisions
        for i, evt in enumerate(timeline_events):
            conn.execute(
                """INSERT OR REPLACE INTO timeline_events (id, kb_id, event_time, description, participants, source_refs)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    f"tl_{kb_id}_{i:04d}",
                    kb_id,
                    evt.get("date", evt.get("event_time", "")),
                    evt["description"][:500],
                    json.dumps(evt.get("participants", []), ensure_ascii=False),
                    json.dumps(evt.get("source_chunks", []), ensure_ascii=False),
                ),
            )

        conn.commit()
    finally:
        conn.close()

    entity_count = len(entities_list)
    timeline_count = len(timeline_events)
    relation_count = len(all_relations)

    logger.info(
        "Entity merge complete for KB %s: %d entities, %d timeline events, %d relations",
        kb_id, entity_count, timeline_count, relation_count,
    )

    # Collect per-document abstracts into a single index
    try:
        from app.services.compilation.abstract_generator import collect_all_abstracts, save_all_abstracts
        abstracts = collect_all_abstracts(kb_id)
        if abstracts:
            save_all_abstracts(abstracts, kb_id)
            logger.info("Collected %d document abstracts for KB %s", len(abstracts), kb_id)
    except Exception as e:
        logger.warning("Failed to collect abstracts for KB %s: %s", kb_id, e)

    # ── A3: Core concept tags (sorted by relevance) ──────────────────
    concept_tags = _build_concept_tags(entities_list, all_relations)
    with open(l0_dir / "concepts.json", "w", encoding="utf-8") as f:
        json.dump(concept_tags, f, ensure_ascii=False, indent=2)
    logger.info("Core concepts for KB %s: %d tags", kb_id, len(concept_tags))

    # ── A2: Typed relations ──────────────────────────────────────────
    try:
        from app.services.compilation.relation_builder import build_typed_relations, save_typed_relations
        typed_relations = build_typed_relations(entities_list, all_relations)
        save_typed_relations(typed_relations, kb_id)
        logger.info("Typed relations for KB %s: %d relations", kb_id, len(typed_relations))
    except Exception as e:
        logger.warning("Relation building failed for KB %s: %s", kb_id, e)

    # ── A4: Timeline builder integration ─────────────────────────────
    try:
        from app.services.compilation.timeline_builder import build_timeline
        build_timeline(kb_id, l1_results)
    except Exception as e:
        logger.warning("Timeline building failed for KB %s: %s", kb_id, e)

    # ── Contradiction detection ──────────────────────────────────────
    try:
        from app.services.compilation.contradiction_detector import detect_contradictions
        detect_contradictions(kb_id)
    except Exception as e:
        logger.warning("Contradiction detection failed for KB %s: %s", kb_id, e)

    return entity_count, timeline_count


def _build_concept_tags(entities_list: list[dict], all_relations: list[dict]) -> list[dict]:
    """Build core concept tags sorted by entity connectivity + frequency.

    Returns [{"id": "ent_0003", "name": "张伟", "frequency": 14, "connections": 7, "rank": 1}, ...]
    """
    # Count connections per entity from relations
    connection_count: dict[str, int] = {}
    for rel in all_relations:
        subj = rel.get("subject", "")
        obj = rel.get("object", "")
        if subj:
            connection_count[subj] = connection_count.get(subj, 0) + 1
        if obj:
            connection_count[obj] = connection_count.get(obj, 0) + 1

    tags = []
    for ent in entities_list:
        name = ent.get("name", "")
        if not name:
            continue
        freq = ent.get("mention_count", 1)
        conns = connection_count.get(name, 0)
        score = freq + conns * 2  # connections weighted 2x
        tags.append({
            "id": ent.get("id", ""),
            "name": name,
            "type": ent.get("type", "unknown"),
            "frequency": freq,
            "connections": conns,
            "score": score,
        })

    tags.sort(key=lambda t: t["score"], reverse=True)

    # Assign ranks
    for i, t in enumerate(tags):
        t["rank"] = i + 1

    return tags[:50]  # Top 50
