"""L1 compiler: generates paragraph summaries, character relations, and contradiction detection."""

import asyncio
import json
import logging
from pathlib import Path

from app.config import settings
from app.models.config import RoleType
from app.services.parsing.chunking import Chunk

logger = logging.getLogger("app.compilation.l1")

# Keywords that indicate a context length error from the LLM provider
_CONTEXT_ERROR_KEYWORDS = [
    "context_length", "maximum context", "token limit",
    "content length too long", "prompt is too long",
    "max_context_length", "exceed", "too long",
]


class L1Compiler:
    """Compile L1 layer: paragraph summaries with relations and contradictions."""

    def __init__(self, llm_client, kb_id: str = ""):
        self._llm_client = llm_client
        self._kb_id = kb_id

    async def generate_summary(self, chunks: list[Chunk], role: RoleType = RoleType.LIGHTWEIGHT, kb_id: str = "", _retry: int = 0) -> dict:
        """Generate L1 summary for a batch of chunks with retry."""
        combined = "\n\n".join(c.content for c in chunks)
        chunk_ids = [c.chunk_id for c in chunks]

        try:
            result = await self._llm_client.summarize_l1(combined, role=role, kb_id=kb_id or self._kb_id)
        except Exception as e:
            if _retry < 2:
                await asyncio.sleep(2 ** _retry)
                return await self.generate_summary(chunks, role=role, kb_id=kb_id, _retry=_retry + 1)
            raise

        summary_text = result.get("summary", "")
        # Detect stub/empty results and retry once with a simplified prompt
        if not summary_text or len(summary_text) < 30:
            if _retry < 1:
                logger.info("L1 summary too short (%d chars), retrying with simplified content", len(summary_text))
                truncated = combined[:3000]  # Send less content on retry
                try:
                    result = await self._llm_client.summarize_l1(truncated, role=role, kb_id=kb_id or self._kb_id)
                    summary_text = result.get("summary", "")
                except Exception:
                    pass

        return {
            "chunk_ids": chunk_ids,
            "summary": summary_text or result.get("raw", ""),
            "entities_mentioned": result.get("entities_mentioned", []),
            "relations": result.get("relations", []),
            "contradictions": result.get("contradictions", []),
        }

    async def generate_excel_l1(
        self,
        analysis: dict,
        chunks: list[Chunk],
        filename: str = "",
        kb_id: str = "",
    ) -> dict:
        """Generate L1 summary for Excel documents using the compact analysis JSON.

        Instead of sending the full L2 text (potentially 20000+ lines) to the
        LLM, this sends the structured analysis JSON (column types, distributions,
        findings) which is typically ~500 lines.  This dramatically reduces token
        consumption while producing higher-quality data-oriented summaries.

        Args:
            analysis: The analysis dict from ExcelProcessResult.analysis
            chunks: The L2 chunks (used for chunk_ids and evidence refs)
            filename: Original filename for context
            kb_id: Knowledge base ID for domain-adaptive prompts

        Returns:
            Dict with chunk_ids, summary (markdown), and metadata
        """
        # Format the analysis into a compact report for the LLM
        report_lines = self._format_excel_analysis_report(analysis, filename)
        chunk_ids = [c.chunk_id for c in chunks]

        prompt = f"""你是数据分析专家。请基于以下 Excel 文件的结构化分析报告，生成一份数据概览文档。

## 要求：
1. **文件概述**：简要描述文件用途和规模
2. **每个 Sheet 的概览**：
   - 表结构（列名、类型、空值情况）
   - 关键分布特征（高基数列、低区分度列等）
   - 数据质量发现（常量列、高空值率等）
3. **可查询的数据维度**：站在用户提问的角度，列出该表能回答哪些类型的问题
   （如"可按日期范围筛选事件""可按类别统计数量""可查找某实体的关联记录"等）
4. **关键实体/字段**：列出最有检索价值的列名（如姓名、日期、金额、案件编号等）

输出纯 Markdown 格式，直接可读。

## 结构化分析报告：

{report_lines}
"""
        messages = [{"role": "user", "content": prompt}]

        try:
            response = await self._llm_client.chat(
                RoleType.LIGHTWEIGHT, messages, temperature=0.3,
            )
            message = response.get("choices", [{}])[0].get("message", {})
            content = message.get("content", "")

            # Extract chunk info from each chunk's metadata
            sheet_map: dict[str, list[str]] = {}
            for c in chunks:
                sheet = getattr(c, "_sheet_name", "")
                if sheet:
                    sheet_map.setdefault(sheet, []).append(c.chunk_id)

            return {
                "chunk_ids": chunk_ids,
                "summary": content,
                "entities_mentioned": [],
                "relations": [],
                "contradictions": [],
                "metadata": {
                    "is_excel": True,
                    "sheet_map": sheet_map,
                    "filename": filename,
                },
            }
        except Exception as e:
            logger.warning("Excel L1 generation failed: %s", e)
            return {
                "chunk_ids": chunk_ids,
                "summary": f"[Excel 分析生成失败: {e}]",
                "entities_mentioned": [],
                "relations": [],
                "contradictions": [],
                "metadata": {
                    "is_excel": True,
                    "sheet_map": {},
                    "filename": filename,
                },
            }

    @staticmethod
    def _format_excel_analysis_report(analysis: dict, filename: str = "") -> str:
        """Format the analysis JSON into a compact text report for the LLM.

        This produces ~500 lines instead of the 20000+ lines of raw L2 markdown,
        dramatically reducing token consumption.
        """
        lines = []

        if filename:
            lines.append(f"# 文件: {filename}")

        sheets = analysis.get("sheets", [])
        lines.append(f"Sheet 数量: {len(sheets)}")
        lines.append("")

        for sheet in sheets:
            name = sheet.get("name", "unknown")
            dims = sheet.get("dimensions", {})
            rows = dims.get("rows", 0)
            cols = dims.get("columns", 0)

            lines.append(f"## Sheet: {name} ({rows}行 x {cols}列)")

            # Banners
            banners = sheet.get("banners", [])
            if banners:
                for b in banners:
                    lines.append(f"**Banner:** {b.get('text', '')}")
                lines.append("")

            # Column info table
            columns = sheet.get("columns", [])
            if columns:
                lines.append("### 列结构")
                lines.append("| 列名 | 类型 | 空值 | 唯一值 | 样本值 |")
                lines.append("|---|---|---|---|---|")
                for col in columns:
                    sample = ", ".join(str(v) for v in col.get("sampleValues", [])[:3])
                    lines.append(
                        f"| {col.get('name', '')} | {col.get('dataType', '')} "
                        f"| {col.get('nullCount', 0)} | {col.get('uniqueCount', 0)} "
                        f"| {sample} |"
                    )
                lines.append("")

            # Distributions
            distributions = sheet.get("distributions", [])
            if distributions:
                lines.append("### 关键分布")
                for dist in distributions:
                    col_name = dist.get("column", "")
                    dtype = dist.get("type", "")
                    stats = dist.get("stats", {})

                    if dtype in ("integer", "float") and stats:
                        lines.append(
                            f"- **{col_name}**: "
                            f"均值={stats.get('mean', '')}, "
                            f"中位数={stats.get('median', '')}, "
                            f"标准差={stats.get('std', '')}, "
                            f"范围=[{stats.get('min', '')}, {stats.get('max', '')}]"
                        )
                    elif dtype == "string" and stats:
                        top = stats.get("topValues", [])[:5]
                        top_str = ", ".join(
                            f"{v.get('value', '')}({v.get('count', '')})"
                            for v in top
                        )
                        lines.append(f"- **{col_name}**: {top_str}")
                    elif dtype == "date" and stats:
                        lines.append(
                            f"- **{col_name}**: "
                            f"{stats.get('earliest', '')} ~ {stats.get('latest', '')}"
                        )
                lines.append("")

            # Findings
            findings = sheet.get("findings", [])
            if findings:
                lines.append("### 数据发现")
                for f in findings:
                    lines.append(f"- [{f.get('type', '')}] {f.get('column', '')}: {f.get('detail', '')}")
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _is_context_error(exc: Exception) -> bool:
        """Check if an exception is due to context length limits."""
        msg = str(exc).lower()
        return any(kw in msg for kw in _CONTEXT_ERROR_KEYWORDS)

    async def compile_batch(
        self,
        chunks: list[Chunk],
        batch_size: int = 50,
        progress_cb=None,
        batch_delay: float = 0.5,
        accel_state: dict | None = None,
        save_cb=None,
    ) -> list[dict]:
        """Process chunks sequentially, with dynamic batch size reduction on context errors.

        If accel_state is provided and count reaches 200, switches to parallel mode
        for remaining batches. Calls save_cb(partial_results) periodically for incremental saves.
        """
        results = []
        effective_batch_size = batch_size
        total_batches = (len(chunks) + batch_size - 1) // batch_size
        i = 0
        save_interval = 1  # Save every batch for crash recovery
        batches_since_save = 0
        start_time = None  # Track for ETA calculation
        batch_timeout = 300  # 5 minutes per batch timeout

        while i < len(chunks):
            # Check if we should switch to acceleration mode
            if accel_state and accel_state["count"] >= 200 and not accel_state["enabled"]:
                accel_state["enabled"] = True
                if progress_cb:
                    result = progress_cb(f"已启用加速模式 (并行 x2, 主模型)")
                    if asyncio.iscoroutine(result):
                        await result
                remaining = chunks[i:]
                parallel_results = await self.compile_batch_parallel(
                    remaining,
                    batch_size=effective_batch_size,
                    max_concurrency=2,
                    progress_cb=progress_cb,
                    role=RoleType.MAIN,
                )
                results.extend(parallel_results)
                return results

            batch = chunks[i:i + effective_batch_size]
            batch_num = len(results) + 1

            # Track start time of first batch for ETA
            if start_time is None:
                import time
                start_time = time.time()

            # Calculate ETA
            eta_str = ""
            if start_time and batch_num > 1:
                import time
                elapsed = time.time() - start_time
                avg_per_batch = elapsed / (batch_num - 1)
                remaining_batches = total_batches - (batch_num - 1)
                eta_seconds = avg_per_batch * remaining_batches
                if eta_seconds > 120:
                    eta_str = f", 预计剩余 {eta_seconds/60:.0f}min"
                elif eta_seconds > 10:
                    eta_str = f", 预计剩余 {eta_seconds:.0f}s"

            if progress_cb:
                result = progress_cb(f"正在生成第 {batch_num}/{total_batches} 批摘要 ({len(batch)} chunks){eta_str}")
                if asyncio.iscoroutine(result):
                    await result

            try:
                summary = await asyncio.wait_for(
                    self.generate_summary(batch),
                    timeout=batch_timeout,
                )
                results.append(summary)
                i += effective_batch_size

                # Count API calls for acceleration tracking
                if accel_state:
                    accel_state["count"] += 1

                # Incremental save every N batches
                if save_cb:
                    batches_since_save += 1
                    if batches_since_save >= save_interval:
                        result = save_cb(list(results))
                        if asyncio.iscoroutine(result):
                            await result
                        batches_since_save = 0
            except Exception as e:
                if isinstance(e, asyncio.TimeoutError):
                    # Retry once: shrink batch for large batches, extend timeout for small ones
                    retry_ok = False
                    if len(batch) > 5:
                        retry_batch = batch[:len(batch) // 2]
                        if progress_cb:
                            result = progress_cb(f"第 {batch_num} 批超时 ({batch_timeout}s)，缩小批次重试 ({len(retry_batch)} chunks)...")
                            if asyncio.iscoroutine(result):
                                await result
                        try:
                            summary = await asyncio.wait_for(
                                self.generate_summary(retry_batch),
                                timeout=batch_timeout,
                            )
                            results.append(summary)
                            i += effective_batch_size
                            retry_ok = True
                        except Exception:
                            pass
                    else:
                        # Small batch (1-5 chunks): retry with doubled timeout
                        extended_timeout = batch_timeout * 2
                        if progress_cb:
                            result = progress_cb(f"第 {batch_num} 批超时 ({batch_timeout}s)，延长超时重试 ({extended_timeout}s)...")
                            if asyncio.iscoroutine(result):
                                await result
                        try:
                            summary = await asyncio.wait_for(
                                self.generate_summary(batch),
                                timeout=extended_timeout,
                            )
                            results.append(summary)
                            i += effective_batch_size
                            retry_ok = True
                        except Exception:
                            pass

                    if not retry_ok:
                        if progress_cb:
                            result = progress_cb(f"第 {batch_num} 批超时，跳过并继续")
                            if asyncio.iscoroutine(result):
                                await result
                        stub = {"chunk_ids": [c.chunk_id if hasattr(c, 'chunk_id') else f"chunk_{i+j}" for j, c in enumerate(batch)],
                                "summary": f"[超时未完成] 第{batch_num}批摘要生成超时",
                                "entities_mentioned": [], "relations": [], "contradictions": [],
                                "_timeout_stub": True}
                        results.append(stub)
                        i += effective_batch_size
                elif self._is_context_error(e):
                    old_size = effective_batch_size
                    effective_batch_size = max(5, old_size // 2)
                    if progress_cb:
                        result = progress_cb(f"上下文超长，批次大小 {old_size} → {effective_batch_size}，重试中...")
                        if asyncio.iscoroutine(result):
                            await result
                    # Don't advance i, retry current position with smaller batch
                else:
                    raise

            if progress_cb:
                result = progress_cb(f"第 {batch_num}/{total_batches} 批完成，累计 {len(results)} 条摘要")
                if asyncio.iscoroutine(result):
                    await result

            # Small delay between batches to avoid rate limits
            if batch_delay > 0 and i < len(chunks):
                await asyncio.sleep(batch_delay)

        # Final save
        if save_cb and results:
            result = save_cb(list(results))
            if asyncio.iscoroutine(result):
                await result

        return results

    async def compile_batch_pool(
        self,
        chunks: list[Chunk],
        batch_size: int = 50,
        progress_cb=None,
        save_cb=None,
    ) -> list[dict]:
        """Shared task queue mode: 4 workers (2 lightweight + 2 main) pulling from a common queue.

        Faster workers automatically complete more tasks, achieving true dynamic load balancing.
        """
        # 1. Split into batches
        batches = [chunks[i:i + batch_size] for i in range(0, len(chunks), batch_size)]
        total = len(batches)

        # 2. Shared task queue: stores (batch_index, batch_chunks)
        queue: asyncio.Queue = asyncio.Queue()
        for idx, batch in enumerate(batches):
            await queue.put((idx, batch))

        results: list[dict | None] = [None] * total
        completed = 0
        lock = asyncio.Lock()

        # 3. 4 workers: 2 lightweight + 2 main
        workers = [
            {"name": "LW-1", "role": RoleType.LIGHTWEIGHT},
            {"name": "LW-2", "role": RoleType.LIGHTWEIGHT},
            {"name": "MAIN-1", "role": RoleType.MAIN},
            {"name": "MAIN-2", "role": RoleType.MAIN},
        ]

        async def _worker(w):
            nonlocal completed
            while not queue.empty():
                try:
                    idx, batch = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                try:
                    summary = await self.generate_summary(batch, role=w["role"])
                    results[idx] = summary
                except Exception as e:
                    results[idx] = {
                        "chunk_ids": [c.chunk_id for c in batch],
                        "summary": "",
                        "entities_mentioned": [],
                        "relations": [],
                        "contradictions": [],
                        "error": str(e),
                    }

                async with lock:
                    completed += 1
                    if progress_cb and completed % 10 == 0:
                        cb_result = progress_cb(f"[加速池] 已完成 {completed}/{total}")
                        if asyncio.iscoroutine(cb_result):
                            await cb_result
                    # Incremental save: every 20 batches
                    if save_cb and completed % 20 == 0:
                        done_results = [r for r in results if r is not None]
                        cb_result = save_cb(done_results)
                        if asyncio.iscoroutine(cb_result):
                            await cb_result

        # 4. Launch 4 workers concurrently
        await asyncio.gather(*[_worker(w) for w in workers])

        # 5. Final save
        if save_cb:
            done_results = [r for r in results if r is not None]
            cb_result = save_cb(done_results)
            if asyncio.iscoroutine(cb_result):
                await cb_result

        return [r for r in results if r is not None]

    async def compile_batch_parallel(
        self,
        chunks: list[Chunk],
        batch_size: int = 50,
        max_concurrency: int = 3,
        progress_cb=None,
        role: RoleType = RoleType.MAIN,
    ) -> list[dict]:
        """Process chunks in parallel batches with semaphore-limited concurrency."""
        batches = [chunks[i:i + batch_size] for i in range(0, len(chunks), batch_size)]
        total = len(batches)
        semaphore = asyncio.Semaphore(max_concurrency)
        lock = asyncio.Lock()
        results: list[dict | None] = [None] * total
        completed = 0

        async def _process_one(idx: int, batch: list[Chunk]):
            nonlocal completed
            async with semaphore:
                try:
                    results[idx] = await self.generate_summary(batch, role=role)
                except Exception as e:
                    results[idx] = {
                        "chunk_ids": [c.chunk_id for c in batch],
                        "summary": "",
                        "entities_mentioned": [],
                        "relations": [],
                        "contradictions": [],
                        "error": str(e),
                    }
                async with lock:
                    completed += 1
                    if progress_cb:
                        cb_result = progress_cb(f"[加速] 已完成 {completed}/{total} 批")
                        if asyncio.iscoroutine(cb_result):
                            await cb_result

        await asyncio.gather(*[_process_one(i, b) for i, b in enumerate(batches)])
        return [r for r in results if r is not None]

    def save(self, results: list[dict], kb_id: str, doc_id: str) -> Path:
        """Save L1 results to filesystem."""
        l1_dir = settings.KB_DIR / kb_id / "documents" / doc_id
        l1_dir.mkdir(parents=True, exist_ok=True)

        output_path = l1_dir / "l1_summaries.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        return output_path

    async def compile(self, chunks: list[Chunk], kb_id: str, doc_id: str) -> Path:
        """Full L1 compilation: generate summaries, save, and generate abstract."""
        results = await self.compile_batch(chunks)
        output_path = self.save(results, kb_id, doc_id)

        # Generate L0 abstract from first L1 summaries
        try:
            from app.services.compilation.abstract_generator import (
                generate_doc_abstract, save_abstract,
            )
            abstract_data = await generate_doc_abstract(
                self._llm_client, results, doc_name=doc_id,
            )
            abstract_data["doc_id"] = doc_id
            save_abstract(abstract_data, kb_id, doc_id)
        except Exception as e:
            logger.warning(
                "Abstract generation failed for %s: %s", doc_id, e,
            )

        return output_path
