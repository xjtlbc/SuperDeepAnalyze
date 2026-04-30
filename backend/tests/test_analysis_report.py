"""Tests for Analysis Report data models."""
try:
    import pytest
except ImportError:
    pass
from pathlib import Path
from app.services.wiki.analysis.report import (
    AnalysisReport, Entity, Relation, Contradiction,
    Concept, Gap, NarrativeThread, Mention,
)


def test_report_serialization():
    report = AnalysisReport(kb_id="test_kb")
    rel = Relation(
        source_id="e1", target_id="e2",
        relation_type="同伙", evidence="原文引用", confidence=0.85,
        sources=["chunk_001"],
    )
    entity = Entity(
        id="e1", name="张三", type="person",
        aliases=["小张"], attributes={"role": "嫌疑人"},
        relations=[rel], importance=0.9, confidence=0.95,
    )
    report.entities.append(entity)
    report.contradictions.append(Contradiction(
        id="c1", type="time_conflict", description="时间矛盾",
        involved_entities=["张三"], severity="high",
    ))
    report.concepts.append(Concept(
        id="c1", name="权力斗争", description="政治权力争夺",
        related_entities=["e1"],
    ))
    report.knowledge_gaps.append(Gap(
        id="g1", description="缺少关键证词", type="missing_relation",
        suggestion="需要补充证人证词",
    ))
    report.narrative_threads.append(NarrativeThread(
        id="t1", title="主要案件线", description="案件发展主线",
        key_entities=["e1"], thread_type="main",
    ))

    data = report.to_dict()
    restored = AnalysisReport.from_dict(data)
    assert len(restored.entities) == 1
    assert restored.entities[0].name == "张三"
    assert len(restored.entities[0].relations) == 1
    assert restored.entities[0].relations[0].relation_type == "同伙"
    assert len(restored.contradictions) == 1
    assert restored.contradictions[0].severity == "high"
    assert len(restored.concepts) == 1
    assert len(restored.knowledge_gaps) == 1
    assert len(restored.narrative_threads) == 1


def test_report_save_load(tmp_path):
    report = AnalysisReport(kb_id="test_kb")
    report.entities.append(Entity(id="e1", name="Test", type="person"))
    report.entities.append(Entity(id="e2", name="Test2", type="organization"))

    path = report.save_to(tmp_path)
    assert path.exists()
    assert path.name == "analysis_report.json"

    loaded = AnalysisReport.load_from(tmp_path)
    assert len(loaded.entities) == 2
    assert loaded.entities[0].name == "Test"
    assert loaded.entities[1].type == "organization"


def test_empty_report():
    report = AnalysisReport(kb_id="empty_kb")
    data = report.to_dict()
    restored = AnalysisReport.from_dict(data)
    assert restored.kb_id == "empty_kb"
    assert len(restored.entities) == 0


def test_entity_with_mentions():
    entity = Entity(id="e1", name="张三", type="person")
    entity.mentions.append(Mention(doc_id="doc_001", chunk_ids=["chunk_005"], context="提到张三"))
    report = AnalysisReport(kb_id="test_kb")
    report.entities.append(entity)

    data = report.to_dict()
    restored = AnalysisReport.from_dict(data)
    assert len(restored.entities[0].mentions) == 1
    assert restored.entities[0].mentions[0].doc_id == "doc_001"


if __name__ == "__main__":
    test_report_serialization()
    print("test_report_serialization PASSED")
    test_report_save_load(Path("D:/lbc/SuperDeepAnalyze/backend/tests/tmp"))
    print("test_report_save_load PASSED")
    test_empty_report()
    print("test_empty_report PASSED")
    test_entity_with_mentions()
    print("test_entity_with_mentions PASSED")
    print("All analysis_report tests PASSED")
