"""Query rewriter: entity extraction + sub-query generation.

Extracts entities from Chinese queries, generates multiple sub-queries
for more comprehensive retrieval coverage.
"""

import re
from dataclasses import dataclass
from typing import Optional

from app.utils.logging_config import get_logger

logger = get_logger("app.retrieval.query_rewriter")


@dataclass
class RewrittenQuery:
    """Result of query rewriting."""
    original: str
    entities: list[str]
    sub_queries: list[str]
    query_type: str  # entity / relation / event / evidence / general
    expanded_terms: list[str]


# Chinese legal domain action words
_LEGAL_ACTIONS = {
    "杀害", "伤害", "伤害", "盗窃", "诈骗", "抢劫", "敲诈", "威胁",
    "恐吓", "殴打", "绑架", "非法", "犯罪", "违法", "作案", "行贿",
    "受贿", "贪污", "走私", "纵火", "投毒", "强奸", "猥亵",
}

# Relation keywords that indicate relationship queries
_RELATION_KEYWORDS = {"关系", "关联", "联系", "之间", "往来", "交集", "纠葛"}

# Evidence keywords that indicate evidence queries
_EVIDENCE_KEYWORDS = {"证据", "证明", "物证", "书证", "证词", "证言", "陈述", "口供", "笔录"}


def _extract_entities_from_query(query: str) -> list[str]:
    """Extract entity names from a Chinese query using multiple strategies."""
    entities = set()

    # Strategy 1: Names before common particles
    pattern = re.compile(r'([一-鿿]{2,4})(?:的|在|与|和|对|向|被|把|从|到|给|是|有|了|把|将)')
    for match in pattern.finditer(query):
        name = match.group(1)
        if _is_likely_name(name):
            entities.add(name)

    # Strategy 2: Split on conjunctions
    for conj in ["和", "与", "同", "及", "、"]:
        if conj in query:
            parts = query.split(conj)
            for part in parts:
                name_match = re.match(r'^([一-鿿]{2,4})', part.strip())
                if name_match and _is_likely_name(name_match.group(1)):
                    entities.add(name_match.group(1))

    # Strategy 3: After certain prepositions
    prep_match = re.findall(r'(?:关于|涉及|有关|对于|针对)([一-鿿]{2,8}?)(?:的|问题|事情|案件|事件)', query)
    for name in prep_match:
        if _is_likely_name(name):
            entities.add(name)

    return list(entities)


def _is_likely_name(text: str) -> bool:
    """Check if text looks like a person/entity name (not a common word)."""
    stopwords = {
        "什么", "怎么", "为什么", "如何", "哪里", "那个", "这个", "哪些",
        "怎样", "多少", "几个", "是否", "能否", "可以", "案件", "证据",
        "关系", "问题", "动机", "原因", "时候", "地方", "情况", "事实",
        "结果", "过程", "经过", "行为", "目的", "手段", "方式", "状态",
    }
    if text in stopwords:
        return False
    if all(c in "的了是在和与或就着过们这那" for c in text):
        return False
    return True


def _classify_query_type(query: str) -> str:
    """Classify the query into a type for tailored sub-query generation."""
    if any(kw in query for kw in _EVIDENCE_KEYWORDS):
        return "evidence"
    if any(kw in query for kw in _RELATION_KEYWORDS):
        return "relation"
    if any(kw in query for kw in ["什么时候", "时间", "时间线", "经过", "先后", "之前", "之后", "期间"]):
        return "event"
    entities = _extract_entities_from_query(query)
    if len(entities) >= 2:
        return "relation"
    if entities:
        return "entity"
    return "general"


def _generate_sub_queries(query: str, entities: list[str], query_type: str) -> list[str]:
    """Generate sub-queries for more comprehensive search coverage."""
    sub_queries = [query]  # Always include original

    if query_type == "relation" and len(entities) >= 2:
        # Entity pair queries
        sub_queries.append(f"{entities[0]} {entities[1]} 关系")
        sub_queries.append(f"{entities[0]} {entities[1]}")
        # Per-entity queries
        for e in entities[:3]:
            sub_queries.append(f"{e} 关系网络")

    elif query_type == "evidence":
        for e in entities[:2]:
            sub_queries.append(f"{e} 证据 证词")
            sub_queries.append(f"{e} 陈述")

    elif query_type == "event":
        for e in entities[:2]:
            sub_queries.append(f"{e} 时间 经过")
        sub_queries.append("案件经过 时间线")

    elif query_type == "entity" and entities:
        e = entities[0]
        sub_queries.append(f"{e} 身份 信息")
        sub_queries.append(f"{e} 涉及 关联")

    # Extract action keywords and add focused queries
    for action in _LEGAL_ACTIONS:
        if action in query:
            for e in entities[:1]:
                sub_queries.append(f"{e} {action}")

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for sq in sub_queries:
        if sq not in seen:
            seen.add(sq)
            unique.append(sq)

    return unique[:6]  # Cap at 6 sub-queries


def _expand_terms(query: str) -> list[str]:
    """Expand query with related legal terms."""
    expansions = {
        "杀": ["杀害", "杀人", "致死", "命案"],
        "伤": ["伤害", "受伤", "殴打", "致伤"],
        "偷": ["盗窃", "偷窃", "窃取"],
        "骗": ["诈骗", "欺骗", "骗取"],
        "抢": ["抢劫", "抢夺"],
        "威胁": ["恐吓", "胁迫", "威逼"],
        "动机": ["目的", "起因", "原因"],
        "证据": ["物证", "书证", "证词", "证明"],
        "矛盾": ["不一致", "冲突", "出入"],
    }
    terms = []
    for key, synonyms in expansions.items():
        if key in query:
            terms.extend(synonyms)
    return terms[:5]


def rewrite_query(query: str) -> RewrittenQuery:
    """Rewrite a user query for better retrieval coverage."""
    entities = _extract_entities_from_query(query)
    query_type = _classify_query_type(query)
    sub_queries = _generate_sub_queries(query, entities, query_type)
    expanded_terms = _expand_terms(query)

    return RewrittenQuery(
        original=query,
        entities=entities,
        sub_queries=sub_queries,
        query_type=query_type,
        expanded_terms=expanded_terms,
    )
