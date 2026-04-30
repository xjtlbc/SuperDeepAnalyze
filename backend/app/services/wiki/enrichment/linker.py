"""Wikilink enrichment engine: safe replacement mode."""

from __future__ import annotations
import re
import json
import asyncio
from pathlib import Path

from app.config import settings
from app.models.config import RoleType
from app.services.wiki.analysis.report import AnalysisReport
from app.services.wiki.catalog.storage import load_catalog, get_leaf_pages
from app.services.wiki.pages.storage import list_pages, load_page
from app.services.wiki.enrichment.parser import has_wikilink, WIKILINK_PATTERN

ENRICH_SYSTEM_PROMPT = """你是一个wikilink插入助手。你的任务是识别文本中应该插入wikilink的位置。

规则：
1. 只输出JSON数组，不输出其他文字
2. 对于每个应该插入的wikilink，输出 {"term": "术语", "target": "页面路径"}
3. 如果文本中已经有[[wikilink]]包围的术语，不要再输出它
4. 只插入确实存在的页面（在available_pages列表中）"""

ENRICH_USER_PROMPT = """请为以下页面内容插入wikilink。

## 可用页面
{available_pages}

## 页面内容
{page_content}

请输出应该插入的wikilink列表：[{{"term": "术语", "target": "页面路径"}}, ...]"""


class WikilinkEnricher:
    """Enrich wiki pages with safe wikilink insertions."""

    def __init__(self, llm_client, report: AnalysisReport):
        self._llm_client = llm_client
        self._report = report

    async def enrich_all(self, kb_id: str, progress_cb=None) -> int:
        """Enrich all wiki pages."""
        pages = list_pages(kb_id)
        if not pages:
            return 0

        catalog = load_catalog(kb_id)
        available = []
        if catalog:
            leaves = get_leaf_pages(catalog)
            for leaf in leaves:
                available.append(leaf.get("title", ""))

        if progress_cb:
            await _cb(progress_cb, {"phase": "enrichment", "message": f"开始为 {len(pages)} 个页面插入wikilink"})

        total_links = 0
        for i, page_info in enumerate(pages):
            content = load_page(kb_id, page_info["path"])
            if not content:
                continue

            existing = set()
            for m in WIKILINK_PATTERN.finditer(content):
                existing.add(m.group(1).strip())

            entity_names = [e.name for e in self._report.entities if e.name not in existing]
            if not entity_names:
                continue

            prompt = ENRICH_USER_PROMPT.format(
                available_pages=", ".join(available),
                page_content=content[:3000],
            )
            messages = [
                {"role": "system", "content": ENRICH_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            try:
                response = await self._llm_client.chat(
                    RoleType.LIGHTWEIGHT, messages, temperature=0.1,
                )
                llm_text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                replacements = self._extract_json_list(llm_text)

                new_content = content
                links_added = 0
                for r in replacements:
                    term = r.get("term", "")
                    target = r.get("target", "")
                    if term and target:
                        pattern = r'(?<!\[)(?<!\|)\b' + re.escape(term) + r'\b(?![^\[]*\]\])'
                        replacement = f'[[{target}|{term}]]'
                        new_content, count = re.subn(pattern, replacement, new_content, count=1)
                        links_added += count

                if links_added > 0 and new_content != content:
                    fm = page_info.get("frontmatter", {})
                    from app.services.wiki.pages.templates import render_page

                    if new_content.startswith("---"):
                        try:
                            end = new_content.index("---", 3)
                            new_content = new_content[:end + 3] + new_content[end + 3:]
                        except ValueError:
                            pass

                    page_dir = settings.KB_DIR / kb_id / "wiki" / "pages"
                    safe_name = page_info["path"].replace("/", "_").replace("\\", "_")
                    page_path = page_dir / f"{safe_name}.md"
                    page_path.write_text(new_content, encoding="utf-8")
                    total_links += links_added

                if progress_cb and (i + 1) % 10 == 0:
                    await _cb(progress_cb, {
                        "phase": "enrichment",
                        "message": f"已处理 {i+1}/{len(pages)} 个页面，新增 {total_links} 个链接",
                    })
            except Exception:
                pass

        if progress_cb:
            await _cb(progress_cb, {
                "phase": "enrichment",
                "message": f"wikilink增强完成，共插入 {total_links} 个链接",
            })

        return total_links

    def _extract_json_list(self, text: str) -> list[dict]:
        """Extract JSON list from LLM response."""
        if "```json" in text:
            try:
                start = text.index("```json") + 7
                end = text.index("```", start)
                return json.loads(text[start:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass
        if text.strip().startswith("["):
            try:
                return json.loads(text.strip())
            except json.JSONDecodeError:
                pass
        return []


async def _cb(cb, data: dict):
    result = cb(data)
    if asyncio.iscoroutine(result):
        await result
