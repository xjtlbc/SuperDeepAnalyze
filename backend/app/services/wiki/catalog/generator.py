"""Catalog generation agent."""

from __future__ import annotations
import json
import asyncio
from pathlib import Path

from app.config import settings
from app.models.config import RoleType
from app.services.wiki.analysis.report import AnalysisReport
from app.services.wiki.catalog.storage import save_catalog

def _build_catalog_system_prompt(domain: str) -> str:
    """Build domain-adaptive catalog system prompt."""
    from app.services.prompts.domain import get_domain_config
    cfg = get_domain_config(domain)
    return f"""你是一个{cfg['material']}wiki目录架构师。基于分析报告，生成一个层级清晰的wiki目录树。

## 目录结构要求：
{cfg['catalog_structure']}

## 输出规则：
1. 只输出JSON，不要输出其他文字
2. 每个节点必须有 title, path, node_type, description
3. category节点有children数组，page节点没有
4. path必须是URL友好的英文slug（如 核心概念 -> "core-concepts"）
5. 只有page类型的节点才会被生成内容
6. 根据实际内容调整目录结构，不要强行套用不相关的分类"""

CATALOG_USER_PROMPT = """请基于以下分析报告生成wiki目录树：

## 实体概览
共 {entity_count} 个实体，类型分布：{type_breakdown}

## 矛盾点
{contradiction_summary}

## 叙事线索
{thread_summary}

## 知识缺口
{gap_summary}

请生成完整的目录树JSON。"""


class CatalogGenerator:
    """Generate wiki catalog tree from Analysis Report."""

    def __init__(self, llm_client, report: AnalysisReport):
        self._llm_client = llm_client
        self._report = report

    async def generate(self, kb_id: str, max_retries: int = 3, progress_cb=None) -> dict:
        """Generate catalog tree and save it."""
        if progress_cb:
            await _cb(progress_cb, {"phase": "catalog", "message": "生成wiki目录树..."})

        from app.services.prompts.domain import detect_kb_domain
        domain = detect_kb_domain(kb_id)
        system_prompt = _build_catalog_system_prompt(domain)

        type_counts: dict[str, int] = {}
        for e in self._report.entities:
            type_counts[e.type] = type_counts.get(e.type, 0) + 1

        prompt = CATALOG_USER_PROMPT.format(
            entity_count=len(self._report.entities),
            type_breakdown=", ".join(f"{k}:{v}" for k, v in type_counts.items()),
            contradiction_summary="\n".join(f"- {c.description} ({c.severity})" for c in self._report.contradictions[:10]),
            thread_summary="\n".join(f"- {t.title}: {t.description}" for t in self._report.narrative_threads),
            gap_summary="\n".join(f"- {g.description}" for g in self._report.knowledge_gaps[:5]),
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        for attempt in range(max_retries):
            response = await self._llm_client.chat(
                role=RoleType.MAIN, messages=messages, temperature=0.3,
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            catalog = self._extract_json(content)

            if catalog and self._validate_catalog(catalog):
                save_catalog(kb_id, catalog)
                if progress_cb:
                    await _cb(progress_cb, {"phase": "catalog", "message": f"目录树生成成功，共 {self._count_pages(catalog)} 个页面"})
                return catalog

            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": "JSON格式无效，请修正。必须是一个包含title, path, node_type, description的树形结构。"})

        raise RuntimeError(f"Catalog generation failed after {max_retries} attempts")

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON from LLM responses."""
        if "```json" in text:
            try:
                start = text.index("```json") + 7
                end = text.index("```", start)
                return json.loads(text[start:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass
        if text.strip().startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return None

    def _validate_catalog(self, catalog: dict) -> bool:
        """Basic validation: must have title, path, node_type."""
        return "title" in catalog and "path" in catalog and "node_type" in catalog

    def _count_pages(self, node: dict) -> int:
        """Count leaf (page) nodes."""
        children = node.get("children", [])
        if not children:
            return 1
        return sum(self._count_pages(c) for c in children)


async def _cb(cb, data: dict):
    result = cb(data)
    if asyncio.iscoroutine(result):
        await result
