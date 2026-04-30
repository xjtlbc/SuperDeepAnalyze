"""Tests for Analysis Toolbox tools."""
from app.services.wiki.analysis.report import AnalysisReport
from app.services.wiki.analysis.tools import AnalysisToolbox


def test_record_entity():
    report = AnalysisReport(kb_id="test_kb")
    toolbox = AnalysisToolbox(report)
    eid = toolbox.record_entity("张三", "person", aliases=["小张"], importance=0.9)
    assert eid == "analysis_entity_001"
    assert len(report.entities) == 1
    assert report.entities[0].aliases == ["小张"]


def test_record_relation():
    report = AnalysisReport(kb_id="test_kb")
    toolbox = AnalysisToolbox(report)
    toolbox.record_entity("张三", "person")
    toolbox.record_entity("李四", "person")
    rel = toolbox.record_relation("张三", "李四", "同伙", "原文证据")
    assert "error" not in rel
    assert len(report.entities[0].relations) == 1


def test_record_contradiction():
    report = AnalysisReport(kb_id="test_kb")
    toolbox = AnalysisToolbox(report)
    cid = toolbox.record_contradiction("time_conflict", "矛盾", ["张三"], severity="high")
    assert cid == "contradiction_001"
    assert len(report.contradictions) == 1


def test_entity_resolution_by_alias():
    report = AnalysisReport(kb_id="test_kb")
    toolbox = AnalysisToolbox(report)
    toolbox.record_entity("张三", "person", aliases=["小张"])
    rel = toolbox.record_relation("小张", "张三", "同伙", "原文")  # Use alias as source
    assert "error" not in rel, f"Should resolve alias: {rel}"


def test_record_relation_unknown_entity():
    report = AnalysisReport(kb_id="test_kb")
    toolbox = AnalysisToolbox(report)
    toolbox.record_entity("张三", "person")
    rel = toolbox.record_relation("王五", "张三", "朋友", "无证据")
    assert "error" in rel


if __name__ == "__main__":
    test_record_entity()
    print("test_record_entity PASSED")
    test_record_relation()
    print("test_record_relation PASSED")
    test_record_contradiction()
    print("test_record_contradiction PASSED")
    test_entity_resolution_by_alias()
    print("test_entity_resolution_by_alias PASSED")
    test_record_relation_unknown_entity()
    print("test_record_relation_unknown_entity PASSED")
    print("All wiki_tools tests PASSED")
