"""Wiki Generation Pipeline: orchestrates analysis -> catalog -> pages -> enrichment."""

from __future__ import annotations
import asyncio
import json
from pathlib import Path

from app.config import settings
from app.models.config import RoleType
from app.models.crud import load_model_configs
from app.models.router import ModelRouter
from app.services.llm.client import LLMClient
from app.services.wiki.analysis.report import AnalysisReport
from app.services.wiki.analysis.agent import AnalysisAgent
from app.services.wiki.analysis.extractor import AnalysisExtractor
from app.services.wiki.analysis.generator import ReportGenerator, QualityGateError
from app.services.wiki.catalog.generator import CatalogGenerator
from app.services.wiki.pages.generator import PageGenerator
from app.services.wiki.enrichment.linker import WikilinkEnricher
from app.services.subagent_dispatcher import SubagentDispatcher


class WikiPipeline:
    """4-stage wiki generation pipeline."""

    def __init__(self, llm_client, kb_id: str):
        self._llm_client = llm_client
        self._kb_id = kb_id

    async def run(self, progress_cb=None) -> dict:
        """Run all 4 stages sequentially."""
        wiki_dir = settings.KB_DIR / self._kb_id / "wiki"

        # Stage 1: Two-Stage Analysis (Extraction + Report Generation)
        if progress_cb:
            await _cb(progress_cb, {"type": "wiki_progress", "phase": "wiki_analysis", "progress": 0, "message": "Wiki阶段1/4: 提取结构化数据..."})

        # Stage 1a: Extract structured data from L0/L1
        extractor = AnalysisExtractor(self._llm_client, self._kb_id)

        def extraction_cb(data: dict):
            progress = data.get("phase") == "extraction" and 10 + int(15 * 0.5)
            if progress_cb:
                asyncio.ensure_future(_cb(progress_cb, {
                    "type": "wiki_progress",
                    "phase": "wiki_analysis",
                    "progress": int(progress) if progress else 10,
                    "message": data.get("message", "提取中..."),
                }))

        extracted, stats = await extractor.run(progress_cb=extraction_cb)

        if progress_cb:
            await _cb(progress_cb, {
                "type": "wiki_progress",
                "phase": "wiki_analysis",
                "progress": 25,
                "message": (
                    f"提取完成: {stats.entity_count} 实体, {stats.relation_count} 关系, "
                    f"平均置信度 {stats.avg_entity_confidence:.2f}"
                ),
            })

        # Stage 1b: Quality gate + report generation
        if progress_cb:
            await _cb(progress_cb, {"type": "wiki_progress", "phase": "wiki_analysis", "progress": 25, "message": "Wiki阶段1/4: 质量门控检查..."})

        try:
            generator = ReportGenerator(self._llm_client, self._kb_id)
            report = generator.run(extracted, stats)
        except QualityGateError as e:
            if progress_cb:
                await _cb(progress_cb, {
                    "type": "wiki_progress",
                    "phase": "wiki_analysis",
                    "progress": 25,
                    "message": f"质量门控未通过: {e.message}，降级使用传统分析Agent...",
                })
            # Fallback: use traditional reAct AnalysisAgent
            if progress_cb:
                await _cb(progress_cb, {"type": "wiki_progress", "phase": "wiki_analysis", "progress": 25, "message": "降级: 启动传统分析Agent..."})

            analysis_agent = AnalysisAgent(self._llm_client, self._kb_id)

            def analysis_cb(data: dict):
                progress = data.get("iteration", 0) / 30 * 25
                if progress_cb:
                    asyncio.ensure_future(_cb(progress_cb, {
                        "type": "wiki_progress",
                        "phase": "wiki_analysis",
                        "progress": int(progress),
                        "message": data.get("message", "分析中..."),
                    }))

            report = await analysis_agent.run(progress_cb=analysis_cb)

        report.save_to(wiki_dir)

        # Stage 2: Catalog Generation
        if progress_cb:
            await _cb(progress_cb, {"type": "wiki_progress", "phase": "wiki_catalog", "progress": 25, "message": "Wiki阶段2/4: 生成目录树..."})

        catalog_gen = CatalogGenerator(self._llm_client, report)

        def catalog_cb(data: dict):
            if progress_cb:
                asyncio.ensure_future(_cb(progress_cb, {
                    "type": "wiki_progress",
                    "phase": "wiki_catalog",
                    "progress": 25 + int(25 * 0.5),
                    "message": data.get("message", "生成目录..."),
                }))

        catalog = await catalog_gen.generate(self._kb_id, progress_cb=catalog_cb)

        # Stage 3: Page Generation
        if progress_cb:
            await _cb(progress_cb, {"type": "wiki_progress", "phase": "wiki_pages", "progress": 50, "message": "Wiki阶段3/4: 生成页面内容..."})

        page_gen = PageGenerator(self._llm_client, report)

        def page_cb(data: dict):
            if progress_cb:
                asyncio.ensure_future(_cb(progress_cb, {
                    "type": "wiki_progress",
                    "phase": "wiki_pages",
                    "progress": 50 + int(35 * 0.5),
                    "message": data.get("message", "生成页面..."),
                }))

        page_results = await page_gen.generate_all(self._kb_id, progress_cb=page_cb)

        # Stage 4: Wikilink Enrichment
        if progress_cb:
            await _cb(progress_cb, {"type": "wiki_progress", "phase": "wiki_enrichment", "progress": 85, "message": "Wiki阶段4/4: 插入交叉链接..."})

        enricher = WikilinkEnricher(self._llm_client, report)
        links_count = await enricher.enrich_all(self._kb_id, progress_cb=lambda d: asyncio.ensure_future(_cb(
            progress_cb, {
                "type": "wiki_progress",
                "phase": "wiki_enrichment",
                "progress": 85 + int(15 * 0.5),
                "message": d.get("message", "插入链接..."),
            }
        )) if progress_cb else None)

        # Done
        pages_ok = sum(1 for r in page_results if r.get("status") == "ok")
        if progress_cb:
            await _cb(progress_cb, {
                "type": "wiki_progress",
                "phase": "wiki_done",
                "progress": 100,
                "message": f"Wiki生成完成! {len(report.entities)} 实体, {pages_ok} 页面, {links_count} wikilink",
            })

        return {
            "entities": len(report.entities),
            "pages_generated": pages_ok,
            "pages_total": len(page_results),
            "wikilinks_inserted": links_count,
            "contradictions": len(report.contradictions),
            "knowledge_gaps": len(report.knowledge_gaps),
        }


async def _cb(cb, data: dict):
    if cb is None:
        return
    result = cb(data)
    if asyncio.iscoroutine(result):
        await result
