"""Subagent dispatcher for parallel task execution with structured reporting."""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine


@dataclass
class SubagentResult:
    """Result from a single subagent task."""
    task_id: str
    status: str  # "ok", "error", "timeout", "cancelled"
    result: Any = None
    error: str = ""
    duration_ms: float = 0


class SubagentDispatcher:
    """Dispatch and manage parallel subagent tasks.

    Usage:
        dispatcher = SubagentDispatcher(max_concurrency=4)
        dispatcher.add_task("task1", coro_fn(arg1))
        dispatcher.add_task("task2", coro_fn(arg2))
        results = await dispatcher.run(progress_cb=cb)
    """

    def __init__(self, max_concurrency: int = 4, timeout: float | None = None):
        self._tasks: list[tuple[str, Coroutine]] = []
        self._max_concurrency = max_concurrency
        self._timeout = timeout
        self._results: list[SubagentResult] = []
        self._lock = asyncio.Lock()
        self._completed = 0

    def add_task(self, task_id: str, coro: Coroutine) -> None:
        """Add a task to the dispatch queue."""
        self._tasks.append((task_id, coro))

    async def run(
        self,
        progress_cb: Callable[[dict], None | Coroutine] | None = None,
    ) -> list[SubagentResult]:
        """Execute all tasks and return structured results."""
        if not self._tasks:
            return []

        total = len(self._tasks)
        semaphore = asyncio.Semaphore(self._max_concurrency)
        self._results = []
        self._completed = 0

        if progress_cb:
            await _cb(progress_cb, {
                "type": "subagent_start",
                "total": total,
                "concurrency": self._max_concurrency,
                "message": f"子代理调度开始: {total} 任务, 并发={self._max_concurrency}",
            })

        async def _run_one(task_id: str, coro: Coroutine):
            async with semaphore:
                start = asyncio.get_running_loop().time()
                try:
                    if self._timeout:
                        result = await asyncio.wait_for(coro, timeout=self._timeout)
                    else:
                        result = await coro
                    status = "ok"
                except asyncio.TimeoutError:
                    result = None
                    status = "timeout"
                except Exception as e:
                    result = None
                    status = "error"

                duration_ms = (asyncio.get_running_loop().time() - start) * 1000

                async with self._lock:
                    self._completed += 1
                    self._results.append(SubagentResult(
                        task_id=task_id,
                        status=status,
                        result=result,
                        error=str(result) if status == "error" else "",
                        duration_ms=duration_ms,
                    ))
                    if progress_cb and self._completed % max(1, total // 10) == 0:
                        await _cb(progress_cb, {
                            "type": "subagent_progress",
                            "completed": self._completed,
                            "total": total,
                            "message": f"子代理进度: {self._completed}/{total}",
                        })

        await asyncio.gather(*[_run_one(tid, coro) for tid, coro in self._tasks])

        ok_count = sum(1 for r in self._results if r.status == "ok")
        if progress_cb:
            await _cb(progress_cb, {
                "type": "subagent_done",
                "completed": self._completed,
                "total": total,
                "ok": ok_count,
                "message": f"子代理调度完成: {ok_count}/{total} 成功",
            })

        return self._results

    def get_successful(self) -> list[SubagentResult]:
        """Return only successful results."""
        return [r for r in self._results if r.status == "ok"]

    def get_failed(self) -> list[SubagentResult]:
        """Return failed/timeout/cancelled results."""
        return [r for r in self._results if r.status != "ok"]


async def _cb(cb: Callable[[dict], None | Coroutine], data: dict):
    result = cb(data)
    if asyncio.iscoroutine(result):
        await result
