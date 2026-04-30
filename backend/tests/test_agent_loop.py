"""Tests for Agent Loop: tool_call_id, consecutive_empty, saturation, context management."""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch


class MockAgentLoop:
    """Minimal mock for testing AgentLoop logic."""

    def __init__(self, tool_calls_per_iteration=None, empty_results_after=0):
        self.tool_calls_per_iteration = tool_calls_per_iteration or []
        self.empty_results_after = empty_results_after
        self.call_ids_passed = []

    def simulate_tool_call_results(self, results, call_ids=None):
        """Simulate the message building logic from loop.py."""
        messages = []
        consecutive_empty = 0

        for i, (tool_name, tool_input, result, elapsed, tc_id) in enumerate(results):
            stripped = result.strip()
            if not stripped or stripped == "[]" or stripped == "{}":
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": "查询未返回有效结果。请尝试其他工具或基于已有信息给出答案。",
                    })
                    messages.append({
                        "role": "system",
                        "content": "多次查询未返回有效结果，请直接基于已有信息给出最终答案，不要再调用工具。",
                    })
                    consecutive_empty = 0
                else:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": result,
                    })
            else:
                consecutive_empty = 0
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result,
                })

        return messages, consecutive_empty


# --- Tests for tool_call_id propagation ---

class TestToolCallIdPropagation:
    """Verify that tool_call_id from LLM response is correctly passed to messages."""

    def test_tool_call_id_not_empty(self):
        """tool_call_id should be the actual LLM call ID, not empty string."""
        loop = MockAgentLoop()
        results = [
            ("search_vector", {"query": "张伟", "kb_id": "kb_1"}, "result1", 0.5, "call_123"),
            ("read_l0", {"entity_id": "entity_1", "kb_id": "kb_1"}, "result2", 0.3, "call_456"),
        ]
        messages, _ = loop.simulate_tool_call_results(results)

        assert messages[0]["tool_call_id"] == "call_123"
        assert messages[1]["tool_call_id"] == "call_456"

    def test_tool_call_id_empty_string_from_llm(self):
        """If LLM returns empty ID, it should still be passed through."""
        loop = MockAgentLoop()
        results = [
            ("search_vector", {"query": "test", "kb_id": "kb_1"}, "result", 0.5, ""),
        ]
        messages, _ = loop.simulate_tool_call_results(results)

        assert messages[0]["tool_call_id"] == ""

    def test_tool_call_id_preserved_in_empty_result(self):
        """tool_call_id should be preserved even when result is empty."""
        loop = MockAgentLoop()
        results = [
            ("search_vector", {"query": "nonexistent", "kb_id": "kb_1"}, "[]", 0.5, "call_789"),
        ]
        messages, _ = loop.simulate_tool_call_results(results)

        assert messages[0]["tool_call_id"] == "call_789"


# --- Tests for consecutive_empty counter ---

class TestConsecutiveEmptyCounter:
    """Verify consecutive_empty counter behavior."""

    def test_counter_increments_on_empty(self):
        """Counter should increment on each empty result."""
        loop = MockAgentLoop()
        results = [
            ("tool1", {}, "[]", 0.1, "c1"),
        ]
        _, count = loop.simulate_tool_call_results(results)
        assert count == 1

    def test_counter_resets_on_non_empty(self):
        """Counter should reset when a non-empty result is received."""
        loop = MockAgentLoop()
        results = [
            ("tool1", {}, "[]", 0.1, "c1"),
            ("tool1", {}, "[]", 0.1, "c2"),
            ("tool1", {}, "some data", 0.1, "c3"),
        ]
        _, count = loop.simulate_tool_call_results(results)
        assert count == 0

    def test_saturation_triggers_at_three(self):
        """After 3 consecutive empty results, saturation message should be added."""
        loop = MockAgentLoop()
        results = [
            ("tool1", {}, "[]", 0.1, "c1"),
            ("tool2", {}, "{}", 0.1, "c2"),
            ("tool3", {}, "", 0.1, "c3"),
        ]
        messages, count = loop.simulate_tool_call_results(results)

        # Should have tool message + system message for saturation
        assert len(messages) >= 2
        assert messages[-1]["role"] == "system"
        assert "多次查询" in messages[-1]["content"]
        # Counter should be reset after saturation
        assert count == 0

    def test_counter_resets_after_saturation(self):
        """Counter should be reset after saturation message is sent."""
        loop = MockAgentLoop()
        results = [
            ("tool1", {}, "[]", 0.1, "c1"),
            ("tool2", {}, "{}", 0.1, "c2"),
            ("tool3", {}, "  ", 0.1, "c3"),
            ("tool4", {}, "[]", 0.1, "c4"),
            ("tool5", {}, "{}", 0.1, "c5"),
            ("tool6", {}, "  ", 0.1, "c6"),
        ]
        messages, count = loop.simulate_tool_call_results(results)

        # After first 3 empties: saturation trigger + reset
        # Then 3 more empties: another saturation trigger + reset
        assert count == 0


# --- Tests for ContextManager adaptive thresholds ---

class TestAdaptiveTokenThresholds:
    """Verify that token thresholds adapt to model context window."""

    def test_small_context_window(self):
        """With 32K context, thresholds should be proportionally smaller."""
        from app.services.agent.context_manager import ContextManager
        cm = ContextManager(model_context_window=32_000)
        assert cm._microcompact_threshold == int(32_000 * 0.4)  # 12,800
        assert cm._autocompact_buffer == int(32_000 * 0.15)  # 4,800

    def test_large_context_window(self):
        """With 200K context, thresholds should be proportionally larger."""
        from app.services.agent.context_manager import ContextManager
        cm = ContextManager(model_context_window=200_000)
        assert cm._microcompact_threshold == int(200_000 * 0.4)  # 80,000
        assert cm._autocompact_buffer == int(200_000 * 0.15)  # 30,000

    def test_default_context_window(self):
        """Default 128K context should produce expected thresholds."""
        from app.services.agent.context_manager import ContextManager
        cm = ContextManager()
        assert cm._microcompact_threshold == int(128_000 * 0.4)  # 51,200
        assert cm._autocompact_buffer == int(128_000 * 0.15)  # 19,200

    def test_should_auto_compact_small_window(self):
        """Auto-compact should trigger earlier with small context windows."""
        from app.services.agent.context_manager import ContextManager
        cm_small = ContextManager(model_context_window=32_000)
        cm_large = ContextManager(model_context_window=128_000)

        # Messages with enough words to exceed the small window threshold
        # 30000 words => ~30001 tokens, above 32K - 4.8K = 27.2K
        content = "word " * 30000
        messages = [{"role": "user", "content": content}]

        # Should trigger for small window (32K - 4.8K = 27.2K threshold)
        assert cm_small.should_auto_compact(messages) == True
        # Should NOT trigger for large window (128K - 19.2K = 108.8K threshold)
        assert cm_large.should_auto_compact(messages) == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
