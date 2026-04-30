"""Shared test fixtures with mock LLM responses to avoid API credit consumption."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure backend is importable
backend_path = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_path))


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for test isolation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "data"
        data_dir.mkdir()
        yield data_dir


@pytest.fixture
def mock_llm_client():
    """Mock LLM client that returns canned responses without real API calls."""
    client = MagicMock()

    async def mock_chat(role=None, messages=None, tools=None, temperature=0.3):
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "summary": "测试摘要：文档内容分析结果",
                        "entities_mentioned": ["张三", "李四"],
                        "relations": [{"from": "张三", "to": "李四", "type": "同事"}],
                        "contradictions": [],
                    }, ensure_ascii=False),
                }
            }]
        }

    async def mock_summarize_l1(combined, role=None):
        return {
            "summary": "L1 测试摘要",
            "entities_mentioned": ["张三", "李四"],
            "relations": [{"from": "张三", "to": "李四", "type": "同事"}],
            "contradictions": [],
        }

    client.chat = mock_chat
    client.summarize_l1 = mock_summarize_l1
    return client


@pytest.fixture
def mock_embedding_provider():
    """Mock embedding provider that returns random vectors without real API calls."""
    import random
    provider = MagicMock()

    async def mock_embed(texts):
        return [[random.random() for _ in range(768)] for _ in texts]

    provider.embed = mock_embed
    return provider


@pytest.fixture
def sample_kb_data():
    """Sample knowledge base data for testing."""
    return {
        "name": "测试知识库",
        "description": "E2E 测试用知识库",
    }


@pytest.fixture
def sample_multi_hop_query():
    """Sample multi-hop test case."""
    return {
        "query": "裴谦的拳法是谁教的？",
        "expected_entities": ["裴谦", "拳法"],
        "expected_relations": ["教", "传授"],
        "min_iterations": 3,
        "description": "Test multi-hop entity relationship tracing",
    }
