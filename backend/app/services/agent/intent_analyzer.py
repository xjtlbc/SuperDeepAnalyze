"""Intent analyzer for Agent retrieval strategy.

Analyzes user questions to generate query plans before the reAct loop starts.
Inspired by OpenViking's IntentAnalyzer, adapted for legal case analysis.
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.models.config import RoleType
from app.utils.logging_config import get_logger

logger = get_logger("app.agent.intent_analyzer")


# Table/aggregation keywords that indicate structured data queries
_TABLE_KEYWORDS = ["表格", "表里", "表中的", "数据表", "Excel", "excel", "统计表"]
_AGG_KEYWORDS = ["统计", "排名", "最多", "最少", "平均", "占比", "总计", "分组",
                 "排行", "TOP", "top", "求和", "数量", "多少个", "几种", "各类"]


class QuestionType(str, Enum):
    FACTUAL = "factual"          # 事实查询: 谁/什么时候/在哪里
    RELATIONAL = "relational"    # 关系查询: A和B什么关系
    TEMPORAL = "temporal"        # 时间查询: 什么时候发生/时间线
    ANALYTICAL = "analytical"    # 分析查询: 为什么/动机/原因
    COMPARATIVE = "comparative"  # 对比查询: A和B的证词矛盾
    EVIDENTIAL = "evidential"    # 证据查询: 有什么证据证明
    TABULAR = "tabular"          # 表格查询: 涉及表格数据的统计/排名/筛选/聚合


class Complexity(str, Enum):
    SIMPLE = "simple"      # 单跳, 直接检索
    MEDIUM = "medium"      # 2-3跳, 需要跨文档
    COMPLEX = "complex"    # 多跳, 需要综合推理


class SearchMode(str, Enum):
    THINKING = "thinking"  # 深度模式: 多轮搜索, L0→L1→L2
    QUICK = "quick"        # 快速模式: 少量搜索, L0或L1


@dataclass
class SubQuery:
    """A single decomposed sub-query with target layer."""
    query: str
    target_layer: str        # L0 / L1 / L2
    search_type: str         # vector / keyword / graph / hybrid
    priority: int = 3        # 1(最高) - 5(最低)


@dataclass
class QueryPlan:
    """Complete query plan generated from intent analysis."""
    original_query: str
    question_type: QuestionType
    complexity: Complexity
    search_mode: SearchMode
    target_entities: list[str]
    time_range: Optional[tuple[str, str]]
    suggested_start_level: str   # L0 / L1 / L2
    sub_queries: list[SubQuery]
    reasoning: str = ""


# Chinese legal domain patterns for entity extraction
_PERSON_PATTERN = re.compile(r'[一-鿿]{2,4}(?=的|在|与|和|对|向|被|把|从|到|给)')
_TIME_PATTERN = re.compile(r'\d{4}年|\d{1,2}月\d{1,2}日|\d{1,2}[月日]|\d{4}[/-]\d{1,2}')
_ACTION_PATTERN = re.compile(r'(杀害|伤害|盗窃|诈骗|抢劫|敲诈|威胁|恐吓|殴打|绑架|非法|犯罪|违法|作案)')


def _extract_entities_simple(query: str) -> list[str]:
    """Extract potential entity names from Chinese query using patterns."""
    entities = set()

    # Pattern 1: Names before common particles (张三的, 李四与)
    for match in _PERSON_PATTERN.finditer(query):
        name = match.group()
        if 2 <= len(name) <= 4:
            stopwords = {"什么", "怎么", "为什么", "如何", "哪里", "那个", "这个",
                         "哪些", "怎样", "多少", "几个", "是否", "能否", "可以"}
            if name not in stopwords:
                entities.add(name)

    # Pattern 2: Split on conjunctions and extract names from both sides
    # e.g. "张三和李四" → [张三, 李四]
    for conj in ["和", "与", "同", "及", "、"]:
        if conj in query:
            parts = query.split(conj)
            for part in parts:
                # Extract 2-4 char Chinese sequences that look like names
                name_match = re.match(r'^([一-鿿]{2,4})', part.strip())
                if name_match:
                    name = name_match.group(1)
                    stopwords = {"什么", "怎么", "为什么", "如何", "哪里", "那个", "这个",
                                 "哪些", "怎样", "多少", "几个", "是否", "能否", "可以",
                                 "案件", "证据", "关系", "问题", "动机", "原因"}
                    if name not in stopwords and len(name) >= 2:
                        entities.add(name)

    # Pattern 3: Quoted names (「张三」 or "张三")
    quoted = re.findall(r'[「"\'《【](.{2,10})[」"\'》】]', query)
    entities.update(q for q in quoted if 2 <= len(q) <= 10)

    # Pattern 4: After "关于" or "涉及"
    about_match = re.search(r'(?:关于|涉及|有关)(.{2,10}?)(?:的|问题|事情|案件|事件)', query)
    if about_match:
        entities.add(about_match.group(1))

    return list(entities)


def _extract_time_range(query: str) -> Optional[tuple[str, str]]:
    """Extract time range from query."""
    matches = _TIME_PATTERN.findall(query)
    if len(matches) >= 2:
        return (matches[0], matches[-1])
    elif len(matches) == 1:
        return (matches[0], "")
    return None


def _classify_question_type(query: str) -> QuestionType:
    """Classify question type based on Chinese keywords."""
    # Table queries: any aggregation or table-reference keyword
    has_table_ref = any(kw in query for kw in _TABLE_KEYWORDS)
    has_agg = any(kw in query for kw in _AGG_KEYWORDS)
    if has_table_ref or has_agg:
        return QuestionType.TABULAR
    if any(kw in query for kw in ["对比", "比较", "矛盾", "不一致", "差异", "不同"]):
        return QuestionType.COMPARATIVE
    if any(kw in query for kw in ["证据", "证明", "证据链", "物证", "书证"]):
        return QuestionType.EVIDENTIAL
    if any(kw in query for kw in ["为什么", "动机", "原因", "目的", "起因", "缘由"]):
        return QuestionType.ANALYTICAL
    if any(kw in query for kw in ["什么时候", "时间", "时间线", "先后", "经过", "日程"]):
        return QuestionType.TEMPORAL
    if any(kw in query for kw in ["关系", "关联", "联系", "之间"]):
        return QuestionType.RELATIONAL
    return QuestionType.FACTUAL


def _classify_complexity(query: str, question_type: QuestionType) -> Complexity:
    """Assess question complexity."""
    # Table queries with aggregation/computation are at least MEDIUM
    if question_type == QuestionType.TABULAR:
        has_agg = any(kw in query for kw in _AGG_KEYWORDS)
        if has_agg:
            return Complexity.COMPLEX  # Aggregation needs multi-step reasoning
        return Complexity.MEDIUM  # Even simple table lookups need tool chain

    complex_keywords = ["综合", "全面", "所有", "全部", "完整", "深度", "详细分析",
                        "为什么", "动机", "原因", "证据链", "矛盾"]
    medium_keywords = ["关系", "关联", "对比", "经过", "时间线"]

    if any(kw in query for kw in complex_keywords):
        return Complexity.COMPLEX
    if question_type in (QuestionType.ANALYTICAL, QuestionType.COMPARATIVE):
        return Complexity.COMPLEX
    if any(kw in query for kw in medium_keywords):
        return Complexity.MEDIUM
    if question_type == QuestionType.RELATIONAL:
        return Complexity.MEDIUM
    return Complexity.SIMPLE


def _select_start_level(question_type: QuestionType, complexity: Complexity) -> str:
    """Select the starting retrieval level."""
    if question_type == QuestionType.TABULAR:
        return "L1"  # Table queries need L1 summaries + search_excel tool
    if complexity == Complexity.SIMPLE:
        return "L0"
    if question_type == QuestionType.EVIDENTIAL:
        return "L2"  # Evidence queries need source text
    if question_type in (QuestionType.TEMPORAL, QuestionType.RELATIONAL):
        return "L1"  # Need paragraph-level detail
    return "L1"  # Default to L1 for medium/complex


def _generate_sub_queries(
    query: str,
    entities: list[str],
    question_type: QuestionType,
    complexity: Complexity,
) -> list[SubQuery]:
    """Generate decomposed sub-queries from the original query."""
    sub_queries = []

    # Always start with the original query as the primary search
    start_level = _select_start_level(question_type, complexity)
    sub_queries.append(SubQuery(
        query=query,
        target_layer=start_level,
        search_type="hybrid",
        priority=1,
    ))

    # Entity-based sub-queries
    for entity in entities[:3]:  # Max 3 entity queries
        if question_type == QuestionType.RELATIONAL:
            sub_queries.append(SubQuery(
                query=f"{entity} 关系",
                target_layer="L0",
                search_type="graph",
                priority=2,
            ))
        elif question_type == QuestionType.TEMPORAL:
            sub_queries.append(SubQuery(
                query=f"{entity} 时间线",
                target_layer="L1",
                search_type="keyword",
                priority=2,
            ))
        elif question_type == QuestionType.EVIDENTIAL:
            sub_queries.append(SubQuery(
                query=f"{entity} 证据",
                target_layer="L2",
                search_type="hybrid",
                priority=2,
            ))
        else:
            sub_queries.append(SubQuery(
                query=entity,
                target_layer="L0",
                search_type="graph",
                priority=2,
            ))

    # For complex questions, add a broader search
    if complexity == Complexity.COMPLEX and entities:
        # Search for relationships between first two entities
        if len(entities) >= 2:
            sub_queries.append(SubQuery(
                query=f"{entities[0]} {entities[1]} 关系",
                target_layer="L1",
                search_type="hybrid",
                priority=2,
            ))
        # Search for contradictions
        if question_type in (QuestionType.COMPARATIVE, QuestionType.ANALYTICAL):
            sub_queries.append(SubQuery(
                query=f"{entities[0] if entities else ''} 矛盾 不一致",
                target_layer="L1",
                search_type="keyword",
                priority=3,
            ))

    return sub_queries


def analyze_intent_simple(query: str) -> QueryPlan:
    """Fast rule-based intent analysis (no LLM call).

    Used as the default intent analyzer. Falls back to LLM-based analysis
    if more precision is needed.
    """
    entities = _extract_entities_simple(query)
    time_range = _extract_time_range(query)
    question_type = _classify_question_type(query)
    complexity = _classify_complexity(query, question_type)
    search_mode = SearchMode.THINKING if complexity == Complexity.COMPLEX else SearchMode.QUICK
    start_level = _select_start_level(question_type, complexity)
    sub_queries = _generate_sub_queries(query, entities, question_type, complexity)

    return QueryPlan(
        original_query=query,
        question_type=question_type,
        complexity=complexity,
        search_mode=search_mode,
        target_entities=entities,
        time_range=time_range,
        suggested_start_level=start_level,
        sub_queries=sub_queries,
        reasoning=f"规则分析: 类型={question_type.value}, 复杂度={complexity.value}, "
                  f"实体={entities}, 起始层级={start_level}",
    )


async def analyze_intent_with_llm(query: str, llm_client) -> QueryPlan:
    """LLM-based intent analysis for more precise query planning.

    Falls back to analyze_intent_simple() if LLM fails.
    """
    # First get the rule-based analysis as baseline
    baseline = analyze_intent_simple(query)

    prompt = f"""你是一个知识库分析助手。请分析以下用户问题，生成检索计划。

用户问题: {query}

规则分析的初步结果:
- 问题类型: {baseline.question_type.value}
- 复杂度: {baseline.complexity.value}
- 识别的实体: {baseline.target_entities}
- 建议起始层级: {baseline.suggested_start_level}

**重要分类规则**：
- 如果问题涉及表格/Excel数据（统计、排名、筛选、分组、最多/最少、数量），
  question_type 必须为 "tabular"，complexity 至少为 "medium"
- tabular 类型的问题需要使用 search_excel 工具，不能用普通文本搜索

请输出JSON格式(不要输出其他内容):
{{
  "question_type": "factual|relational|temporal|analytical|comparative|evidential|tabular",
  "complexity": "simple|medium|complex",
  "entities": ["实体1", "实体2"],
  "time_range": ["开始时间", "结束时间"],
  "sub_queries": [
    {{"query": "子查询1", "layer": "L0|L1|L2", "priority": 1}}
  ],
  "reasoning": "分析推理过程"
}}"""

    try:
        response = await llm_client.chat(
            role=RoleType.LIGHTWEIGHT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            return baseline

        parsed = json.loads(json_match.group())

        question_type = QuestionType(parsed.get("question_type", baseline.question_type.value))
        complexity = Complexity(parsed.get("complexity", baseline.complexity.value))
        entities = parsed.get("entities", baseline.target_entities)
        time_range_raw = parsed.get("time_range", [])
        time_range = tuple(time_range_raw) if time_range_raw else baseline.time_range

        sub_queries = []
        for sq in parsed.get("sub_queries", []):
            sub_queries.append(SubQuery(
                query=sq.get("query", ""),
                target_layer=sq.get("layer", "L1"),
                search_type="hybrid",
                priority=sq.get("priority", 3),
            ))
        if not sub_queries:
            sub_queries = baseline.sub_queries

        search_mode = SearchMode.THINKING if complexity == Complexity.COMPLEX else SearchMode.QUICK
        start_level = _select_start_level(question_type, complexity)

        return QueryPlan(
            original_query=query,
            question_type=question_type,
            complexity=complexity,
            search_mode=search_mode,
            target_entities=entities,
            time_range=time_range,
            suggested_start_level=start_level,
            sub_queries=sub_queries,
            reasoning=parsed.get("reasoning", baseline.reasoning),
        )

    except Exception as e:
        logger.warning("LLM 意图分析失败，使用规则分析: %s", e)
        return baseline
