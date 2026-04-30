"""Wiki Analysis Report data models."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
import json
from pathlib import Path
from datetime import datetime, timezone


@dataclass
class Relation:
    source_id: str
    target_id: str
    relation_type: str
    evidence: str
    confidence: float
    sources: list[str] = field(default_factory=list)


@dataclass
class Mention:
    doc_id: str
    chunk_ids: list[str] = field(default_factory=list)
    context: str = ""


@dataclass
class Entity:
    id: str
    name: str
    type: Literal["person", "organization", "location", "event", "evidence", "document"]
    aliases: list[str] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)
    relations: list[Relation] = field(default_factory=list)
    mentions: list[Mention] = field(default_factory=list)
    importance: float = 0.0
    confidence: float = 1.0
    community_id: int = 0


@dataclass
class Concept:
    id: str
    name: str
    description: str
    related_entities: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


@dataclass
class Contradiction:
    id: str
    type: Literal["time_conflict", "statement_conflict", "evidence_conflict", "logical_gap"]
    description: str
    involved_entities: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    severity: Literal["high", "medium", "low"] = "medium"


@dataclass
class Gap:
    id: str
    description: str
    type: Literal["isolated_entity", "missing_relation", "unanswered_question", "sparse_community"]
    suggestion: str
    related_entities: list[str] = field(default_factory=list)


@dataclass
class NarrativeThread:
    id: str
    title: str
    description: str
    key_entities: list[str] = field(default_factory=list)
    timeline_events: list[str] = field(default_factory=list)
    thread_type: Literal["main", "subplot"] = "subplot"


@dataclass
class AnalysisReport:
    kb_id: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: str = "1.0"
    entities: list[Entity] = field(default_factory=list)
    concepts: list[Concept] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    knowledge_gaps: list[Gap] = field(default_factory=list)
    narrative_threads: list[NarrativeThread] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON."""
        def _obj_dict(obj):
            if hasattr(obj, "__dataclass_fields__"):
                return {k: _obj_dict(getattr(obj, k)) for k in obj.__dataclass_fields__}
            if isinstance(obj, list):
                return [_obj_dict(i) for i in obj]
            return obj
        return _obj_dict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> AnalysisReport:
        """Deserialize from dict."""
        report = cls(kb_id=data["kb_id"], generated_at=data.get("generated_at", ""), version=data.get("version", "1.0"))
        for e in data.get("entities", []):
            relations = [Relation(**r) for r in e.get("relations", [])]
            mentions = [Mention(**m) if isinstance(m, dict) else m for m in e.get("mentions", [])]
            report.entities.append(Entity(
                id=e["id"], name=e["name"], type=e["type"],
                aliases=e.get("aliases", []), attributes=e.get("attributes", {}),
                relations=relations, mentions=mentions,
                importance=e.get("importance", 0.0), confidence=e.get("confidence", 1.0),
                community_id=e.get("community_id", 0),
            ))
        for c in data.get("concepts", []):
            report.concepts.append(Concept(**c))
        for c in data.get("contradictions", []):
            report.contradictions.append(Contradiction(**c))
        for g in data.get("knowledge_gaps", []):
            report.knowledge_gaps.append(Gap(**g))
        for t in data.get("narrative_threads", []):
            report.narrative_threads.append(NarrativeThread(**t))
        return report

    def save_to(self, directory: Path) -> Path:
        """Save report to filesystem."""
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "analysis_report.json"
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def load_from(cls, directory: Path) -> AnalysisReport:
        """Load report from filesystem."""
        data = json.loads((directory / "analysis_report.json").read_text(encoding="utf-8"))
        return cls.from_dict(data)
