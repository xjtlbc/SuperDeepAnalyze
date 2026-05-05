"""Relation builder: classify entity relationships into typed categories.

Auto-infers relation types from entity attributes, co-occurrence patterns,
and L1 summary context. Outputs weighted, typed relations for the knowledge graph.
"""

import json
import logging
import re
from pathlib import Path

from app.config import settings, flags

logger = logging.getLogger("app.compilation.relation")

# Relation type inference patterns
_RELATION_PATTERNS: list[tuple[str, list[str], float]] = [
    ("资金往来", ["转账", "汇款", "支付", "收款", "金额", "万元", "元", "资金"], 0.8),
    ("雇佣关系", ["任职", "担任", "员工", "经理", "董事", "法定代表人", "负责人", "股东"], 0.85),
    ("亲属关系", ["配偶", "子女", "父母", "兄弟", "姐妹", "夫妻", "父子", "母女"], 0.9),
    ("通话记录", ["通话", "电话", "联系", "拨打", "接听", "主叫", "被叫"], 0.75),
    ("证据链", ["证明", "证实", "佐证", "印证", "相符", "吻合"], 0.7),
    ("时间关联", ["同时", "之后", "之前", "当天", "同日", "次日"], 0.65),
    ("地点关联", ["位于", "地址", "住所", "经营地", "注册地"], 0.7),
    ("合同关系", ["合同", "协议", "签署", "甲方", "乙方", "签订"], 0.8),
    ("共犯关系", ["伙同", "共谋", "指使", "授意", "参与", "协助"], 0.85),
    ("受害人关系", ["被害人", "受害者", "受害人", "侵害", "骗取"], 0.8),
]

# Monetary patterns for 资金往来 detection
_MONEY_RE = re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:万|亿)?\s*(?:元|美元|人民币)")


def infer_relation_type(subject: str, predicate: str, obj: str, summary: str) -> tuple[str, float]:
    """Infer the relation type and confidence from context.

    Returns (relation_type, confidence_score).
    """
    combined = f"{subject} {predicate} {obj} {summary}"

    best_type = "相关"
    best_score = 0.5

    for rel_type, keywords, base_score in _RELATION_PATTERNS:
        hits = sum(1 for kw in keywords if kw in combined)
        if hits >= 2:
            score = min(1.0, base_score + 0.05 * hits)
            if score > best_score:
                best_type = rel_type
                best_score = score

    # Boost: check monetary values for financial relations
    if best_type != "资金往来" and _MONEY_RE.search(combined):
        if best_score < 0.7:
            best_type = "资金往来"
            best_score = 0.7

    return best_type, best_score


def build_typed_relations(entities_list: list[dict], all_relations: list[dict]) -> list[dict]:
    """Enrich relations with inferred types and weights.

    Args:
        entities_list: Merged entity list with entity names and IDs.
        all_relations: Raw relation triples from entity_merger with
                       subject, predicate, object, source_chunks.

    Returns:
        List of typed relation dicts:
        {subject, subject_id, predicate, object, object_id, type, weight, source_chunks}
    """
    if not flags.compile_contradiction_detection:  # reuse existing flag for now
        return all_relations

    # Build name→id lookup
    name_to_id: dict[str, str] = {}
    for ent in entities_list:
        name = ent.get("name", "").strip()
        if name:
            name_to_id[name] = ent.get("id", "")
        for alias in ent.get("aliases", []):
            if alias.strip():
                name_to_id[alias.strip()] = ent.get("id", "")

    typed: list[dict] = []
    for rel in all_relations:
        subj = rel.get("subject", "")
        obj = rel.get("object", "")
        pred = rel.get("predicate", "相关")

        rel_type, score = infer_relation_type(
            subj, pred, obj,
            rel.get("summary_context", pred),
        )

        typed.append({
            "subject": subj,
            "subject_id": name_to_id.get(subj, ""),
            "predicate": pred,
            "object": obj,
            "object_id": name_to_id.get(obj, ""),
            "type": rel_type,
            "weight": score,
            "source_chunks": rel.get("source_chunks", []),
        })

    # Save
    return typed


def save_typed_relations(relations: list[dict], kb_id: str) -> Path:
    """Save typed relations to L0 directory."""
    l0_dir = settings.KB_DIR / kb_id / "l0"
    l0_dir.mkdir(parents=True, exist_ok=True)
    path = l0_dir / "relations.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(relations, f, ensure_ascii=False, indent=2)
    return path
