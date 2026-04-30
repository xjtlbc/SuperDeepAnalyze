"""Shared pytest fixtures for SuperDeepAnalyze tests."""
import pytest
import json
import os
import tempfile


@pytest.fixture
def test_kb_id():
    """Return a test knowledge base ID."""
    return "kb_test_001"


@pytest.fixture
def test_session_id():
    """Return a test session ID."""
    return "sess_test_001"


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create a temporary data directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def sample_tool_result_json():
    """Sample tool result in JSON format with entities."""
    return json.dumps([
        {"name": "张伟", "type": "人物", "role": "主犯"},
        {"name": "刘强", "type": "人物", "role": "主犯"},
        {"name": "华信理财", "type": "组织", "role": "诈骗公司"},
    ])


@pytest.fixture
def sample_tool_result_empty():
    """Empty tool result."""
    return "[]"


@pytest.fixture
def sample_tool_result_text():
    """Plain text tool result with entity-like patterns."""
    return "张伟与刘强于2023年5月在西安市高新区成立了华信理财公司，以高额回报为诱饵实施诈骗。"


@pytest.fixture
def test_case_files():
    """Return paths to test case files."""
    base = os.path.join(os.path.dirname(__file__), "..", "..", "test_data", "cases")
    return {
        "fraud_md": os.path.join(base, "001_zhang_wei_fraud_case.md"),
        "dispute_md": os.path.join(base, "002_lijianhua_contract_dispute.md"),
        "evidence_xlsx": os.path.join(base, "003_evidence_records.xlsx"),
        "injury_md": os.path.join(base, "004_chen_intentional_injury.md"),
    }
