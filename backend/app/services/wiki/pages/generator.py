"""Page generation orchestrator."""

from __future__ import annotations
import asyncio
import json
from pathlib import Path

from app.config import settings
from app.models.config import RoleType
from app.services.wiki.analysis.report import AnalysisReport
from app.services.wiki.catalog.storage import load_catalog, get_leaf_pages
from app.services.wiki.pages.templates import build_page_context, render_page, build_frontmatter
from app.services.wiki.pages.storage import save_page

def _build_page_system_prompt(domain: str) -> str:
    """Build domain-adaptive page generation system prompt."""
    from app.services.prompts.domain import get_domain_config
    cfg = get_domain_config(domain)
    return f"""你是一个{cfg['material']}wiki撰写专家。你正在为知识库的wiki页面撰写内容。

## 撰写要求：
1. 使用中文撰写
2. 内容基于提供的分析报告数据
3. 在提到其他实体时，使用[[实体名称]]格式创建wikilink
4. {cfg['page_style']}
5. 根据页面类型选择合适的结构
6. 每个陈述都要引用数据来源（在句末标注来源文档/摘要编号）

## 页面结构模板：
# 标题
{cfg['page_structure']}"""


class PageGenerator:
    """Generate wiki pages for all catalog leaf nodes."""

    def __init__(self, llm_client, report: AnalysisReport):
        self._llm_client = llm_client
        self._report = report
        self._max_concurrency = 3
        self._timeout = 300  # 5 minutes per page

    async def generate_all(self, kb_id: str, progress_cb=None) -> list[dict]:
        """Generate all wiki pages in parallel."""
        catalog = load_catalog(kb_id)
        if not catalog:
            raise RuntimeError("No catalog found. Run catalog generation first.")

        leaves = get_leaf_pages(catalog)
        if not leaves:
            raise RuntimeError("No leaf pages in catalog.")

        from app.services.prompts.domain import detect_kb_domain
        domain = detect_kb_domain(kb_id)
        system_prompt = _build_page_system_prompt(domain)

        if progress_cb:
            await _cb(progress_cb, {
                "phase": "pages",
                "message": f"开始生成 {len(leaves)} 个wiki页面，并发数={self._max_concurrency}",
            })

        semaphore = asyncio.Semaphore(self._max_concurrency)
        results: list[dict] = []
        lock = asyncio.Lock()
        completed = 0

        async def _gen_one(leaf: dict):
            nonlocal completed
            async with semaphore:
                try:
                    context = build_page_context(leaf, self._report, domain)
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": context},
                    ]
                    response = await asyncio.wait_for(
                        self._llm_client.chat(RoleType.MAIN, messages, temperature=0.5),
                        timeout=self._timeout,
                    )
                    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

                    entity = self._find_matching_entity(leaf.get("title", ""))
                    fm = build_frontmatter(
                        title=leaf["title"],
                        page_type=entity.type if entity else "general",
                        tags=self._extract_tags(leaf),
                        community=entity.community_id if entity else 0,
                        importance=entity.importance if entity else 0.5,
                    )

                    page_content = render_page(leaf["title"], fm["type"], content, fm)
                    path = leaf["full_path"]
                    save_page(kb_id, path, page_content, fm)

                    async with lock:
                        completed += 1
                        results.append({"path": path, "status": "ok"})
                        if progress_cb and completed % 5 == 0:
                            await _cb(progress_cb, {
                                "phase": "pages",
                                "message": f"已生成 {completed}/{len(leaves)} 个页面",
                            })

                except asyncio.TimeoutError:
                    async with lock:
                        completed += 1
                        results.append({"path": leaf.get("full_path", "unknown"), "status": "timeout"})
                except Exception as e:
                    async with lock:
                        completed += 1
                        results.append({"path": leaf.get("full_path", "unknown"), "status": f"error: {e}"})

        await asyncio.gather(*[_gen_one(leaf) for leaf in leaves])

        if progress_cb:
            ok = sum(1 for r in results if r["status"] == "ok")
            await _cb(progress_cb, {
                "phase": "pages",
                "message": f"页面生成完成: {ok}/{len(leaves)} 成功",
            })

        return results

    def _find_matching_entity(self, title: str):
        """Find entity that matches the page title."""
        for e in self._report.entities:
            if e.name == title or title in e.aliases:
                return e
        return None

    def _extract_tags(self, leaf: dict) -> list[str]:
        """Extract tags from catalog path."""
        path = leaf.get("full_path", "").lower()
        tags = []
        if "人物" in path or "character" in path:
            tags.append("人物")
        if "矛盾" in path or "contradiction" in path:
            tags.append("矛盾")
        if "证据" in path or "evidence" in path:
            tags.append("证据")
        if "时间" in path or "timeline" in path:
            tags.append("时间线")
        return tags


async def _cb(cb, data: dict):
    result = cb(data)
    if asyncio.iscoroutine(result):
        await result
