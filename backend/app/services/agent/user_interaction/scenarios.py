"""Scenario detection for user interaction."""

from typing import Tuple, Optional, List

from .states import InteractionState, AskUserScenario


def check_info_sufficient(query: str, search_results: list) -> Tuple[InteractionState, Optional[str]]:
    """Check if search results are sufficient to answer the question.

    Args:
        query: User's query string
        search_results: List of search result dicts with 'relevance_score' key

    Returns:
        Tuple of (InteractionState, hint message if state is not CONTINUE)
    """
    # If search results are empty or all have low relevance, need more clues
    if not search_results:
        return (InteractionState.NEEDS_CONTEXT,
                "未找到相关信息，请提供更多线索（如特定人物、时间范围、文档来源）")

    # Check relevance scores
    low_relevance = [r for r in search_results if r.get('relevance_score', 0) < 0.3]
    if len(low_relevance) == len(search_results):
        return (InteractionState.NEEDS_CONTEXT,
                "检索结果相关性较低，请补充更具体的查询关键词")

    return (InteractionState.CONTINUE, None)


def check_ambiguity(query: str) -> Tuple[InteractionState, Optional[str], Optional[List[str]]]:
    """Check if the question has ambiguity.

    Args:
        query: User's query string

    Returns:
        Tuple of (InteractionState, hint message, list of options if state is CLARIFYING)
    """
    # Common ambiguity patterns
    ambiguity_patterns = [
        ('张三', '案件', '张三涉及多个案件，请指定具体案件',
         ['张三的案件A', '张三的案件B', '张三的案件C']),
        ('李四', '合同', '李四涉及多份合同，请指定合同编号或时间',
         ['李四的合同-2023-001', '李四的合同-2024-002', '李四的合同-2024-003']),
    ]

    for name, context, hint, options in ambiguity_patterns:
        if name in query and context in query:
            return (InteractionState.CLARIFYING, hint, options)

    return (InteractionState.CONTINUE, None, None)


def should_confirm_decision(query: str, current_analysis: str) -> Tuple[InteractionState, Optional[str]]:
    """Check if confirmation is needed before giving important conclusions.

    Args:
        query: User's query string
        current_analysis: Current analysis content

    Returns:
        Tuple of (InteractionState, confirmation message if state is CONFIRMING)
    """
    # Key conclusion keywords
    conclusion_keywords = ['责任', '判决', '犯罪', '违法', '关键证据']

    for kw in conclusion_keywords:
        if kw in query:
            return (InteractionState.CONFIRMING,
                    f"即将分析关于'{kw}'的重要结论，请确认分析方向是否正确")

    return (InteractionState.CONTINUE, None)


def detect_blocked_scenario(query: str, error_context: str = None) -> Tuple[InteractionState, Optional[str]]:
    """Detect if the task is blocked and requires human intervention.

    Args:
        query: User's query string
        error_context: Optional error context information

    Returns:
        Tuple of (InteractionState, block message if state is BLOCKED)
    """
    # Block patterns that require human intervention
    block_patterns = [
        ('权限不足', '您没有权限访问此内容，请联系管理员'),
        ('系统错误', '系统发生错误，请联系技术支持'),
        ('数据缺失', '关键数据缺失，无法完成分析，请补充相关文档'),
    ]

    if error_context:
        for pattern, message in block_patterns:
            if pattern in error_context:
                return (InteractionState.BLOCKED, message)

    return (InteractionState.CONTINUE, None)