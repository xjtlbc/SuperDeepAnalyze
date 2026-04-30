"""L1 compiler: generates paragraph summaries, character relations, and contradiction detection."""

import asyncio
import json
from pathlib import Path

from app.config import settings
from app.models.config import RoleType
from app.services.parsing.chunking import Chunk

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

    async def generate_summary(self, chunks: list[Chunk], role: RoleType = RoleType.LIGHTWEIGHT, kb_id: str = "") -> dict:
        """Generate L1 summary for a batch of chunks."""
        combined = "\n\n".join(c.content for c in chunks)
        chunk_ids = [c.chunk_id for c in chunks]

        result = await self._llm_client.summarize_l1(combined, role=role, kb_id=kb_id or self._kb_id)

        return {
            "chunk_ids": chunk_ids,
            "summary": result.get("summary", ""),
            "entities_mentioned": result.get("entities_mentioned", []),
            "relations": result.get("relations", []),
            "contradictions": result.get("contradictions", []),
        }

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
                    if progress_cb:
                        result = progress_cb(f"第 {batch_num} 批超时 ({batch_timeout}s)，跳过并继续")
                        if asyncio.iscoroutine(result):
                            await result
                    # Create a minimal stub for the timed-out batch
                    stub = {"chunk_ids": [c.chunk_id if hasattr(c, 'chunk_id') else f"chunk_{i+j}" for j, c in enumerate(batch)],
                            "summary": f"[超时未完成] 第{batch_num}批摘要生成超时",
                            "entities_mentioned": [], "relations": [], "contradictions": []}
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
        """Full L1 compilation: generate summaries and save."""
        results = await self.compile_batch(chunks)
        return self.save(results, kb_id, doc_id)
