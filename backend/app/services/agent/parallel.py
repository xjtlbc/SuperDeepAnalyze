"""Parallel research framework for complex multi-direction queries.

Spawns lightweight researcher tasks that each explore a sub-query independently.
Results are merged and returned to the main agent loop.

Inspired by Claude Code's fork subagent pattern and OpenAI Deep Research's
multi-agent pipeline.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from app.models.config import RoleType
from app.utils.logging_config import get_logger

logger = get_logger("app.agent.parallel")


@dataclass
class ResearchSummary:
    """Structured result from a sub-query research task."""
    sub_query: str
    findings: str = ""
    entities_found: list[str] = field(default_factory=list)
    relations_found: list[str] = field(default_factory=list)
    docs_accessed: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    success: bool = True
    error: str = ""


async def run_parallel_research(
    sub_queries: list[str],
    kb_id: str,
    llm_client,
    tool_registry,
    embedding_provider=None,
    max_per_query_seconds: int = 180,
    max_concurrent: int = 3,
) -> list[ResearchSummary]:
    """Execute multiple sub-query research tasks in parallel.

    Each task: search → read top results → synthesize into structured summary.
    Uses semaphore for concurrency control and per-task timeouts.
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _research_one(query: str) -> ResearchSummary:
        async with semaphore:
            start = time.time()
            summary = ResearchSummary(sub_query=query)
            try:
                summary = await asyncio.wait_for(
                    _execute_research(query, kb_id, llm_client, tool_registry, embedding_provider),
                    timeout=max_per_query_seconds,
                )
                summary.elapsed_seconds = time.time() - start
            except asyncio.TimeoutError:
                # Fallback: try a quick keyword search instead of full research
                try:
                    fallback = await asyncio.wait_for(
                        _quick_keyword_search(query, kb_id, tool_registry),
                        timeout=30,
                    )
                    if fallback:
                        summary.findings = f"[简化搜索] {fallback}"
                        summary.success = True
                    else:
                        summary.success = False
                        summary.error = f"研究超时 ({max_per_query_seconds}s)"
                except Exception:
                    summary.success = False
                    summary.error = f"研究超时 ({max_per_query_seconds}s)"
                summary.elapsed_seconds = time.time() - start
            except Exception as e:
                summary.success = False
                summary.error = str(e)
                summary.elapsed_seconds = time.time() - start
            return summary

    results = await asyncio.gather(*[_research_one(q) for q in sub_queries])
    return list(results)


async def _execute_research(
    query: str,
    kb_id: str,
    llm_client,
    tool_registry,
    embedding_provider=None,
) -> ResearchSummary:
    """Execute a single research task: search → read → synthesize."""
    from app.services.agent.tools import ProgressiveSearchTool
    from app.services.agent.utils import extract_entities

    summary = ResearchSummary(sub_query=query)
    search_results_text = ""

    # Step 1: Search using progressive search
    for tool in tool_registry._tools.values():
        if isinstance(tool, ProgressiveSearchTool):
            result = await tool.execute(query=query, kb_id=kb_id, top_k=5)
            search_results_text = result
            break

    if not search_results_text or "Error" in search_results_text[:50]:
        summary.findings = f"搜索 '{query}' 未找到相关结果"
        return summary

    # Step 2: Extract key information from search results
    summary.entities_found = list(extract_entities(search_results_text, max_count=15))

    # Extract doc references
    try:
        data = json.loads(search_results_text)
        docs = set()
        if isinstance(data, dict):
            results_by_level = data.get("results_by_level", [])
            for level_result in results_by_level:
                level_data = level_result.get("data", {})
                for key in ["entities", "summaries", "chunks"]:
                    items = level_data.get(key, [])
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                doc_id = item.get("doc_id", "")
                                if doc_id:
                                    docs.add(doc_id)
        summary.docs_accessed = list(docs)
    except (json.JSONDecodeError, ValueError):
        pass

    # Step 3: LLM synthesis of search results
    try:
        synthesis_prompt = (
            f"基于以下搜索结果，提取关于 '{query}' 的关键信息。\n"
            "输出格式：\n"
            "1. 核心发现（3-5条）\n"
            "2. 关键实体\n"
            "3. 关键关系\n"
            "4. 信息缺口\n\n"
            f"搜索结果：\n{search_results_text[:4000]}"
        )
        response = await llm_client.chat(
            role=RoleType.LIGHTWEIGHT,
            messages=[{"role": "user", "content": synthesis_prompt}],
            temperature=0.3,
        )
        summary.findings = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        # Fallback: use raw search results as findings
        summary.findings = f"LLM合成失败，原始搜索结果摘要: {search_results_text[:1000]}"
        logger.warning("Research synthesis failed for '%s': %s", query, e)

    return summary


async def _quick_keyword_search(query: str, kb_id: str, tool_registry) -> str:
    """Lightweight keyword-only search as a fallback when full research times out."""
    from app.services.retrieval.hybrid_search import KeywordSearch, _extract_chinese_words

    words = _extract_chinese_words(query)
    if not words:
        return ""
    combined = " ".join(words)
    results = KeywordSearch.search(combined, top_k=5, kb_id=kb_id)
    if not results:
        return ""

    parts = []
    for r in results[:5]:
        doc_id = r.get("doc_id", "")
        content = r.get("content", "")[:300]
        parts.append(f"[{doc_id}] {content}")
    return "\n".join(parts)
