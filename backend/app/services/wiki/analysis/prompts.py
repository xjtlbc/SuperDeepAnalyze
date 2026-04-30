"""Prompts for the Wiki Analysis Agent."""


def build_system_prompt(domain: str) -> str:
    """Build domain-adaptive analysis system prompt."""
    from app.services.prompts.domain import get_domain_config
    cfg = get_domain_config(domain)

    return f"""你是一个{cfg['identity']}。你正在对一个{cfg['material']}知识库进行全面分析。

你的任务是从L1摘要、L0实体库和L2原文中深入分析，提取以下信息：
1. **实体(Entities)**：{cfg['entity_types']}。每个实体需要有别名、属性、重要性评分(0-1)。
2. **关系(Relations)**：实体间的关系，需要引用原文作为证据。
3. **矛盾(Contradictions)**：不一致、冲突、逻辑漏洞。标注严重程度。
4. **概念(Concepts)**：{cfg['material']}中的抽象概念和关键术语。
5. **知识缺口(Knowledge Gaps)**：孤立实体、缺失的关系、未解答的关键问题。
6. **叙事线索(Narrative Threads)**：核心主题和发展脉络。

使用可用的工具深入探索每个实体，不要仅停留在表面信息。对于每个发现，调用对应的record工具进行记录。当连续5次工具调用没有获得新信息时，说明信息已经饱和，可以停止分析。"""


SYSTEM_PROMPT = build_system_prompt("general")

ANALYSIS_OVERVIEW_PROMPT = """以下是知识库 {kb_id} 的全局概览：

## 实体库（L0）
{entity_summary}

## 时间线
{timeline_summary}

## 可用摘要批次
{summary_stats}

请开始你的分析。建议从最重要的实体开始，使用expand_entity工具展开其完整信息，然后读取相关L1摘要和L2原文进行验证。"""


def format_analysis_overview(kb_id: str, entity_summary: str, timeline_summary: str, summary_stats: str) -> str:
    """Format the analysis overview prompt."""
    return ANALYSIS_OVERVIEW_PROMPT.format(
        kb_id=kb_id,
        entity_summary=entity_summary,
        timeline_summary=timeline_summary,
        summary_stats=summary_stats,
    )
