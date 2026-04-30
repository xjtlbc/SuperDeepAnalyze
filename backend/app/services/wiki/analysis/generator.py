"""Stage 2: Generate AnalysisReport from extracted structured data with quality gates."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Literal

from app.config import settings
from app.models.config import RoleType
from app.services.wiki.analysis.report import (
    AnalysisReport, Entity, Relation, Mention, Concept,
    Contradiction, Gap, NarrativeThread,
)
from app.services.wiki.analysis.extractor import ExtractionStats


class QualityGateError(Exception):
    """Raised when extracted data fails quality gate."""

    def __init__(self, message: str, stats: ExtractionStats):
        self.message = message
        self.stats = stats
        super().__init__(message)


class ReportGenerator:
    """Stage 2: Converts extracted structured data into AnalysisReport.

    Validates quality, filters low-confidence items, and constructs the
    AnalysisReport data model for downstream catalog/page generation.
    """

    def __init__(self, llm_client, kb_id: str, entity_confidence_threshold: float = 0.3):
        self._llm_client = llm_client
        self._kb_id = kb_id
        self._entity_confidence_threshold = entity_confidence_threshold

    def run(self, extracted: dict, stats: ExtractionStats) -> AnalysisReport:
        """Run quality gate + report generation.

        Args:
            extracted: Dict from AnalysisExtractor with entities, relations, etc.
            stats: ExtractionStats from AnalysisExtractor

        Returns:
            AnalysisReport ready for catalog/page generation

        Raises:
            QualityGateError: If data quality is insufficient
        """
        # Quality gate check
        if not stats.is_valid():
            reasons = []
            if stats.entity_count < 3:
                reasons.append(f"实体数量不足 ({stats.entity_count} < 3)")
            if stats.relation_count < 1:
                reasons.append(f"关系数量不足 ({stats.relation_count} < 1)")
            if stats.avg_entity_confidence < 0.3:
                reasons.append(f"平均置信度过低 ({stats.avg_entity_confidence:.2f} < 0.3)")
            raise QualityGateError(
                f"数据质量门控未通过: {'; '.join(reasons)}",
                stats,
            )

        report = AnalysisReport(kb_id=self._kb_id)

        # Build entity name -> ID mapping
        name_to_id: dict[str, str] = {}

        for e in extracted.get("entities", []):
            # Filter by confidence
            if e.get("confidence", 1.0) < self._entity_confidence_threshold:
                continue

            entity = Entity(
                id=e["id"],
                name=e.get("name", ""),
                type=self._normalize_entity_type(e.get("type", "person")),
                aliases=e.get("aliases", []),
                attributes=e.get("attributes", {}),
                importance=e.get("importance", 0.5),
                confidence=e.get("confidence", 0.8),
            )
            report.entities.append(entity)
            name_to_id[e.get("name", "").lower()] = entity.id

        # Convert relations
        for r in extracted.get("relations", []):
            source_id = self._resolve_relation_name(r.get("source", ""), name_to_id)
            target_id = self._resolve_relation_name(r.get("target", ""), name_to_id)
            if not source_id or not target_id:
                continue

            rel = Relation(
                source_id=source_id,
                target_id=target_id,
                relation_type=r.get("relation_type", "unknown"),
                evidence=r.get("evidence", ""),
                confidence=r.get("confidence", 0.8),
                sources=r.get("sources", []),
            )
            # Attach to both entities
            for entity in report.entities:
                if entity.id in (source_id, target_id):
                    entity.relations.append(rel)

        # Convert concepts
        for c in extracted.get("concepts", []):
            concept = Concept(
                id=f"concept_{len(report.concepts)+1:03d}",
                name=c.get("name", ""),
                description=c.get("description", ""),
                related_entities=c.get("related_entities", []),
                sources=c.get("sources", []),
            )
            report.concepts.append(concept)

        # Convert contradictions
        for c in extracted.get("contradictions", []):
            contradiction = Contradiction(
                id=f"contradiction_{len(report.contradictions)+1:03d}",
                type=self._normalize_contradiction_type(c.get("type", "logical_gap")),
                description=c.get("description", ""),
                involved_entities=c.get("involved_entities", []),
                sources=c.get("sources", []),
                severity=c.get("severity", "medium"),
            )
            report.contradictions.append(contradiction)

        # Convert gaps
        for g in extracted.get("gaps", []):
            gap = Gap(
                id=f"gap_{len(report.knowledge_gaps)+1:03d}",
                description=g.get("description", ""),
                type=self._normalize_gap_type(g.get("type", "unanswered_question")),
                suggestion=g.get("suggestion", ""),
                related_entities=[g["related_entity_id"]] if g.get("related_entity_id") else [],
            )
            report.knowledge_gaps.append(gap)

        # Convert narrative threads
        for t in extracted.get("threads", []):
            thread = NarrativeThread(
                id=f"thread_{len(report.narrative_threads)+1:03d}",
                title=t.get("title", ""),
                description=t.get("description", ""),
                key_entities=t.get("key_entities", []),
                timeline_events=t.get("timeline_events", []),
                thread_type=t.get("type", "subplot"),
            )
            report.narrative_threads.append(thread)

        return report

    def _resolve_relation_name(self, name: str, name_to_id: dict) -> str | None:
        """Resolve relation source/target name to entity ID."""
        name_lower = name.lower()
        if name_lower in name_to_id:
            return name_to_id[name_lower]
        # Fuzzy: try partial match
        for k, v in name_to_id.items():
            if name_lower in k or k in name_lower:
                return v
        return None

    def _normalize_entity_type(self, raw: str) -> Literal["person", "organization", "location", "event", "evidence", "document"]:
        """Map arbitrary entity type strings to valid enum values."""
        valid = {"person", "organization", "location", "event", "evidence", "document"}
        if raw in valid:
            return raw  # type: ignore[return-value]
        # Common Chinese type mappings
        mappings = {
            "人物": "person", "人": "person", "person": "person",
            "组织": "organization", "organization": "organization", "org": "organization",
            "地点": "location", "location": "location", "loc": "location",
            "事件": "event", "event": "event",
            "证据": "evidence", "evidence": "evidence",
            "文档": "document", "document": "document", "doc": "document",
        }
        return mappings.get(raw, "person")  # type: ignore[return-value]

    def _normalize_contradiction_type(self, raw: str) -> Literal["time_conflict", "statement_conflict", "evidence_conflict", "logical_gap"]:
        valid = {"time_conflict", "statement_conflict", "evidence_conflict", "logical_gap"}
        if raw in valid:
            return raw  # type: ignore[return-value]
        mappings = {
            "时间冲突": "time_conflict",
            "陈述矛盾": "statement_conflict",
            "证据矛盾": "evidence_conflict",
            "逻辑漏洞": "logical_gap",
        }
        return mappings.get(raw, "logical_gap")  # type: ignore[return-value]

    def _normalize_gap_type(self, raw: str) -> Literal["isolated_entity", "missing_relation", "unanswered_question", "sparse_community"]:
        valid = {"isolated_entity", "missing_relation", "unanswered_question", "sparse_community"}
        if raw in valid:
            return raw  # type: ignore[return-value]
        mappings = {
            "孤立实体": "isolated_entity",
            "缺失关系": "missing_relation",
            "未解答问题": "unanswered_question",
        }
        return mappings.get(raw, "unanswered_question")  # type: ignore[return-value]
