"""Cross-document contradiction detection for compiled knowledge bases.

When two documents describe the same entity with conflicting attributes
(e.g., Document A says person X is 35, Document B says X is 42), this
module detects and reports the contradictions.

Algorithmic — no LLM calls needed.
"""

import json
import logging
from pathlib import Path

from app.config import settings, flags

logger = logging.getLogger("app.compilation.contradiction")


def _normalize_value(val) -> str:
    """Normalize a value for comparison — strip, lowercase, remove punctuation."""
    if isinstance(val, str):
        return val.strip().lower().replace(" ", "").replace("(", "").replace(")", "")
    return str(val)


def _values_conflict(v1, v2) -> bool:
    """Check if two values conflict (are different after normalization)."""
    return _normalize_value(v1) != _normalize_value(v2)


def _is_comparable(attr_name: str) -> bool:
    """Only compare meaningful attributes (skip IDs, timestamps, etc.)."""
    comparable = {"age", "gender", "sex", "name", "id_number", "amount",
                   "date", "time", "location", "address", "role", "title",
                   "position", "status", "result", "conclusion", "verdict"}
    attr_lower = attr_name.lower()
    return any(kw in attr_lower for kw in comparable)


def detect_contradictions(kb_id: str) -> list[dict]:
    """Detect cross-document contradictions from entity attributes.

    Loads entities from entities.json, compares same-name entities across
    their source documents for conflicting attribute values.

    Returns list of contradiction dicts:
        {entity, attr, values: [{doc_id, value, source}], confidence}
    """
    if not flags.compile_contradiction_detection:
        return []

    entities_path = settings.KB_DIR / kb_id / "l0" / "entities.json"
    if not entities_path.exists():
        logger.warning("No entities.json for KB %s, skipping contradiction detection", kb_id)
        return []

    with open(entities_path, "r", encoding="utf-8") as f:
        entities = json.load(f)

    contradictions: list[dict] = []

    # Group entities by name for cross-document comparison
    name_groups: dict[str, list[dict]] = {}
    for ent in entities:
        name = ent.get("name", "").strip()
        if not name:
            continue
        name_groups.setdefault(name, []).append(ent)

    for entity_name, group in name_groups.items():
        if len(group) < 2:
            continue

        attributes = group[0].get("attributes", {})
        if not attributes:
            continue

        for attr_key, attr_val in attributes.items():
            if not _is_comparable(attr_key):
                continue

            values_seen: dict[str, list[dict]] = {}
            for ent in group:
                ent_attrs = ent.get("attributes", {})
                ent_val = ent_attrs.get(attr_key)
                if ent_val is None:
                    continue
                normed = _normalize_value(ent_val)
                values_seen.setdefault(normed, []).append({
                    "value": str(ent_val),
                    "entity_id": ent.get("id", ""),
                    "source_chunks": ent.get("source_chunks", [])[:3],
                })

            if len(values_seen) > 1:
                values_list = list(values_seen.values())
                contradictions.append({
                    "entity": entity_name,
                    "attribute": attr_key,
                    "values": [
                        {"value": vals[0]["value"], "source_count": len(vals)}
                        for vals in values_list
                    ],
                    "confidence": min(1.0, 0.5 + 0.1 * len(values_list)),
                    "type": "attribute_conflict",
                })

    # Save contradictions report
    l0_dir = settings.KB_DIR / kb_id / "l0"
    l0_dir.mkdir(parents=True, exist_ok=True)
    with open(l0_dir / "contradictions.json", "w", encoding="utf-8") as f:
        json.dump(contradictions, f, ensure_ascii=False, indent=2)

    logger.info("Contradiction detection for KB %s: %d contradictions found", kb_id, len(contradictions))
    return contradictions
