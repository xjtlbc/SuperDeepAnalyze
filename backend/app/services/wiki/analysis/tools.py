"""Record tools for the Analysis Agent to save findings to the Analysis Report."""

from __future__ import annotations
from app.services.wiki.analysis.report import (
    AnalysisReport, Entity, Relation, Mention,
    Contradiction, Concept, Gap, NarrativeThread,
)


class AnalysisToolbox:
    """Container for record_* tools that write to the Analysis Report."""

    def __init__(self, report: AnalysisReport):
        self._report = report
        self._entity_counter = 0
        self._relation_counter = 0
        self._contradiction_counter = 0
        self._concept_counter = 0
        self._gap_counter = 0
        self._thread_counter = 0

    def record_entity(
        self,
        name: str,
        entity_type: str,
        aliases: list[str] | None = None,
        attributes: dict[str, str] | None = None,
        importance: float = 0.5,
        confidence: float = 1.0,
    ) -> str:
        """记录一个实体到分析报告。

        Args:
            name: 实体名称
            entity_type: 类型 (person/organization/location/event/evidence/document)
            aliases: 别名列表
            attributes: 属性字典，如 {"角色": "嫌疑人", "年龄": "35"}
            importance: 重要性评分 (0-1)
            confidence: 置信度 (0-1)

        Returns:
            实体ID
        """
        self._entity_counter += 1
        entity_id = f"analysis_entity_{self._entity_counter:03d}"
        entity = Entity(
            id=entity_id, name=name, type=entity_type,
            aliases=aliases or [], attributes=attributes or {},
            importance=importance, confidence=confidence,
        )
        self._report.entities.append(entity)
        return entity_id

    def record_relation(
        self,
        source_name: str,
        target_name: str,
        relation_type: str,
        evidence: str,
        confidence: float = 0.8,
        sources: list[str] | None = None,
    ) -> dict:
        """记录两个实体之间的关系。

        Args:
            source_name: 源实体名称
            target_name: 目标实体名称
            relation_type: 关系类型
            evidence: 原文证据引用
            confidence: 置信度 (0-1)
            sources: 来源chunk_ids

        Returns:
            关系信息和匹配的实体ID
        """
        source_id = self._resolve_entity_id(source_name)
        target_id = self._resolve_entity_id(target_name)
        if not source_id or not target_id:
            return {"error": f"Entity not found: source={source_name}, target={target_name}"}

        self._relation_counter += 1
        rel = Relation(
            source_id=source_id, target_id=target_id,
            relation_type=relation_type, evidence=evidence,
            confidence=confidence, sources=sources or [],
        )

        for entity in self._report.entities:
            if entity.id in (source_id, target_id):
                entity.relations.append(rel)

        return {"relation_id": f"rel_{self._relation_counter:03d}", "source_id": source_id, "target_id": target_id}

    def record_contradiction(
        self,
        contradiction_type: str,
        description: str,
        involved_entities: list[str],
        sources: list[str] | None = None,
        severity: str = "medium",
    ) -> str:
        """记录一个矛盾点。"""
        self._contradiction_counter += 1
        cid = f"contradiction_{self._contradiction_counter:03d}"
        self._report.contradictions.append(Contradiction(
            id=cid, type=contradiction_type, description=description,
            involved_entities=involved_entities, sources=sources or [],
            severity=severity,
        ))
        return cid

    def record_concept(
        self,
        name: str,
        description: str,
        related_entities: list[str] | None = None,
        sources: list[str] | None = None,
    ) -> str:
        """记录一个抽象概念。"""
        self._concept_counter += 1
        cid = f"concept_{self._concept_counter:03d}"
        resolved_ids = []
        for en in (related_entities or []):
            eid = self._resolve_entity_id(en)
            if eid:
                resolved_ids.append(eid)
        self._report.concepts.append(Concept(
            id=cid, name=name, description=description,
            related_entities=resolved_ids, sources=sources or [],
        ))
        return cid

    def record_gap(
        self,
        description: str,
        gap_type: str,
        suggestion: str,
        related_entities: list[str] | None = None,
    ) -> str:
        """记录一个知识缺口。"""
        self._gap_counter += 1
        gid = f"gap_{self._gap_counter:03d}"
        resolved_ids = []
        for en in (related_entities or []):
            eid = self._resolve_entity_id(en)
            if eid:
                resolved_ids.append(eid)
        self._report.knowledge_gaps.append(Gap(
            id=gid, description=description, type=gap_type,
            suggestion=suggestion, related_entities=resolved_ids,
        ))
        return gid

    def record_thread(
        self,
        title: str,
        description: str,
        key_entities: list[str],
        timeline_events: list[str] | None = None,
        thread_type: str = "subplot",
    ) -> str:
        """记录一个叙事线索。"""
        self._thread_counter += 1
        tid = f"thread_{self._thread_counter:03d}"
        resolved_ids = []
        for en in key_entities:
            eid = self._resolve_entity_id(en)
            if eid:
                resolved_ids.append(eid)
        self._report.narrative_threads.append(NarrativeThread(
            id=tid, title=title, description=description,
            key_entities=resolved_ids, timeline_events=timeline_events or [],
            thread_type=thread_type,
        ))
        return tid

    def add_mention(self, entity_name: str, doc_id: str, chunk_ids: list[str], context: str = "") -> bool:
        """为已有实体添加提及。"""
        entity = self._resolve_entity(entity_name)
        if not entity:
            return False
        entity.mentions.append(Mention(doc_id=doc_id, chunk_ids=chunk_ids, context=context))
        return True

    def _resolve_entity_id(self, name: str) -> str | None:
        """Resolve entity name to ID (exact match + alias match)."""
        for entity in self._report.entities:
            if entity.name == name or name in entity.aliases:
                return entity.id
        return None

    def _resolve_entity(self, name: str) -> Entity | None:
        """Resolve entity name to Entity object."""
        for entity in self._report.entities:
            if entity.name == name or name in entity.aliases:
                return entity
        return None
