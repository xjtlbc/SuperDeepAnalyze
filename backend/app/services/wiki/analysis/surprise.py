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

    # 1. Rarity-based surprises: entities with unusually few relations
    entity_relation_count = Counter()
    for ref in cross_refs:
        for doc in [ref.get("source_doc", ""), ref.get("target_doc", "")]:
            if doc:
                entity_relation_count[doc] += 1

    # Entities mentioned in cross_refs but with low counts are "surprising"
    if entity_relation_count:
        counts = list(entity_relation_count.values())
        avg_count = sum(counts) / len(counts) if counts else 0
        for entity_name, count in entity_relation_count.items():
            if count == 0 and avg_count > 2:
                surprises.append({
                    "type": "isolated_entity",
                    "score": 0.7,
                    "subject": entity_name,
                    "description": f"实体 {entity_name} 未与其他实体建立关系",
                    "reason": "孤立实体，可能遗漏关键关联",
                })

    # 2. Contradiction-based surprises
    for ref in cross_refs:
        description = ref.get("description", "")
        if description and len(description) > 10:
            surprises.append({
                "type": "cross_doc_contradiction",
                "score": 0.9,
                "subject": ref.get("source_doc", ""),
                "description": description,
                "reason": f"跨文档矛盾: {ref.get('source_doc', '')} ↔ {ref.get('target_doc', '')}",
                "source_doc": ref.get("source_doc"),
                "target_doc": ref.get("target_doc"),
            })

    # 3. Temporal anomalies: events with impossible time sequences
    time_events = [e for e in timeline if e.get("time")]
    time_events.sort(key=lambda e: e["time"])
    for i in range(1, len(time_events)):
        prev_time = time_events[i - 1].get("time", "")
        curr_time = time_events[i].get("time", "")
        if prev_time and curr_time and curr_time < prev_time:
            surprises.append({
                "type": "temporal_anomaly",
                "score": 0.85,
                "subject": time_events[i].get("description", "")[:50],
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
