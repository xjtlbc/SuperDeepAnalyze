# 两阶段Ingest + 结构化Wiki生成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在L0/L1/L2编译完成后自动触发4阶段Wiki生成Pipeline，将扁平的实体列表升级为层级目录+独立页面的结构化Wiki。

**Architecture:** 新增 `backend/app/services/wiki/` 模块，包含analysis（分析）、catalog（目录）、pages（页面）、enrichment（链接增强）4个子模块。在 `compile.py` 的L0编译完成后插入 `WikiPipeline.run()` 调用。

**Tech Stack:** Python 3.12+, FastAPI, 现有LLMClient复用, python-louvain(新增用于社区检测)

## 技能映射表

| Task | 阶段 | 推荐技能 | 说明 |
|------|------|----------|------|
| 1-2 | 数据模型+社区检测 | systematic-debugging | 确保数据库迁移正确、社区检测算法准确 |
| 3-5 | Analysis阶段 | systematic-debugging | Analysis Agent的reAct循环需要反复调试验证 |
| 6-7 | Catalog+Pages | systematic-debugging | LLM输出格式解析、并行处理竞态 |
| 8-9 | Enrichment | systematic-debugging | Wikilink正则替换安全性验证 |
| 10 | 编译集成+API | verification-before-completion | 每个API端点验证可用性 |
| 11 | 前端渲染 | frontend-testing-best-practices, webapp-testing | E2E测试前端渲染 |
| 12 | 单元测试 | verification-before-completion | 所有测试通过后自动继续 |
| END | 端到端测试 | webapp-testing, systematic-debugging | 完整前后端联调测试 |

---

## File Map

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/app/services/wiki/__init__.py` | 创建 | 模块入口 |
| `backend/app/services/wiki/pipeline.py` | 创建 | 4阶段orchestrator，调度analysis→catalog→pages→enrichment |
| `backend/app/services/wiki/analysis/__init__.py` | 创建 | 模块入口 |
| `backend/app/services/wiki/analysis/report.py` | 创建 | AnalysisReport/Entity/Relation/Contradiction/Concept/Gap/Thread数据模型 |
| `backend/app/services/wiki/analysis/tools.py` | 创建 | record_entity, record_relation, record_contradiction, record_gap, record_thread 工具 |
| `backend/app/services/wiki/analysis/agent.py` | 创建 | Analysis Agent reAct loop |
| `backend/app/services/wiki/analysis/prompts.py` | 创建 | Analysis阶段系统提示词 |
| `backend/app/services/wiki/catalog/__init__.py` | 创建 | 模块入口 |
| `backend/app/services/wiki/catalog/generator.py` | 创建 | Catalog Agent + WriteCatalog tool |
| `backend/app/services/wiki/catalog/storage.py` | 创建 | Catalog JSON持久化 |
| `backend/app/services/wiki/pages/__init__.py` | 创建 | 模块入口 |
| `backend/app/services/wiki/pages/generator.py` | 创建 | Page generation orchestrator（并行处理） |
| `backend/app/services/wiki/pages/templates.py` | 创建 | Page frontmatter模板 |
| `backend/app/services/wiki/pages/storage.py` | 创建 | Page文件持久化 |
| `backend/app/services/wiki/enrichment/__init__.py` | 创建 | 模块入口 |
| `backend/app/services/wiki/enrichment/linker.py` | 创建 | Wikilink enrichment engine |
| `backend/app/services/wiki/enrichment/parser.py` | 创建 | Wikilink解析器 |
| `backend/app/services/retrieval/community.py` | 创建 | Louvain社区检测 |
| `backend/app/api/wiki.py` | 修改 | 新增wiki生成触发API + 页面读取API |
| `backend/app/api/compile.py` | 修改 | L0编译完成后触发WikiPipeline |
| `backend/app/models/database.py` | 修改 | 新增wiki_pages, wiki_catalog表 |
| `backend/requirements.txt` | 修改 | 新增python-louvain, networkx |

---

### Task 1: 数据模型 + 数据库表

**Files:**
- Create: `backend/app/services/wiki/analysis/report.py`
- Modify: `backend/app/models/database.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 创建数据模型文件**

```python
"""Wiki Analysis Report data models."""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
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
```

- [ ] **Step 2: 修改数据库添加wiki表**

修改 `backend/app/models/database.py`，在 `init_db()` 的 `executescript` 末尾（`messages` 表之后）添加：

```python
            CREATE TABLE IF NOT EXISTS wiki_catalog (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                title TEXT NOT NULL,
                path TEXT NOT NULL,
                parent_id TEXT,
                node_order INTEGER NOT NULL DEFAULT 0,
                node_type TEXT NOT NULL DEFAULT 'page',
                description TEXT DEFAULT '',
                FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id),
                FOREIGN KEY (parent_id) REFERENCES wiki_catalog(id)
            );

            CREATE TABLE IF NOT EXISTS wiki_pages (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                catalog_path TEXT NOT NULL,
                title TEXT NOT NULL,
                page_type TEXT NOT NULL,
                content TEXT NOT NULL,
                frontmatter TEXT DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id)
            );

            CREATE TABLE IF NOT EXISTS wiki_analysis (
                id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                report_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id)
            );
```

- [ ] **Step 3: 添加依赖**

在 `backend/requirements.txt` 末尾添加：

```
networkx>=3.0
python-louvain>=0.16
```

- [ ] **Step 4: 验证数据库迁移**

```bash
cd D:\lbc\SuperDeepAnalyze\backend
python -c "from app.models.database import init_db; init_db(); print('DB migration OK')"
```

Expected: "DB migration OK"

---

### Task 2: 社区检测模块

**Files:**
- Create: `backend/app/services/retrieval/community.py`

- [ ] **Step 1: 创建社区检测文件**

```python
"""Louvain community detection for entity grouping."""

import networkx as nx
import community as community_louvain  # python-louvain package


def assign_communities(entities: list[dict]) -> dict[str, int]:
    """Assign community IDs to entities based on their relations.

    Args:
        entities: List of entity dicts with 'id' and 'relations' keys.
                  Each relation dict has 'target_id' key.

    Returns:
        Mapping of entity_id -> community_id.
    """
    if not entities:
        return {}

    # Build graph from entity relations
    G = nx.Graph()
    entity_ids = set()

    for entity in entities:
        eid = entity["id"]
        entity_ids.add(eid)
        G.add_node(eid)

        for rel in entity.get("relations", []):
            target = rel.get("target_id", "")
            if target and target != eid:
                weight = rel.get("confidence", 0.5)
                G.add_edge(eid, target, weight=weight)

    if G.number_of_edges() == 0:
        # No relations, each entity is its own community
        return {eid: i for i, eid in enumerate(entity_ids)}

    # Run Louvain community detection
    partition = community_louvain.best_partition(G, weight="weight", random_state=42)

    return partition
```

- [ ] **Step 2: 单元测试**

```bash
cd D:\lbc\SuperDeepAnalyze\backend
python -c "
from app.services.retrieval.community import assign_communities
entities = [
    {'id': 'e1', 'relations': [{'target_id': 'e2', 'confidence': 0.9}]},
    {'id': 'e2', 'relations': [{'target_id': 'e1', 'confidence': 0.9}]},
    {'id': 'e3', 'relations': []},
]
result = assign_communities(entities)
assert 'e1' in result
assert 'e2' in result
assert 'e3' in result
assert result['e1'] == result['e2'], 'e1 and e2 should be in same community'
print('Community detection test PASSED')
"
```

---

### Task 3: Analysis Prompts

**Files:**
- Create: `backend/app/services/wiki/analysis/prompts.py`
- Create: `backend/app/services/wiki/analysis/__init__.py`

- [ ] **Step 1: 创建空模块入口**

```python
# backend/app/services/wiki/analysis/__init__.py
```

- [ ] **Step 2: 创建Analysis提示词**

```python
"""Prompts for the Wiki Analysis Agent."""

SYSTEM_PROMPT = """你是一个资深法律卷宗分析专家。你正在对一个知识库进行全面分析。

你的任务是从L1摘要、L0实体库和L2原文中深入分析，提取以下信息：
1. **实体(Entities)**：人物、组织、地点、事件、证据、文档。每个实体需要有别名、属性（角色、职业、年龄等）、重要性评分(0-1)。
2. **关系(Relations)**：实体间的关系（同伙、上下级、亲属、对立等），需要引用原文作为证据。
3. **矛盾(Contradictions)**：时间冲突、陈述矛盾、证据不一致、逻辑漏洞。标注严重程度。
4. **概念(Concepts)**：卷宗中的抽象概念（如"权力斗争"、"利益输送"、"预谋犯罪"）。
5. **知识缺口(Knowledge Gaps)**：孤立实体、缺失的关系、未解答的关键问题。
6. **叙事线索(Narrative Threads)**：案件的叙事主线和副线。

使用可用的工具深入探索每个实体，不要仅停留在表面信息。对于每个发现，调用对应的record工具进行记录。当连续5次工具调用没有获得新信息时，说明信息已经饱和，可以停止分析。"""

ANALYSIS_OVERVIEW_PROMPT = """以下是知识库 {kb_id} 的全局概览：

## 实体库（L0）
{entity_summary}

## 时间线
{timeline_summary}

## 可用摘要批次
{summary_stats}

请开始你的分析。建议从最重要的实体开始，使用expand_entity工具展开其完整信息，然后读取相关L1摘要和L2原文进行验证。"""


def format_analysis_overview(kb_id: str, entity_summary: str, timeline_summary: str, summary_stats: str) -> str:
    """Format the analysis overview prompt."""
    return ANALYSIS_OVERVIEW_PROMPT.format(
        kb_id=kb_id,
        entity_summary=entity_summary,
        timeline_summary=timeline_summary,
        summary_stats=summary_stats,
    )
```

---

### Task 4: Analysis Tools (record_* 工具集)

**Files:**
- Create: `backend/app/services/wiki/analysis/tools.py`

- [ ] **Step 1: 创建Analysis工具文件**

```python
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
        # Resolve entity IDs by name
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

        # Add relation to both entities
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
        """记录一个矛盾点。

        Args:
            contradiction_type: 类型 (time_conflict/statement_conflict/evidence_conflict/logical_gap)
            description: 矛盾描述
            involved_entities: 涉及的实体名称列表
            sources: 来源chunk_ids
            severity: 严重程度 (high/medium/low)

        Returns:
            矛盾ID
        """
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
        # Resolve entity names to IDs
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
```

---

### Task 5: Analysis Agent

**Files:**
- Create: `backend/app/services/wiki/analysis/agent.py`
- Modify: `backend/app/services/wiki/__init__.py`

- [ ] **Step 1: 创建wiki模块入口**

```python
# backend/app/services/wiki/__init__.py
```

- [ ] **Step 2: 创建Analysis Agent**

```python
"""Analysis Agent: reAct loop for deep knowledge analysis."""

from __future__ import annotations
import json
import asyncio
from pathlib import Path

from app.config import settings
from app.models.config import RoleType
from app.services.wiki.analysis.report import AnalysisReport
from app.services.wiki.analysis.tools import AnalysisToolbox
from app.services.wiki.analysis.prompts import SYSTEM_PROMPT, format_analysis_overview


class AnalysisAgent:
    """Agent that performs deep analysis on compiled KB data."""

    def __init__(self, llm_client, kb_id: str):
        self._llm_client = llm_client
        self._kb_id = kb_id
        self._report = AnalysisReport(kb_id=kb_id)
        self._toolbox = AnalysisToolbox(self._report)
        self._max_iterations = 30
        self._zero_gain_count = 0

    async def run(self, progress_cb=None) -> AnalysisReport:
        """Run the analysis reAct loop."""
        if progress_cb:
            await _cb(progress_cb, {"phase": "analysis", "message": "初始化分析Agent..."})

        # Gather context from existing L0/L1 data
        context = self._gather_context()

        # Build initial prompt
        prompt = format_analysis_overview(
            kb_id=self._kb_id,
            entity_summary=context["entity_summary"],
            timeline_summary=context["timeline_summary"],
            summary_stats=context["summary_stats"],
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        iteration = 0
        tools_used = []

        while iteration < self._max_iterations:
            iteration += 1
            if progress_cb:
                await _cb(progress_cb, {"phase": "analysis", "iteration": iteration, "message": f"分析迭代 {iteration}/{self._max_iterations}"})

            # Call LLM with tools
            tool_definitions = self._get_tool_definitions()
            response = await self._llm_client.chat(
                role=RoleType.MAIN,
                messages=messages,
                temperature=0.3,
                tools=tool_definitions,
            )

            # Check for tool calls
            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {})
            tool_calls = message.get("tool_calls", None)
            content = message.get("content", "")

            if tool_calls:
                # Execute tool calls
                for tc in tool_calls:
                    tc_id = tc["id"]
                    tc_name = tc["function"]["name"]
                    tc_args = json.loads(tc["function"]["arguments"])
                    result = self._execute_tool(tc_name, tc_args)

                    messages.append({
                        "role": "assistant",
                        "tool_calls": [tc],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                    tools_used.append(tc_name)

                self._zero_gain_count = 0
            else:
                # No tool call — check if we should continue
                if content and len(content.strip()) > 10:
                    # LLM is providing text analysis, record findings if any
                    messages.append({"role": "assistant", "content": content})
                    self._zero_gain_count = 0
                else:
                    self._zero_gain_count += 1

                if self._zero_gain_count >= 3:
                    if progress_cb:
                        await _cb(progress_cb, {"phase": "analysis", "message": "信息饱和，分析完成"})
                    break

            # Safety break: if LLM keeps calling the same tool, stop
            if len(tools_used) > 50:
                break

        # Post-processing: assign communities
        self._assign_communities()

        if progress_cb:
            await _cb(progress_cb, {
                "phase": "analysis",
                "message": f"分析完成: {len(self._report.entities)} 实体, "
                          f"{len(self._report.contradictions)} 矛盾, "
                          f"{len(self._report.knowledge_gaps)} 缺口",
            })

        return self._report

    def _gather_context(self) -> dict:
        """Gather existing L0/L1 data as analysis context."""
        kb_dir = settings.KB_DIR / self._kb_id

        # L0 entities summary
        entity_summary = ""
        entities_path = kb_dir / "l0" / "entities.json"
        if entities_path.exists():
            entities = json.loads(entities_path.read_text(encoding="utf-8"))
            lines = [f"- {e['name']} ({e.get('type', 'unknown')})" for e in entities[:50]]
            entity_summary = "\n".join(lines)
            if len(entities) > 50:
                entity_summary += f"\n... 共 {len(entities)} 个实体"

        # Timeline summary
        timeline_summary = ""
        timeline_path = kb_dir / "l0" / "timeline.json"
        if timeline_path.exists():
            events = json.loads(timeline_path.read_text(encoding="utf-8"))
            lines = [f"- {e.get('time', '?')}: {e.get('description', '')}" for e in events[:30]]
            timeline_summary = "\n".join(lines)

        # L1 summary stats
        summary_stats = ""
        total_summaries = 0
        total_chunks = 0
        l1_dir = kb_dir / "documents"
        if l1_dir.exists():
            for doc_dir in l1_dir.iterdir():
                l1_path = doc_dir / "l1_summaries.json"
                if l1_path.exists():
                    summaries = json.loads(l1_path.read_text(encoding="utf-8"))
                    total_summaries += len(summaries)
                    for s in summaries:
                        total_chunks += len(s.get("chunk_ids", []))
        summary_stats = f"共 {total_summaries} 批摘要, 覆盖 {total_chunks} 个文本块"

        return {
            "entity_summary": entity_summary,
            "timeline_summary": timeline_summary,
            "summary_stats": summary_stats,
        }

    def _get_tool_definitions(self) -> list[dict]:
        """Return OpenAI function-calling definitions for record tools."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "record_entity",
                    "description": "记录一个实体到分析报告",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "实体名称"},
                            "entity_type": {
                                "type": "string", "enum": ["person", "organization", "location", "event", "evidence", "document"],
                                "description": "实体类型",
                            },
                            "aliases": {"type": "array", "items": {"type": "string"}, "description": "别名列表"},
                            "attributes": {"type": "object", "description": "属性，如角色、职业、年龄"},
                            "importance": {"type": "number", "description": "重要性评分 (0-1)"},
                            "confidence": {"type": "number", "description": "置信度 (0-1)"},
                        },
                        "required": ["name", "entity_type"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "record_relation",
                    "description": "记录两个实体之间的关系",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "source_name": {"type": "string", "description": "源实体名称"},
                            "target_name": {"type": "string", "description": "目标实体名称"},
                            "relation_type": {"type": "string", "description": "关系类型，如'同伙'、'上下级'、'亲属'、'对立'"},
                            "evidence": {"type": "string", "description": "原文证据引用"},
                            "confidence": {"type": "number", "description": "置信度 (0-1)"},
                            "sources": {"type": "array", "items": {"type": "string"}, "description": "来源chunk_ids"},
                        },
                        "required": ["source_name", "target_name", "relation_type", "evidence"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "record_contradiction",
                    "description": "记录一个矛盾点",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "contradiction_type": {
                                "type": "string",
                                "enum": ["time_conflict", "statement_conflict", "evidence_conflict", "logical_gap"],
                            },
                            "description": {"type": "string", "description": "矛盾描述"},
                            "involved_entities": {"type": "array", "items": {"type": "string"}, "description": "涉及的实体名称"},
                            "sources": {"type": "array", "items": {"type": "string"}, "description": "来源"},
                            "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                        },
                        "required": ["contradiction_type", "description", "involved_entities"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "record_concept",
                    "description": "记录一个抽象概念",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "概念名称"},
                            "description": {"type": "string", "description": "概念描述"},
                            "related_entities": {"type": "array", "items": {"type": "string"}, "description": "相关实体"},
                            "sources": {"type": "array", "items": {"type": "string"}, "description": "来源"},
                        },
                        "required": ["name", "description"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "record_gap",
                    "description": "记录一个知识缺口",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string", "description": "缺口描述"},
                            "gap_type": {
                                "type": "string",
                                "enum": ["isolated_entity", "missing_relation", "unanswered_question", "sparse_community"],
                            },
                            "suggestion": {"type": "string", "description": "建议"},
                            "related_entities": {"type": "array", "items": {"type": "string"}, "description": "相关实体"},
                        },
                        "required": ["description", "gap_type", "suggestion"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "record_thread",
                    "description": "记录一个叙事线索",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "线索标题"},
                            "description": {"type": "string", "description": "线索描述"},
                            "key_entities": {"type": "array", "items": {"type": "string"}, "description": "关键实体名称"},
                            "timeline_events": {"type": "array", "items": {"type": "string"}, "description": "相关时间线事件"},
                            "thread_type": {"type": "string", "enum": ["main", "subplot"], "description": "线索类型"},
                        },
                        "required": ["title", "description", "key_entities"],
                    },
                },
            },
        ]

    def _execute_tool(self, name: str, args: dict) -> dict:
        """Execute a record tool by name."""
        toolbox = self._toolbox
        try:
            if name == "record_entity":
                eid = toolbox.record_entity(
                    name=args["name"], entity_type=args["entity_type"],
                    aliases=args.get("aliases", []), attributes=args.get("attributes", {}),
                    importance=args.get("importance", 0.5), confidence=args.get("confidence", 1.0),
                )
                return {"entity_id": eid, "status": "ok"}
            elif name == "record_relation":
                result = toolbox.record_relation(
                    source_name=args["source_name"], target_name=args["target_name"],
                    relation_type=args["relation_type"], evidence=args["evidence"],
                    confidence=args.get("confidence", 0.8), sources=args.get("sources", []),
                )
                return result
            elif name == "record_contradiction":
                cid = toolbox.record_contradiction(
                    contradiction_type=args["contradiction_type"],
                    description=args["description"],
                    involved_entities=args["involved_entities"],
                    sources=args.get("sources", []),
                    severity=args.get("severity", "medium"),
                )
                return {"contradiction_id": cid, "status": "ok"}
            elif name == "record_concept":
                cid = toolbox.record_concept(
                    name=args["name"], description=args["description"],
                    related_entities=args.get("related_entities", []),
                    sources=args.get("sources", []),
                )
                return {"concept_id": cid, "status": "ok"}
            elif name == "record_gap":
                gid = toolbox.record_gap(
                    description=args["description"], gap_type=args["gap_type"],
                    suggestion=args["suggestion"],
                    related_entities=args.get("related_entities", []),
                )
                return {"gap_id": gid, "status": "ok"}
            elif name == "record_thread":
                tid = toolbox.record_thread(
                    title=args["title"], description=args["description"],
                    key_entities=args["key_entities"],
                    timeline_events=args.get("timeline_events", []),
                    thread_type=args.get("thread_type", "subplot"),
                )
                return {"thread_id": tid, "status": "ok"}
            else:
                return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            return {"error": str(e)}

    def _assign_communities(self):
        """Run Louvain community detection on entities."""
        from app.services.retrieval.community import assign_communities

        entity_data = []
        for e in self._report.entities:
            entity_data.append({
                "id": e.id,
                "relations": [{"target_id": r.target_id, "confidence": r.confidence} for r in e.relations],
            })

        partition = assign_communities(entity_data)
        for e in self._report.entities:
            e.community_id = partition.get(e.id, 0)


async def _cb(cb, data: dict):
    """Handle sync/async callback."""
    result = cb(data)
    if asyncio.iscoroutine(result):
        await result
```

---

### Task 6: Catalog Generation

**Files:**
- Create: `backend/app/services/wiki/catalog/__init__.py`
- Create: `backend/app/services/wiki/catalog/generator.py`
- Create: `backend/app/services/wiki/catalog/storage.py`

- [ ] **Step 1: 创建模块入口**

```python
# backend/app/services/wiki/catalog/__init__.py
```

- [ ] **Step 2: Catalog Storage**

```python
"""Catalog tree storage to SQLite."""

from __future__ import annotations
import json
from pathlib import Path
from app.models.database import get_connection


def save_catalog(kb_id: str, catalog_tree: dict) -> None:
    """Save catalog tree to both SQLite and filesystem."""
    kb_dir = _kb_dir(kb_id)
    wiki_dir = kb_dir / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    # Save to filesystem
    catalog_path = wiki_dir / "catalog.json"
    catalog_path.write_text(json.dumps(catalog_tree, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save to SQLite
    conn = get_connection()
    try:
        conn.execute("DELETE FROM wiki_catalog WHERE kb_id = ?", (kb_id,))
        conn.execute("BEGIN IMMEDIATE")
        _save_node(conn, kb_id, catalog_tree, parent_id=None)
        conn.commit()
    finally:
        conn.close()


def _save_node(conn, kb_id: str, node: dict, parent_id: str | None) -> None:
    """Recursively save a catalog node."""
    import uuid
    node_id = str(uuid.uuid4())[:8]
    conn.execute(
        """INSERT INTO wiki_catalog (id, kb_id, title, path, parent_id, node_order, node_type, description)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            node_id, kb_id, node["title"], node.get("path", ""),
            parent_id, node.get("order", 0), node.get("node_type", "page"),
            node.get("description", ""),
        ),
    )
    for child in node.get("children", []):
        _save_node(conn, kb_id, child, parent_id=node_id)


def load_catalog(kb_id: str) -> dict | None:
    """Load catalog tree from filesystem (primary source)."""
    catalog_path = _kb_dir(kb_id) / "wiki" / "catalog.json"
    if not catalog_path.exists():
        return None
    return json.loads(catalog_path.read_text(encoding="utf-8"))


def get_leaf_pages(catalog_tree: dict) -> list[dict]:
    """Extract all leaf (page) nodes from catalog tree."""
    leaves = []
    def _walk(node, path=""):
        current_path = f"{path}/{node['path']}" if path else node["path"]
        children = node.get("children", [])
        if not children or node.get("node_type") == "page":
            leaves.append({**node, "full_path": current_path})
        else:
            for child in children:
                _walk(child, current_path)
    _walk(catalog_tree)
    return leaves


def _kb_dir(kb_id: str) -> Path:
    from app.config import settings
    return settings.KB_DIR / kb_id
```

- [ ] **Step 3: Catalog Generator**

```python
"""Catalog generation agent."""

from __future__ import annotations
import json
import asyncio
from pathlib import Path

from app.config import settings
from app.models.config import RoleType
from app.services.wiki.analysis.report import AnalysisReport
from app.services.wiki.catalog.storage import save_catalog

CATALOG_SYSTEM_PROMPT = """你是一个法律卷宗wiki目录架构师。基于分析报告，生成一个层级清晰的wiki目录树。

## 目录结构要求：
- 案件概述 (overview)
- 涉案人物 (characters) → 按社区/重要性分为主要人物、次要人物
- 组织与机构 (organizations)
- 时间线与事件 (timeline)
- 证据链 (evidence)
- 矛盾与疑点 (contradictions)
- 知识缺口 (gaps)

## 输出规则：
1. 只输出JSON，不要输出其他文字
2. 每个节点必须有 title, path, node_type, description
3. category节点有children数组，page节点没有
4. path必须是URL友好的英文slug（如 涉案人物 → "characters"）
5. 只有page类型的节点才会被生成内容"""

CATALOG_USER_PROMPT = """请基于以下分析报告生成wiki目录树：

## 实体概览
共 {entity_count} 个实体，类型分布：{type_breakdown}

## 矛盾点
{contradiction_summary}

## 叙事线索
{thread_summary}

## 知识缺口
{gap_summary}

请生成完整的目录树JSON。"""


class CatalogGenerator:
    """Generate wiki catalog tree from Analysis Report."""

    def __init__(self, llm_client, report: AnalysisReport):
        self._llm_client = llm_client
        self._report = report

    async def generate(self, kb_id: str, max_retries: int = 3, progress_cb=None) -> dict:
        """Generate catalog tree and save it."""
        if progress_cb:
            await _cb(progress_cb, {"phase": "catalog", "message": "生成wiki目录树..."})

        type_counts: dict[str, int] = {}
        for e in self._report.entities:
            type_counts[e.type] = type_counts.get(e.type, 0) + 1

        prompt = CATALOG_USER_PROMPT.format(
            entity_count=len(self._report.entities),
            type_breakdown=", ".join(f"{k}:{v}" for k, v in type_counts.items()),
            contradiction_summary="\n".join(f"- {c.description} ({c.severity})" for c in self._report.contradictions[:10]),
            thread_summary="\n".join(f"- {t.title}: {t.description}" for t in self._report.narrative_threads),
            gap_summary="\n".join(f"- {g.description}" for g in self._report.knowledge_gaps[:5]),
        )

        messages = [
            {"role": "system", "content": CATALOG_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        for attempt in range(max_retries):
            response = await self._llm_client.chat(
                role=RoleType.MAIN, messages=messages, temperature=0.3,
            )

            # Extract JSON from response
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            catalog = self._extract_json(content)

            if catalog and self._validate_catalog(catalog):
                save_catalog(kb_id, catalog)
                if progress_cb:
                    await _cb(progress_cb, {"phase": "catalog", "message": f"目录树生成成功，共 {self._count_pages(catalog)} 个页面"})
                return catalog

            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": "JSON格式无效，请修正。必须是一个包含title, path, node_type, description的树形结构。"})

        raise RuntimeError(f"Catalog generation failed after {max_retries} attempts")

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON from LLM response."""
        if "```json" in text:
            try:
                start = text.index("```json") + 7
                end = text.index("```", start)
                return json.loads(text[start:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass
        if text.strip().startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return None

    def _validate_catalog(self, catalog: dict) -> bool:
        """Basic validation: must have title, path, node_type."""
        return "title" in catalog and "path" in catalog and "node_type" in catalog

    def _count_pages(self, node: dict) -> int:
        """Count leaf (page) nodes."""
        children = node.get("children", [])
        if not children:
            return 1
        return sum(self._count_pages(c) for c in children)


async def _cb(cb, data: dict):
    result = cb(data)
    if asyncio.iscoroutine(result):
        await result
```

---

### Task 7: Page Generation

**Files:**
- Create: `backend/app/services/wiki/pages/__init__.py`
- Create: `backend/app/services/wiki/pages/generator.py`
- Create: `backend/app/services/wiki/pages/templates.py`
- Create: `backend/app/services/wiki/pages/storage.py`

- [ ] **Step 1: 创建模块入口**

```python
# backend/app/services/wiki/pages/__init__.py
```

- [ ] **Step 2: Page Templates**

```python
"""Wiki page templates and frontmatter."""

PAGE_TEMPLATE = """---
title: {title}
type: {page_type}
created: {created}
tags: {tags}
sources: {sources}
community: {community}
importance: {importance}
---

# {title}

{content}
"""


def build_frontmatter(
    title: str,
    page_type: str,
    tags: list[str] | None = None,
    sources: list[dict] | None = None,
    community: int = 0,
    importance: float = 0.0,
) -> dict:
    """Build frontmatter dict for a wiki page."""
    from datetime import datetime, timezone
    return {
        "title": title,
        "type": page_type,
        "created": datetime.now(timezone.utc).isoformat(),
        "tags": tags or [],
        "sources": sources or [],
        "community": community,
        "importance": importance,
    }


def render_page(title: str, page_type: str, content: str, frontmatter: dict) -> str:
    """Render a complete wiki page with frontmatter."""
    fm = frontmatter.copy()
    tags_str = str(fm.get("tags", []))
    sources_str = str(fm.get("sources", []))
    return PAGE_TEMPLATE.format(
        title=title,
        page_type=page_type,
        created=fm.get("created", ""),
        tags=tags_str,
        sources=sources_str,
        community=fm.get("community", 0),
        importance=fm.get("importance", 0.0),
        content=content,
    )


def build_page_context(catalog_node: dict, report) -> str:
    """Build context string for page generation based on catalog node and report data."""
    path = catalog_node.get("full_path", catalog_node.get("path", ""))
    title = catalog_node.get("title", "")
    description = catalog_node.get("description", "")

    parts = [f"请为wiki页面 '{title}' (路径: {path}) 生成内容。", f"页面描述: {description}", ""]

    # Include relevant entities based on path keywords
    if "人物" in title or "character" in path.lower():
        persons = [e for e in report.entities if e.type == "person"]
        parts.append(f"## 相关人物实体（共{len(persons)}个）")
        for e in persons[:20]:
            aliases = f"，别名：{', '.join(e.aliases)}" if e.aliases else ""
            attrs = f"，属性：{e.attributes}" if e.attributes else ""
            parts.append(f"- {e.name}{aliases}{attrs}")

    if "矛盾" in title or "contradiction" in path.lower():
        parts.append("## 矛盾点")
        for c in report.contradictions:
            parts.append(f"- [{c.severity}] {c.description} (涉及: {', '.join(c.involved_entities)})")

    if "缺口" in title or "gap" in path.lower():
        parts.append("## 知识缺口")
        for g in report.knowledge_gaps:
            parts.append(f"- {g.description} (建议: {g.suggestion})")

    if "叙事" in title or "thread" in path.lower():
        parts.append("## 叙事线索")
        for t in report.narrative_threads:
            parts.append(f"- {t.title}: {t.description}")

    return "\n".join(parts)
```

- [ ] **Step 3: Page Storage**

```python
"""Wiki page file storage."""

from __future__ import annotations
import json
from pathlib import Path
from app.config import settings


def save_page(kb_id: str, catalog_path: str, content: str, frontmatter: dict) -> Path:
    """Save a wiki page to filesystem."""
    wiki_dir = settings.KB_DIR / kb_id / "wiki" / "pages"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    # Use catalog_path as filename (slugified)
    safe_name = catalog_path.replace("/", "_").replace("\\", "_")
    page_path = wiki_dir / f"{safe_name}.md"

    page_path.write_text(content, encoding="utf-8")

    # Also save metadata to SQLite
    from app.models.database import get_connection
    import uuid
    conn = get_connection()
    try:
        page_id = str(uuid.uuid4())[:8]
        conn.execute(
            """INSERT OR REPLACE INTO wiki_pages
               (id, kb_id, catalog_path, title, page_type, content, frontmatter, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'completed')""",
            (
                page_id, kb_id, catalog_path,
                frontmatter.get("title", ""), frontmatter.get("type", ""),
                content, json.dumps(frontmatter, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return page_path


def load_page(kb_id: str, catalog_path: str) -> str | None:
    """Load a wiki page from filesystem."""
    wiki_dir = settings.KB_DIR / kb_id / "wiki" / "pages"
    safe_name = catalog_path.replace("/", "_").replace("\\", "_")
    page_path = wiki_dir / f"{safe_name}.md"

    if not page_path.exists():
        return None
    return page_path.read_text(encoding="utf-8")


def list_pages(kb_id: str) -> list[dict]:
    """List all wiki pages for a KB."""
    wiki_dir = settings.KB_DIR / kb_id / "wiki" / "pages"
    if not wiki_dir.exists():
        return []

    pages = []
    for f in wiki_dir.glob("*.md"):
        content = f.read_text(encoding="utf-8")
        # Extract frontmatter
        if content.startswith("---"):
            end = content.index("---", 3)
            import yaml
            try:
                fm = yaml.safe_load(content[3:end])
            except Exception:
                fm = {}
            pages.append({
                "path": f.stem,
                "title": fm.get("title", f.stem),
                "type": fm.get("type", "unknown"),
                "frontmatter": fm,
            })
    return pages
```

- [ ] **Step 4: Page Generator**

```python
"""Page generation orchestrator."""

from __future__ import annotations
import asyncio
import json
from pathlib import Path

from app.config import settings
from app.models.config import RoleType
from app.services.wiki.analysis.report import AnalysisReport
from app.services.wiki.catalog.storage import load_catalog, get_leaf_pages
from app.services.wiki.pages.templates import build_page_context, render_page, build_frontmatter
from app.services.wiki.pages.storage import save_page

PAGE_SYSTEM_PROMPT = """你是一个法律卷宗wiki撰写专家。你正在为知识库的wiki页面撰写内容。

## 撰写要求：
1. 使用中文撰写
2. 内容基于提供的分析报告数据
3. 在提到其他实体时，使用[[实体名称]]格式创建wikilink
4. 保持客观、专业的法律文档风格
5. 包含：基本信息、关系网、涉案时间线、关键证据、矛盾点（根据页面类型调整结构）
6. 每个陈述都要引用数据来源（在句末标注来源文档/摘要编号）

## 页面结构模板：
# 标题
## 基本信息
## 关系网
## 涉案时间线
## 关键证据
## 矛盾点（如适用）"""


class PageGenerator:
    """Generate wiki pages for all catalog leaf nodes."""

    def __init__(self, llm_client, report: AnalysisReport):
        self._llm_client = llm_client
        self._report = report
        self._max_concurrency = 3
        self._timeout = 300  # 5 minutes per page

    async def generate_all(self, kb_id: str, progress_cb=None) -> list[dict]:
        """Generate all wiki pages in parallel."""
        catalog = load_catalog(kb_id)
        if not catalog:
            raise RuntimeError("No catalog found. Run catalog generation first.")

        leaves = get_leaf_pages(catalog)
        if not leaves:
            raise RuntimeError("No leaf pages in catalog.")

        if progress_cb:
            await _cb(progress_cb, {
                "phase": "pages",
                "message": f"开始生成 {len(leaves)} 个wiki页面，并发数={self._max_concurrency}",
            })

        semaphore = asyncio.Semaphore(self._max_concurrency)
        results: list[dict] = []
        lock = asyncio.Lock()
        completed = 0

        async def _gen_one(leaf: dict):
            nonlocal completed
            async with semaphore:
                try:
                    context = build_page_context(leaf, self._report)
                    messages = [
                        {"role": "system", "content": PAGE_SYSTEM_PROMPT},
                        {"role": "user", "content": context},
                    ]
                    response = await asyncio.wait_for(
                        self._llm_client.chat(RoleType.MAIN, messages, temperature=0.5),
                        timeout=self._timeout,
                    )
                    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

                    # Build frontmatter
                    entity = self._find_matching_entity(leaf.get("title", ""))
                    fm = build_frontmatter(
                        title=leaf["title"],
                        page_type=entity.type if entity else "general",
                        tags=self._extract_tags(leaf),
                        community=entity.community_id if entity else 0,
                        importance=entity.importance if entity else 0.5,
                    )

                    page_content = render_page(leaf["title"], fm["type"], content, fm)
                    path = leaf["full_path"]
                    save_page(kb_id, path, page_content, fm)

                    async with lock:
                        completed += 1
                        results.append({"path": path, "status": "ok"})
                        if progress_cb and completed % 5 == 0:
                            await _cb(progress_cb, {
                                "phase": "pages",
                                "message": f"已生成 {completed}/{len(leaves)} 个页面",
                            })

                except asyncio.TimeoutError:
                    async with lock:
                        completed += 1
                        results.append({"path": leaf.get("full_path", "unknown"), "status": "timeout"})
                except Exception as e:
                    async with lock:
                        completed += 1
                        results.append({"path": leaf.get("full_path", "unknown"), "status": f"error: {e}"})

        await asyncio.gather(*[_gen_one(leaf) for leaf in leaves])

        if progress_cb:
            ok = sum(1 for r in results if r["status"] == "ok")
            await _cb(progress_cb, {
                "phase": "pages",
                "message": f"页面生成完成: {ok}/{len(leaves)} 成功",
            })

        return results

    def _find_matching_entity(self, title: str):
        """Find entity that matches the page title."""
        for e in self._report.entities:
            if e.name == title or title in e.aliases:
                return e
        return None

    def _extract_tags(self, leaf: dict) -> list[str]:
        """Extract tags from catalog path."""
        path = leaf.get("full_path", "").lower()
        tags = []
        if "人物" in path or "character" in path:
            tags.append("人物")
        if "矛盾" in path or "contradiction" in path:
            tags.append("矛盾")
        if "证据" in path or "evidence" in path:
            tags.append("证据")
        if "时间" in path or "timeline" in path:
            tags.append("时间线")
        return tags


async def _cb(cb, data: dict):
    result = cb(data)
    if asyncio.iscoroutine(result):
        await result
```

---

### Task 8: Wikilink Enrichment

**Files:**
- Create: `backend/app/services/wiki/enrichment/__init__.py`
- Create: `backend/app/services/wiki/enrichment/linker.py`
- Create: `backend/app/services/wiki/enrichment/parser.py`

- [ ] **Step 1: 创建模块入口**

```python
# backend/app/services/wiki/enrichment/__init__.py
```

- [ ] **Step 2: Wikilink Parser**

```python
"""Wikilink parser and renderer."""

import re


# Match [[target|display]] or [[target]]
WIKILINK_PATTERN = re.compile(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')


def extract_wikilinks(text: str) -> list[dict]:
    """Extract all wikilinks from text."""
    links = []
    for match in WIKILINK_PATTERN.finditer(text):
        links.append({
            "target": match.group(1).strip(),
            "display": match.group(2).strip() if match.group(2) else match.group(1).strip(),
        })
    return links


def has_wikilink(text: str, target: str) -> bool:
    """Check if text already contains a wikilink to target."""
    for match in WIKILINK_PATTERN.finditer(text):
        if match.group(1).strip() == target:
            return True
    return False
```

- [ ] **Step 3: Wikilink Enrichment Engine**

```python
"""Wikilink enrichment engine: safe replacement mode."""

from __future__ import annotations
import re
import json
import asyncio
from pathlib import Path

from app.config import settings
from app.models.config import RoleType
from app.services.wiki.analysis.report import AnalysisReport
from app.services.wiki.catalog.storage import load_catalog, get_leaf_pages
from app.services.wiki.pages.storage import list_pages, load_page, save_page
from app.services.wiki.enrichment.parser import has_wikilink, WIKILINK_PATTERN

ENRICH_SYSTEM_PROMPT = """你是一个wikilink插入助手。你的任务是识别文本中应该插入wikilink的位置。

规则：
1. 只输出JSON，不输出其他文字
2. 对于每个应该插入的wikilink，输出 {"term": "术语", "target": "页面路径"}
3. 如果文本中已经有[[wikilink]]包围的术语，不要再输出它
4. 只插入确实存在的页面（在available_pages列表中）"""

ENRICH_USER_PROMPT = """请为以下页面内容插入wikilink。

## 可用页面
{available_pages}

## 页面内容
{page_content}

请输出应该插入的wikilink列表：[{{"term": "术语", "target": "页面路径"}}, ...]"""


class WikilinkEnricher:
    """Enrich wiki pages with safe wikilink insertions."""

    def __init__(self, llm_client, report: AnalysisReport):
        self._llm_client = llm_client
        self._report = report

    async def enrich_all(self, kb_id: str, progress_cb=None) -> int:
        """Enrich all wiki pages."""
        pages = list_pages(kb_id)
        if not pages:
            return 0

        # Build available pages map: entity name -> catalog path
        catalog = load_catalog(kb_id)
        available = []
        if catalog:
            leaves = get_leaf_pages(catalog)
            for leaf in leaves:
                available.append(leaf.get("title", ""))

        if progress_cb:
            await _cb(progress_cb, {"phase": "enrichment", "message": f"开始为 {len(pages)} 个页面插入wikilink"})

        total_links = 0
        for i, page_info in enumerate(pages):
            content = load_page(kb_id, page_info["path"])
            if not content:
                continue

            # Check for existing wikilinks to avoid duplicates
            existing = set()
            for m in WIKILINK_PATTERN.finditer(content):
                existing.add(m.group(1).strip())

            # Build entity names from report
            entity_names = [e.name for e in self._report.entities if e.name not in existing]

            if not entity_names:
                continue

            # Ask LLM for wikilink replacements
            prompt = ENRICH_USER_PROMPT.format(
                available_pages=", ".join(available),
                page_content=content[:3000],  # Limit context
            )
            messages = [
                {"role": "system", "content": ENRICH_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            try:
                response = await self._llm_client.chat(
                    RoleType.LIGHTWEIGHT, messages, temperature=0.1,
                )
                llm_text = response.get("choices", [{}])[0].get("message", {}).get("content", "")

                # Extract JSON
                replacements = self._extract_json_list(llm_text)

                # Apply safe replacements
                new_content = content
                links_added = 0
                for r in replacements:
                    term = r.get("term", "")
                    target = r.get("target", "")
                    if term and target:
                        # Only replace if term appears as standalone text (not inside existing wikilink)
                        # Use word boundary for safety
                        pattern = r'(?<!\[)(?<!\|)\b' + re.escape(term) + r'\b(?![^\[]*\]\])'
                        replacement = f'[[{target}|{term}]]'
                        new_content, count = re.subn(pattern, replacement, new_content, count=1)
                        links_added += count

                if links_added > 0:
                    # Save updated content
                    # Re-read frontmatter
                    fm = page_info.get("frontmatter", {})
                    from app.services.wiki.pages.templates import render_page
                    # We need to preserve frontmatter, so replace only the content part
                    if new_content.startswith("---"):
                        end = new_content.index("---", 3)
                        old_content = new_content[end + 3:]
                        save_page(kb_id, page_info["path"], new_content, fm)

                    total_links += links_added

                if progress_cb and (i + 1) % 10 == 0:
                    await _cb(progress_cb, {
                        "phase": "enrichment",
                        "message": f"已处理 {i+1}/{len(pages)} 个页面，新增 {total_links} 个链接",
                    })

            except Exception:
                pass

        if progress_cb:
            await _cb(progress_cb, {
                "phase": "enrichment",
                "message": f"wikilink增强完成，共插入 {total_links} 个链接",
            })

        return total_links

    def _extract_json_list(self, text: str) -> list[dict]:
        """Extract JSON list from LLM response."""
        if "```json" in text:
            try:
                start = text.index("```json") + 7
                end = text.index("```", start)
                return json.loads(text[start:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass
        if text.strip().startswith("["):
            try:
                return json.loads(text.strip())
            except json.JSONDecodeError:
                pass
        return []


async def _cb(cb, data: dict):
    result = cb(data)
    if asyncio.iscoroutine(result):
        await result
```

---

### Task 9: Wiki Pipeline Orchestrator

**Files:**
- Create: `backend/app/services/wiki/pipeline.py`

- [ ] **Step 1: 创建Pipeline文件**

```python
"""Wiki Generation Pipeline: orchestrates analysis -> catalog -> pages -> enrichment."""

from __future__ import annotations
import asyncio
import json
from pathlib import Path

from app.config import settings
from app.models.config import RoleType
from app.models.crud import load_model_configs
from app.models.router import ModelRouter
from app.services.llm.client import LLMClient
from app.services.wiki.analysis.report import AnalysisReport
from app.services.wiki.analysis.agent import AnalysisAgent
from app.services.wiki.catalog.generator import CatalogGenerator
from app.services.wiki.pages.generator import PageGenerator
from app.services.wiki.enrichment.linker import WikilinkEnricher


class WikiPipeline:
    """4-stage wiki generation pipeline."""

    def __init__(self, llm_client, kb_id: str):
        self._llm_client = llm_client
        self._kb_id = kb_id

    async def run(self, progress_cb=None) -> dict:
        """Run all 4 stages sequentially."""
        wiki_dir = settings.KB_DIR / self._kb_id / "wiki"

        # Stage 1: Analysis
        if progress_cb:
            await _cb(progress_cb, {"type": "wiki_progress", "phase": "wiki_analysis", "progress": 0, "message": "Wiki阶段1/4: 开始深度分析..."})

        analysis_agent = AnalysisAgent(self._llm_client, self._kb_id)

        def analysis_cb(data: dict):
            progress = data.get("iteration", 0) / 30 * 25
            if progress_cb:
                _cb(progress_cb, {
                    "type": "wiki_progress",
                    "phase": "wiki_analysis",
                    "progress": int(progress),
                    "message": data.get("message", "分析中..."),
                })

        report = await analysis_agent.run(progress_cb=analysis_cb)
        report.save_to(wiki_dir)

        # Stage 2: Catalog Generation
        if progress_cb:
            await _cb(progress_cb, {"type": "wiki_progress", "phase": "wiki_catalog", "progress": 25, "message": "Wiki阶段2/4: 生成目录树..."})

        catalog_gen = CatalogGenerator(self._llm_client, report)

        def catalog_cb(data: dict):
            if progress_cb:
                _cb(progress_cb, {
                    "type": "wiki_progress",
                    "phase": "wiki_catalog",
                    "progress": 25 + int(25 * 0.5),
                    "message": data.get("message", "生成目录..."),
                })

        catalog = await catalog_gen.generate(self._kb_id, progress_cb=catalog_cb)

        # Stage 3: Page Generation
        if progress_cb:
            await _cb(progress_cb, {"type": "wiki_progress", "phase": "wiki_pages", "progress": 50, "message": "Wiki阶段3/4: 生成页面内容..."})

        page_gen = PageGenerator(self._llm_client, report)

        def page_cb(data: dict):
            if progress_cb:
                _cb(progress_cb, {
                    "type": "wiki_progress",
                    "phase": "wiki_pages",
                    "progress": 50 + int(35 * 0.5),
                    "message": data.get("message", "生成页面..."),
                })

        page_results = await page_gen.generate_all(self._kb_id, progress_cb=page_cb)

        # Stage 4: Wikilink Enrichment
        if progress_cb:
            await _cb(progress_cb, {"type": "wiki_progress", "phase": "wiki_enrichment", "progress": 85, "message": "Wiki阶段4/4: 插入交叉链接..."})

        enricher = WikilinkEnricher(self._llm_client, report)
        links_count = await enricher.enrich_all(self._kb_id, progress_cb=lambda d: _cb(
            progress_cb, {
                "type": "wiki_progress",
                "phase": "wiki_enrichment",
                "progress": 85 + int(15 * 0.5),
                "message": d.get("message", "插入链接..."),
            }
        ) if progress_cb else None)

        # Done
        pages_ok = sum(1 for r in page_results if r.get("status") == "ok")
        if progress_cb:
            await _cb(progress_cb, {
                "type": "wiki_progress",
                "phase": "wiki_done",
                "progress": 100,
                "message": f"Wiki生成完成! {len(report.entities)} 实体, {pages_ok} 页面, {links_count} wikilink",
            })

        return {
            "entities": len(report.entities),
            "pages_generated": pages_ok,
            "pages_total": len(page_results),
            "wikilinks_inserted": links_count,
            "contradictions": len(report.contradictions),
            "knowledge_gaps": len(report.knowledge_gaps),
        }


async def _cb(cb, data: dict):
    if cb is None:
        return
    result = cb(data)
    if asyncio.iscoroutine(result):
        await result
```

---

### Task 10: 编译流程集成 + API端点

**Files:**
- Modify: `backend/app/api/compile.py`
- Modify: `backend/app/api/wiki.py`

- [ ] **Step 1: 在compile.py中集成Wiki Pipeline**

在 `compile.py` 的 `run_compilation` 函数中，L0编译完成后（第277-278行 `await l0.compile(all_l1_results, kb_id)` 之后），添加：

找到第277-278行：
```python
    # L0 compile
    if all_l1_results:
        l0 = L0Compiler(llm_client)
        await l0.compile(all_l1_results, kb_id)
```

修改为：
```python
    # L0 compile
    if all_l1_results:
        l0 = L0Compiler(llm_client)
        await l0.compile(all_l1_results, kb_id)

        # Trigger Wiki Generation Pipeline
        from app.services.wiki.pipeline import WikiPipeline

        async def wiki_progress_cb(data: dict):
            msg = data.get("message", "")
            await _send_progress(progress_cb, {
                "type": data.get("type", "wiki_progress"),
                "phase": data.get("phase", "wiki"),
                "progress": data.get("progress", 0),
                "message": f"[Wiki] {msg}",
            })

        try:
            pipeline = WikiPipeline(llm_client, kb_id)
            wiki_result = await pipeline.run(progress_cb=wiki_progress_cb)
            await _send_progress(progress_cb, {
                "type": "wiki_progress",
                "phase": "wiki_done",
                "progress": 100,
                "message": f"Wiki生成完成: {wiki_result}",
            })
        except Exception as wiki_error:
            await _send_progress(progress_cb, {
                "type": "wiki_progress",
                "phase": "wiki_error",
                "message": f"Wiki生成失败: {wiki_error}",
            })
```

- [ ] **Step 2: 增强wiki.py添加页面读取API**

在 `backend/app/api/wiki.py` 末尾添加以下端点：

```python
@router.get("/{kb_id}/catalog")
async def get_wiki_catalog(kb_id: str):
    """Get wiki catalog tree."""
    from app.services.wiki.catalog.storage import load_catalog
    catalog = load_catalog(kb_id)
    if not catalog:
        raise HTTPException(status_code=404, detail="No catalog found")
    return catalog


@router.get("/{kb_id}/page")
async def get_wiki_page(kb_id: str, path: str):
    """Get a specific wiki page by catalog path."""
    from app.services.wiki.pages.storage import load_page
    content = load_page(kb_id, path)
    if not content:
        raise HTTPException(status_code=404, detail=f"Page not found: {path}")

    # Parse frontmatter
    fm = {}
    body = content
    if content.startswith("---"):
        try:
            end = content.index("---", 3)
            import yaml
            fm = yaml.safe_load(content[3:end]) or {}
            body = content[end + 3:]
        except (ValueError, Exception):
            pass

    return {"frontmatter": fm, "content": body}


@router.get("/{kb_id}/pages")
async def list_wiki_pages(kb_id: str):
    """List all wiki pages."""
    from app.services.wiki.pages.storage import list_pages
    pages = list_pages(kb_id)
    return {"pages": pages, "count": len(pages)}


@router.get("/{kb_id}/analysis")
async def get_wiki_analysis(kb_id: str):
    """Get the analysis report."""
    from app.config import settings
    from app.services.wiki.analysis.report import AnalysisReport
    wiki_dir = settings.KB_DIR / kb_id / "wiki"
    report_path = wiki_dir / "analysis_report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="No analysis report found")
    data = json.loads(report_path.read_text(encoding="utf-8"))
    return data


@router.post("/{kb_id}/generate")
async def trigger_wiki_generation(kb_id: str):
    """Manually trigger wiki generation (for re-generation)."""
    from app.models.crud import load_model_configs
    from app.models.router import ModelRouter
    from app.services.llm.client import LLMClient
    from app.services.wiki.pipeline import WikiPipeline

    db_configs = load_model_configs()
    if not db_configs:
        raise HTTPException(status_code=400, detail="No model configuration found")

    router_obj = ModelRouter()
    router_obj.register(db_configs)
    llm_client = LLMClient(router_obj)

    pipeline = WikiPipeline(llm_client, kb_id)
    result = await pipeline.run()
    return result
```

---

### Task 11: 前端Wiki页面渲染

**Files:**
- Create: `frontend/src/components/pages/WikiPageRenderer.tsx`
- Modify: `frontend/src/components/pages/WikiView.tsx`

- [ ] **Step 1: 创建WikiPageRenderer组件**

```tsx
// frontend/src/components/pages/WikiPageRenderer.tsx
import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface WikiPageProps {
  content: string
  frontmatter?: Record<string, any>
  className?: string
}

function parseWikilink(target: string): string {
  // [[target|display]] or [[target]]
  if (target.includes('|')) {
    return target
  }
  return target
}

export const WikiPageRenderer: React.FC<WikiPageProps> = ({ content, frontmatter, className }) => {
  const renderWikilink = (text: string) => {
    // Replace [[wikilink]] patterns with clickable spans
    return text.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (match, target, display) => {
      return `<a href="#" class="wikilink" data-target="${target}">${display || target}</a>`
    })
  }

  return (
    <div className={`wiki-page ${className || ''}`}>
      {frontmatter && (
        <div className="wiki-page-header mb-4">
          <h1 className="text-2xl font-bold">{frontmatter.title}</h1>
          {frontmatter.tags && frontmatter.tags.length > 0 && (
            <div className="flex gap-2 mt-2">
              {frontmatter.tags.map((tag: string, i: number) => (
                <span key={i} className="px-2 py-0.5 text-xs bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded">
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="wiki-page-content prose prose-sm dark:prose-invert max-w-none">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            p: ({ children, ...props }) => {
              const text = React.Children.toArray(children).join('')
              if (text.includes('[[')) {
                return <div dangerouslySetInnerHTML={{ __html: renderWikilink(text) }} {...props} />
              }
              return <p {...props}>{children}</p>
            },
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 修改WikiView组件**

修改 `frontend/src/components/pages/WikiView.tsx`，将原来的从JSON读取实体的方式改为：
1. 先尝试读取catalog和pages（新wiki系统）
2. 如果没有，降级到旧的JSON实体读取方式

关键修改点：
- 在组件挂载时，调用 `fetch(\`${API_BASE}/api/wiki/${kbId}/catalog\`)`
- 如果有catalog，显示目录树作为侧边栏
- 点击目录节点时，调用 `fetch(\`${API_BASE}/api/wiki/${kbId}/page?path=${path}\`)` 获取页面内容
- 使用 `WikiPageRenderer` 渲染页面内容
- 如果catalog不存在，保持现有JSON实体浏览方式作为降级方案

---

### Task 12: 单元测试

**Files:**
- Create: `backend/tests/test_wiki_pipeline.py`
- Create: `backend/tests/test_analysis_report.py`
- Create: `backend/tests/test_community.py`

- [ ] **Step 1: Analysis Report测试**

```python
# backend/tests/test_analysis_report.py
import json
import pytest
from pathlib import Path
from app.services.wiki.analysis.report import (
    AnalysisReport, Entity, Relation, Contradiction,
)


def test_report_serialization():
    report = AnalysisReport(kb_id="test_kb")
    report.entities.append(Entity(
        id="e1", name="张三", type="person",
        aliases=["小张"], attributes={"role": "嫌疑人"},
        importance=0.9, confidence=0.95,
    ))
    report.contradictions.append(Contradiction(
        id="c1", type="time_conflict", description="时间矛盾",
        involved_entities=["张三"], severity="high",
    ))

    data = report.to_dict()
    restored = AnalysisReport.from_dict(data)
    assert len(restored.entities) == 1
    assert restored.entities[0].name == "张三"
    assert len(restored.contradictions) == 1


def test_report_save_load(tmp_path):
    report = AnalysisReport(kb_id="test_kb")
    report.entities.append(Entity(id="e1", name="Test", type="person"))

    path = report.save_to(tmp_path)
    assert path.exists()

    loaded = AnalysisReport.load_from(tmp_path)
    assert len(loaded.entities) == 1
    assert loaded.entities[0].name == "Test"
```

- [ ] **Step 2: Community Detection测试**

```python
# backend/tests/test_community.py
from app.services.retrieval.community import assign_communities


def test_community_same_group():
    entities = [
        {"id": "e1", "relations": [{"target_id": "e2", "confidence": 0.9}]},
        {"id": "e2", "relations": [{"target_id": "e1", "confidence": 0.9}]},
    ]
    result = assign_communities(entities)
    assert result["e1"] == result["e2"]


def test_community_separate():
    entities = [
        {"id": "e1", "relations": []},
        {"id": "e2", "relations": []},
    ]
    result = assign_communities(entities)
    assert result["e1"] != result["e2"]


def test_empty_entities():
    result = assign_communities([])
    assert result == {}
```

- [ ] **Step 3: 运行测试**

```bash
cd D:\lbc\SuperDeepAnalyze\backend
pip install pytest
python -m pytest tests/test_analysis_report.py tests/test_community.py -v
```

---

## Verification

### 端到端测试流程

1. **启动后端**:
```bash
cd D:\lbc\SuperDeepAnalyze\backend
uvicorn app.main:app --reload --port 8000
```

2. **创建知识库并上传文档**:
```bash
# 通过前端或API上传测试文档
curl -X POST http://localhost:8000/api/knowledge-bases -H "Content-Type: application/json" -d '{"name": "测试KB"}'
```

3. **触发编译** (将自动触发Wiki生成):
```bash
curl -X POST http://localhost:8000/api/compile/{kb_id}
# 观察WebSocket进度，应该看到 "Wiki阶段1/4: 开始深度分析..." 等消息
```

4. **验证Wiki生成**:
```bash
# 检查catalog
curl http://localhost:8000/api/wiki/{kb_id}/catalog

# 检查页面列表
curl http://localhost:8000/api/wiki/{kb_id}/pages

# 检查分析报
curl http://localhost:8000/api/wiki/{kb_id}/analysis

# 检查具体页面
curl "http://localhost:8000/api/wiki/{kb_id}/page?path=overview"
```

5. **前端验证**: 打开前端应用，导航到知识库的Wiki标签，应看到目录树和页面内容而非原始JSON实体列表。
