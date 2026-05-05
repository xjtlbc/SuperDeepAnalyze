"""Surprise detection: calculates surprise scores for findings based on rarity, contradictions, and temporal anomalies."""

from __future__ import annotations
import json
from pathlib import Path
from collections import Counter

from app.config import settings


def detect_surprises(kb_id: str) -> dict:
    """Analyze L0/L1 data for surprising findings.

    Returns dict with:
    - surprises: list of findings with surprise scores
    - stats: summary statistics
    """
    l0_dir = settings.KB_DIR / kb_id / "l0"

    surprises: list[dict] = []

    # Load L0 data
    entities = _load_json(l0_dir / "entities.json", [])
    timeline = _load_json(l0_dir / "timeline.json", [])
    cross_refs = _load_json(l0_dir / "cross_refs.json", [])

    # 1. Rarity-based surprises: entities appearing in few documents vs. average
    # cross_refs format: [{"entity": str, "document_count": int, "documents": [str]}]
    doc_counts = [ref.get("document_count", 0) for ref in cross_refs]
    if doc_counts:
        avg_docs = sum(doc_counts) / len(doc_counts)
        for ref in cross_refs:
            entity_name = ref.get("entity", "")
            count = ref.get("document_count", 0)
            if entity_name and count <= 1 and avg_docs > 2:
                surprises.append({
                    "type": "isolated_entity",
                    "score": 0.7,
                    "subject": entity_name,
                    "description": f"实体 {entity_name} 仅在 {count} 篇文档中出现",
                    "reason": "该实体出现频率远低于平均水平，可能存在信息遗漏",
                })

    # 2. Cross-doc entity contradictions: entities with attribute variance across docs
    # Build entity attribute map from entities.json
    entity_attrs: dict[str, dict] = {}
    for e in entities:
        name = e.get("name", "")
        attrs = e.get("attributes", {})
        if name and attrs:
            entity_attrs[name] = attrs

    for ref in cross_refs:
        entity_name = ref.get("entity", "")
        docs = ref.get("documents", [])
        if entity_name and len(docs) >= 2:
            # Check if this entity has attributes that might be conflicting
            attrs = entity_attrs.get(entity_name, {})
            if attrs:
                surprises.append({
                    "type": "cross_doc_contradiction",
                    "score": 0.75,
                    "subject": entity_name,
                    "description": f"实体 {entity_name} 出现在 {len(docs)} 篇文档中",
                    "reason": f"跨文档实体: 需人工核实不同文档中对 {entity_name} 的描述是否一致",
                    "related_docs": docs,
                })

    # 3. Temporal anomalies: events with impossible time sequences
    time_events = [e for e in timeline if e.get("date", e.get("time", ""))]
    time_events.sort(key=lambda e: e.get("date", e.get("time", "")))
    for i in range(1, len(time_events)):
        prev_time = time_events[i - 1].get("date", time_events[i - 1].get("time", ""))
        curr_time = time_events[i].get("date", time_events[i].get("time", ""))
        if prev_time and curr_time and curr_time < prev_time:
            surprises.append({
                "type": "temporal_anomaly",
                "score": 0.85,
                "subject": (time_events[i].get("title") or time_events[i].get("description", ""))[:50],
                "description": f"时间顺序异常: {prev_time} → {curr_time}",
                "reason": "事件时间倒序，可能存在记录错误或关键信息缺失",
            })

    # 4. Entity type distribution surprises
    type_counts = Counter(e.get("type", "unknown") for e in entities)
    total_entities = len(entities)
    if total_entities > 10:
        # If one type dominates unusually (>80%), flag it
        for etype, count in type_counts.items():
            ratio = count / total_entities
            if ratio > 0.8 and len(type_counts) > 2:
                surprises.append({
                    "type": "skewed_distribution",
                    "score": 0.5,
                    "subject": etype,
                    "description": f"实体类型分布倾斜: {etype} 占 {ratio:.0%}",
                    "reason": "某类实体占比过高，可能遗漏其他类型实体",
                })

    # Sort by score (highest first)
    surprises.sort(key=lambda s: s["score"], reverse=True)

    return {
        "kb_id": kb_id,
        "surprises": surprises,
        "stats": {
            "total_surprises": len(surprises),
            "high_surprise": sum(1 for s in surprises if s["score"] >= 0.8),
            "medium_surprise": sum(1 for s in surprises if 0.5 <= s["score"] < 0.8),
            "low_surprise": sum(1 for s in surprises if s["score"] < 0.5),
            "by_type": dict(Counter(s["type"] for s in surprises)),
        },
    }


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default
