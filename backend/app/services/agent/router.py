"""Hybrid query router — direct simple queries to fast RAG, complex ones to Agent loop.

Classifies query complexity and routes accordingly:
- SIMPLE + FACTUAL → single hybrid_search + single LLM synthesis (no iteration)
- MEDIUM/COMPLEX → full agentic reAct loop

Inspired by DigitalApplied's hybrid routing pattern for production Agentic RAG.
"""

import json
from typing import Optional

from app.models.config import RoleType
from app.services.agent.intent_analyzer import QueryPlan, Complexity, QuestionType
from app.utils.logging_config import get_logger

logger = get_logger("app.agent.router")


class RouteDecision:
    SIMPLE_RAG = "simple_rag"
    AGENTIC_LOOP = "agentic_loop"


def should_use_simple_rag(query_plan: QueryPlan) -> bool:
    """Determine if a query can be answered via simple RAG without the Agent loop."""
    # Simple + factual → fast path
    if query_plan.complexity == Complexity.SIMPLE and query_plan.question_type == QuestionType.FACTUAL:
        return True
    # Simple + any type with single sub-query → fast path
    if query_plan.complexity == Complexity.SIMPLE and len(query_plan.sub_queries) <= 1:
        return True
    return False


async def run_simple_rag(
    llm_client,
    user_query: str,
    kb_id: str,
    tool_registry=None,
) -> dict:
    """Execute a multi-strategy RAG pass: entity graph + keyword search → LLM synthesis.

    Strategy order (inspired by leohc/DeepAnalyze retriever):
    1. L0 Entity graph lookup — direct entity name matching, no FTS needed
    2. Keyword search with query rewriting — extract keywords from NL question
    3. ProgressiveSearchTool drill-down if available

    Returns a dict with 'content' and 'evidence_refs' suitable for
    yielding as a final_answer event.
    """
    import asyncio
    from app.services.retrieval.hybrid_search import KeywordSearch, _extract_chinese_words

    search_parts: list[str] = []

    # ── Parallel search strategies (Promise.allSettled pattern) ──────

    async def _entity_graph_search():
        """L0: Entity graph direct lookup — no FTS dependency."""
        from app.config import settings
        entities_path = settings.KB_DIR / kb_id / "l0" / "entities.json"
        if not entities_path.exists():
            return None
        with open(entities_path, "r", encoding="utf-8") as f:
            entities = json.load(f)
        matched = [e for e in entities if e.get("name", "") in user_query]
        if not matched:
            return None
        parts = [f"[实体匹配] {json.dumps([{'name': e['name'], 'type': e.get('type', '')} for e in matched[:5]], ensure_ascii=False)}"]
        for ent in matched[:3]:
            aliases = ent.get("aliases", [])
            if aliases:
                parts.append(f"  {ent['name']} 别名: {', '.join(aliases)}")
        return "\n".join(parts)

    def _keyword_search():
        """Keyword search with Chinese word extraction."""
        search_words = _extract_chinese_words(user_query)
        results = []
        seen_keys: set[str] = set()
        for word in search_words[:4]:
            for r in KeywordSearch.search(word, top_k=5, kb_id=kb_id):
                key = f"{r['doc_id']}:{r.get('chunk_id', '')}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    results.append(r)
        if not results:
            return None
        chunks_text = "\n".join(
            f"  [{r['doc_id']}] {r['content'][:150]}"
            for r in results[:8]
        )
        return f"[关键词搜索]\n{chunks_text}"

    def _two_stage_search():
        """Two-stage: abstract-first, then detail with document prioritization."""
        # Stage 1: Search L0 abstracts to find relevant documents
        from app.config import settings
        abstracts_path = settings.KB_DIR / kb_id / "l0" / "entities.json"
        if not abstracts_path.exists():
            return _keyword_search()  # No L0 data, fall back to plain keyword

        search_words = _extract_chinese_words(user_query)
        if not search_words:
            return None

        # Stage 1: Find which docs contain relevant entities
        doc_scores: dict[str, int] = {}
        try:
            with open(abstracts_path, "r", encoding="utf-8") as f:
                entities = json.load(f)
            for ent in entities:
                name = ent.get("name", "")
                if name and name in user_query:
                    for cid in ent.get("source_chunks", [])[:3]:
                        doc_id = cid.rsplit("_chunk_", 1)[0] if "_chunk_" in cid else cid
                        doc_scores[doc_id] = doc_scores.get(doc_id, 0) + 1
        except Exception:
            pass

        # Stage 2: Search with document prioritization
        results = []
        seen_keys: set[str] = set()
        for word in search_words[:3]:
            for r in KeywordSearch.search(word, top_k=8, kb_id=kb_id):
                key = f"{r['doc_id']}:{r.get('chunk_id', '')}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    # Boost score for documents found in Stage 1
                    boost = doc_scores.get(r["doc_id"], 0)
                    results.append((r, boost))

        # Sort: prioritized docs first
        results.sort(key=lambda x: x[1], reverse=True)
        if not results:
            return None

        chunks_text = "\n".join(
            f"  [{'★' if boost > 0 else ' '}] [{r['doc_id']}] {r['content'][:150]}"
            for r, boost in results[:8]
        )
        return f"[两阶段检索 — ★为高相关文档]\n{chunks_text}"

    # ── grep_docs (launched early — runs in parallel with index searches) ──
    async def _grep_raw_docs():
        try:
            import re as _re
            cjk_chars = _re.findall(r'[一-鿿]', user_query)
            terms = set()
            for _i in range(len(cjk_chars) - 1):
                terms.add(''.join(cjk_chars[_i:_i+2]))
            terms.update(cjk_chars)
            skip_words = {"什么", "怎么", "如何", "哪里", "哪个", "为什么", "结合", "看看", "是否", "一下", "这个", "那个", "知识库", "知识"}
            key_terms = sorted(terms - skip_words, key=len, reverse=True)
            # Also add common weapon/property terms to catch answers using different words
            weapon_terms = ["酒瓶", "刀具", "棍棒", "作案工具", "击打", "凶器", "殴打", "伤情", "鉴定", "轻伤", "重伤"]
            extra_terms = [t for t in weapon_terms if t not in terms]
            pattern = "|".join((key_terms[:10] + extra_terms)[:15]) if key_terms else user_query[:30]

            from pathlib import Path
            from app.config import settings
            docs_dir = settings.KB_DIR / kb_id / "documents"
            lines_out = []
            _regex = _re.compile(pattern, _re.IGNORECASE)
            for doc_dir in sorted(docs_dir.iterdir()):
                if not doc_dir.is_dir():
                    continue
                parsed = doc_dir / "parsed.md"
                if not parsed.exists():
                    continue
                file_lines = parsed.read_text(encoding="utf-8", errors="replace").split("\n")
                for _j, line in enumerate(file_lines):
                    if _regex.search(line) and len(lines_out) < 12:
                        ctx_s = max(0, _j - 1)
                        ctx_e = min(len(file_lines), _j + 2)
                        ctx = "\n".join(
                            f"  L{c+1}: {lc[:200]}"
                            for c, lc in enumerate(file_lines[ctx_s:ctx_e], ctx_s)
                        )
                        lines_out.append(f"### {doc_dir.name} L{_j+1}:\n> {line[:250]}\n上下文:\n{ctx}")
            if lines_out:
                top_docs = list(dict.fromkeys(
                    ln.split()[0] for ln in lines_out if ln.startswith("  ")
                ))[:2]
                full_ctx = []
                for ddn in top_docs:
                    try:
                        dp = settings.KB_DIR / kb_id / "documents" / ddn / "parsed.md"
                        if dp.exists():
                            full_ctx.append(f"\n### {ddn} 全文预览:\n{dp.read_text('utf-8', errors='replace')[:1500]}")
                    except Exception:
                        pass
                result = f"[grep原始文档搜索 — 关键词: {pattern[:60]}\n" + "\n".join(lines_out)
                if full_ctx:
                    result += "\n" + "\n".join(full_ctx)
                return result[:4000]
        except Exception as _e:
            logger.warning("grep_docs inner failed: %s", _e)
        return None

    grep_task = asyncio.create_task(_grep_raw_docs())

    # Run all strategies in parallel (Promise.allSettled pattern)
    async def _safe_entity():
        try:
            return await _entity_graph_search()
        except Exception as e:
            logger.debug("Entity graph search failed: %s", e)
            return None

    results = await asyncio.gather(
        _safe_entity(),
        asyncio.to_thread(_keyword_search),
        asyncio.to_thread(_two_stage_search),
        grep_task,
        return_exceptions=True,
    )

    # Collect successful results (Promise.allSettled pattern)
    for r in results:
        if isinstance(r, Exception):
            logger.debug("Search strategy failed: %s", r)
        elif r is not None:
            search_parts.append(r)

    # Step 1c: ProgressiveSearchTool if available and still no results
    try:
        search_words = _extract_chinese_words(user_query)
        kw_results = []
        seen_keys: set[str] = set()
        for word in search_words[:4]:
            for r in KeywordSearch.search(word, top_k=5, kb_id=kb_id):
                key = f"{r['doc_id']}:{r.get('chunk_id', '')}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    kw_results.append(r)
        if kw_results:
            chunks_text = "\n".join(
                f"  [{r['doc_id']}] {r['content'][:150]}"
                for r in kw_results[:8]
            )
            search_parts.append(f"[关键词搜索]\n{chunks_text}")
    except Exception as e:
        logger.debug("Keyword search failed: %s", e)

    # Step 2: Single LLM synthesis
    # Prioritize grep results (raw doc search) over keyword (FTS5 chunk headers)
    grep_parts = [p for p in search_parts if "grep原始文档" in str(p)]
    other_parts = [p for p in search_parts if "grep原始文档" not in str(p)]
    if not search_parts:
        search_text = "（未找到相关搜索结果）"
    else:
        # Grep first (most relevant), then keyword (limited to avoid drowning)
        ordered = grep_parts + [p for p in other_parts[:2]]
        search_text = "\n\n".join(str(p)[:3000] for p in ordered)[:5000]

    messages = [
        {
            "role": "system",
            "content": (
                "你是法律知识库分析助手。基于以下检索结果，回答用户问题。\n"
                "重要：原始文档中可能使用不同的措辞描述同一事物（如用户问'凶器'但文档用'酒瓶'、'作案工具'等）。"
                "请仔细阅读文档全文，找出与用户问题语义相关的信息来回答。\n\n"
                "回答请使用以下Markdown结构（如某节不适用则跳过）：\n"
                "## 案件基本事实\n## 涉案人员\n## 证据链\n## 法律定性\n"
                "每节标注引用来源 [doc_xxx] 或 [doc_xxx L15]。\n"
                "如果检索结果不足以回答，请如实说明。"
            ),
        },
        {
            "role": "user",
            "content": f"检索结果:\n{search_text}\n\n用户问题: {user_query}",
        },
    ]

    try:
        response = await llm_client.chat(
            role=RoleType.MAIN,
            messages=messages,
            temperature=0.3,
        )
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        content = f"搜索完成但合成失败: {e}"

    return {
        "content": content,
        "evidence_refs": [],
        "tool_calls_made": 1,
        "iterations": 1,
    }
