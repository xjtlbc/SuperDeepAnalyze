"""Question complexity assessment for progressive disclosure strategy."""

from enum import Enum


class QuestionComplexity(str, Enum):
    """Question complexity levels for retrieval strategy."""
    SIMPLE = "simple"      # Entity queries, timeline queries
    MEDIUM = "medium"      # Relation analysis, event summaries
    COMPLEX = "complex"    # Evidence analysis, causal relationships


def assess_complexity(query: str) -> QuestionComplexity:
    """Assess the complexity of a user question.

    Determines the appropriate retrieval starting level based on
    keywords and question patterns.

    Args:
        query: The user's question string.

    Returns:
        QuestionComplexity: The assessed complexity level.
    """
    simple_keywords = [
        '是谁', '叫什么', '什么时候', '在哪', '时间', '地点', '名字',
        '什么人', '哪个', '几位', '多少', '何时', '哪里', '姓名'
    ]
    medium_keywords = [
        '关系', '关联', '如何', '为什么', '原因', '经过', '摘要', '概述',
        '过程', '情况', '背景', '影响', '演变', '发展', '联系', '区别'
    ]
    # Table+aggregation keywords: these require multi-step reasoning (not simple)
    table_agg_keywords = ['统计', '排名', '最多', '最少', '占比', '分组', '排行']
    if any(kw in query for kw in table_agg_keywords):
        return QuestionComplexity.COMPLEX

    complex_keywords = [
        '证据', '分析', '责任', '法律', '判决', '犯罪', '案件', '关键', '核心',
        '矛盾', '疑点', '争议', '定性', '定罪', '量刑', '依据', '充分', '链条'
    ]

    # Check from most complex to least complex
    for kw in complex_keywords:
        if kw in query:
            return QuestionComplexity.COMPLEX

    for kw in medium_keywords:
        if kw in query:
            return QuestionComplexity.MEDIUM

    for kw in simple_keywords:
        if kw in query:
            return QuestionComplexity.SIMPLE

    # Default to medium complexity
    return QuestionComplexity.MEDIUM