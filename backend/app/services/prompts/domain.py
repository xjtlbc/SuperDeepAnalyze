"""Two-mode domain detection: legal (公检法) vs general.

Legal mode is the primary use case. General mode is the fallback for
everything else (technical papers, business docs, etc).
"""

from __future__ import annotations

from app.models.database import get_connection
from app.utils.logging_config import get_logger

logger = get_logger("app.prompts.domain")

# Domain constants
LEGAL = "legal"
GENERAL = "general"


def detect_kb_domain(kb_id: str) -> str:
    """Detect whether KB is legal (公检法) or general.

    Heuristic: if the KB has legal-specific entity types (evidence, document)
    or if person+organization entities dominate, it's legal.
    Falls back to checking L0 entities file if DB table is empty.
    """
    try:
        conn = get_connection()
        cursor = conn.execute(
            "SELECT entity_type, COUNT(*) as cnt FROM entities "
            "WHERE kb_id = ? GROUP BY entity_type ORDER BY cnt DESC LIMIT 5",
            (kb_id,),
        )
        type_counts = {row["entity_type"]: row["cnt"] for row in cursor.fetchall()}
        conn.close()

        if type_counts:
            # Legal indicators: evidence or document entity types
            if type_counts.get("evidence", 0) > 0 or type_counts.get("document", 0) > 0:
                return LEGAL
            # Person + org dominant → likely legal case
            person_org = type_counts.get("person", 0) + type_counts.get("organization", 0)
            concept = type_counts.get("concept", 0) + type_counts.get("method", 0) + type_counts.get("model", 0)
            if person_org > 0 and person_org >= concept:
                return LEGAL
            return GENERAL
    except Exception:
        pass

    # Fallback: check L0 entities file directly
    try:
        import json
        from app.config import settings
        l0_path = settings.KB_DIR / kb_id / "l0" / "entities.json"
        if l0_path.exists():
            with open(l0_path, encoding="utf-8") as f:
                entities = json.load(f)
            types = set(e.get("type", "") for e in entities)
            if "evidence" in types or "document" in types:
                return LEGAL
            person_org = sum(1 for e in entities if e.get("type") in ("person", "organization"))
            concept = sum(1 for e in entities if e.get("type") in ("concept", "method", "model"))
            if person_org > 0 and person_org >= concept:
                return LEGAL
    except Exception:
        pass

    return GENERAL


# --- Two-mode prompt configs -----------------------------------------

_CONFIGS = {
    LEGAL: {
        "identity": "资深案件材料分析专家",
        "material": "卷宗材料",
        "entity_types": "人物、组织、地点、事件、证据、文档",
        "catalog_structure": """\
- 案件概述 (overview)
- 涉案人物 (characters) -> 按重要性分为主要人物、次要人物
- 组织与机构 (organizations)
- 时间线与事件 (timeline)
- 证据链 (evidence)
- 矛盾与疑点 (contradictions)
- 知识缺口 (gaps)""",
        "page_style": "保持客观、专业的法律文档风格",
        "page_structure": """\
## 基本信息
## 关系网络
## 涉案时间线
## 关键证据
## 矛盾点（如适用）""",
    },
    GENERAL: {
        "identity": "知识库深度分析专家",
        "material": "知识库文档",
        "entity_types": "实体、概念、方法、模型、数据、指标、人物、组织",
        "catalog_structure": """\
- 概述 (overview) -> 核心内容、主要发现/贡献
- 核心内容 (core-concepts) -> 关键实体、概念、方法
- 方法与架构 (methods) -> 技术方案、框架、算法（如适用）
- 数据与实验 (experiments) -> 数据集、指标、结果（如适用）
- 关联分析 (relations) -> 实体间关联、对比、影响
- 时间线 (timeline) -> 关键事件和里程碑（如适用）
- 知识缺口 (gaps) -> 缺失信息和待深入方向""",
        "page_style": "保持严谨、清晰的知识库文档风格",
        "page_structure": """\
## 概述
## 核心内容
## 相关实体与关系
## 关键发现/数据
## 待补充信息""",
    },
}


def get_domain_config(domain: str) -> dict:
    """Get domain config dict. domain should be LEGAL or GENERAL."""
    return _CONFIGS.get(domain, _CONFIGS[GENERAL]).copy()
