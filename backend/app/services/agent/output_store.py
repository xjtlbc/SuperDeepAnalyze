"""Tool output externalization: save large results to disk, use placeholders in context."""

import json
import logging
import time
import uuid
from pathlib import Path

from app.config import settings

logger = logging.getLogger("app.agent")

MAX_INLINE_CHARS = 4000


class ToolOutputStore:
    """Save large tool outputs to disk, return compact placeholders."""

    def __init__(self, kb_id: str, session_id: str):
        self._dir = settings.DATA_DIR / "tool_outputs" / kb_id / session_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, str] = {}  # output_id -> tool_name

    def store(self, tool_name: str, output: str, max_inline: int = MAX_INLINE_CHARS) -> str:
        """If output exceeds max_inline, save to file and return placeholder."""
        if len(output) <= max_inline:
            return output

        output_id = f"{tool_name}_{uuid.uuid4().hex[:8]}"
        path = self._dir / f"{output_id}.json"

        with open(path, "w", encoding="utf-8") as f:
            json.dump({"tool": tool_name, "output": output, "timestamp": time.time()}, f, ensure_ascii=False)

        self._index[output_id] = tool_name

        preview = output[:200].replace("\n", " ")
        placeholder = (
            f"[结果已外化 ({len(output)} chars): {output_id}]\n"
            f"预览: {preview}...\n"
            f"使用 recall_expand('{output_id}') 获取完整内容"
        )

        logger.debug("Externalized %s output: %s (%d chars)", tool_name, output_id, len(output))
        return placeholder

    def retrieve(self, output_id: str) -> str | None:
        """Retrieve a stored output by ID."""
        if output_id not in self._index:
            # Try direct file lookup
            path = self._dir / f"{output_id}.json"
            if not path.exists():
                return None
        else:
            path = self._dir / f"{output_id}.json"

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("output", "")
        except Exception as e:
            logger.warning("Failed to retrieve externalized output %s: %s", output_id, e)
            return None

    def cleanup_stale(self, max_age_hours: int = 24) -> int:
        """Remove output files older than max_age_hours."""
        removed = 0
        cutoff = time.time() - (max_age_hours * 3600)

        for path in self._dir.glob("*.json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                if data.get("timestamp", 0) < cutoff:
                    path.unlink()
                    removed += 1
            except Exception:
                pass

        return removed

    @property
    def stored_count(self) -> int:
        return len(self._index)
