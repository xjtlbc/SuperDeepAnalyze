# 两阶段Ingest + 结构化Wiki生成设计

> **Created:** 2026-04-25
> **Status:** Draft — Awaiting user review

## Context

SuperDeepAnalyze当前通过L0编译生成实体库、时间线、事件图，但这些数据直接渲染为前端wiki页面，缺乏结构化组织。具体问题是：
- L0 prompt未定义entity relations、mentions、attributes字段，导致数据缺失
- 没有wiki目录/页面概念，wiki就是实体列表的UI渲染
- 事件图边定义模糊，图谱连接断裂
- 缺少矛盾分析、知识缺口、社区分组等高级特性

参考OpenDeepWiki的catalog-first架构和llm_wiki的两阶段ingest + wikilink enrichment模式，设计一个高质量的wiki生成pipeline。

---

## Architecture

### 4阶段Pipeline

```
L0/L1/L2编译完成（现有）
    ▼
Phase 1: ANALYSIS — 从L1/L2/L0数据中提取增强版实体、关系、矛盾、概念、知识缺口、叙事线索
    ▼
Phase 2: CATALOG — 基于Analysis Report生成wiki目录树（分类→子分类→叶子页面）
    ▼
Phase 3: PAGES — 并行生成每个叶子节点的wiki页面（Markdown + frontmatter）
    ▼
Phase 4: ENRICHMENT — 安全替换方式插入[[wikilink]]交叉链接
```

### 触发方式

L0编译完成后**自动同步触发**。Wiki生成作为编译流程的一部分，完成后才返回"编译完成"状态。

---

## Data Structures

### Analysis Report

```python
@dataclass
class AnalysisReport:
    kb_id: str
    generated_at: str
    entities: list[Entity]
    concepts: list[Concept]
    contradictions: list[Contradiction]
    knowledge_gaps: list[Gap]
    narrative_threads: list[Thread]
```

### Entity（增强版）

```python
@dataclass
class Entity:
    id: str
    name: str
    type: Literal["person", "organization", "location", "event", "evidence", "document"]
    aliases: list[str]
    attributes: dict[str, str]
    relations: list[Relation]
    mentions: list[Mention]
    importance: float        # 0-1，基于mention频次+关系数量计算
    confidence: float        # 提取置信度
    community_id: int        # Louvain社区检测自动分配
```

### Relation

```python
@dataclass
class Relation:
    source_id: str
    target_id: str
    relation_type: str       # "同伙"、"上下级"、"亲属"、"对立"
    evidence: str            # 原文引用作为证据
    confidence: float        # 0-1
    sources: list[str]       # 来源chunk_ids
```

### Contradiction

```python
@dataclass
class Contradiction:
    id: str
    type: Literal["time_conflict", "statement_conflict", "evidence_conflict", "logical_gap"]
    description: str
    involved_entities: list[str]
    sources: list[str]
    severity: Literal["high", "medium", "low"]
```

### Catalog Tree

```python
@dataclass
class CatalogNode:
    title: str
    path: str                # URL-friendly slug
    order: int
    node_type: Literal["category", "page"]
    children: list[CatalogNode]
    description: str         # 生成页面时的上下文提示
```

### Wiki Page Format

```markdown
---
title: 张三
type: person
created: 2026-04-25T10:30:00Z
tags: ["嫌疑人", "主犯"]
sources:
  - doc_id: doc_001
    chunks: [chunk_005, chunk_012]
community: 0
importance: 0.95
---

# 张三

## 基本信息
## 关系网
## 涉案时间线
## 关键证据
## 矛盾点
```

---

## Tool System

### Analysis Agent Tools

复用现有工具：`read_l0`, `read_l1`, `read_l2`, `search_vector`, `search_keyword`, `expand_entity`, `get_timeline`

新增工具：`record_entity`, `record_relation`, `record_contradiction`, `record_gap`, `record_thread`

Analysis Agent是reAct循环：逐个实体深度探索 → 读L1摘要 → 必要时读L2原文 → 记录发现 → 信息饱和后停止。

### Catalog Agent Tools

`ReadAnalysis` — 读取完整Analysis Report
`WriteCatalog` — 输出目录树JSON

### Page Generation Tools

`ReadAnalysis`, `ReadL1`, `ReadL2`, `WritePage`

每页强制三阶段：GATHER → THINK → WRITE

### Wikilink Enrichment

LLM输出`{term, target}` JSON列表，代码执行安全字符串替换，不碰页面其他内容。

---

## Code Structure

```
backend/app/
├── services/
│   └── wiki/                          # 新增wiki生成模块
│       ├── pipeline.py                # 4阶段orchestrator
│       ├── analysis/
│       │   ├── agent.py               # Analysis Agent reAct loop
│       │   ├── report.py              # AnalysisReport model
│       │   └── tools.py               # record_* tools
│       ├── catalog/
│       │   ├── generator.py           # Catalog generation agent
│       │   └── storage.py             # Catalog JSON持久化
│       ├── pages/
│       │   ├── generator.py           # Page generation orchestrator
│       │   ├── templates.py           # Page template + frontmatter
│       │   └── storage.py             # Page文件持久化
│       └── enrichment/
│           ├── linker.py              # Wikilink enrichment engine
│           └── parser.py              # Wikilink解析器
│   └── retrieval/
│       └── community.py               # Louvain社区检测
├── api/wiki.py                        # 新增: wiki生成触发 + 页面读取API
├── models/database.py                 # 新增: wiki_pages, wiki_catalog表
```

---

## Error Handling

| 阶段 | 失败场景 | 策略 |
|------|----------|------|
| Analysis | LLM API错误 | 3次重试，指数退避；降级为旧版wiki |
| Catalog | JSON格式错误 | Schema验证，max 3次修正 |
| Pages | 单页面超时 | 独立超时(60min)，失败不影响其他页面 |
| Enrichment | 替换冲突 | 只替换确定匹配，歧义跳过 |

---

## Frontend Changes

- `WikiView.tsx`: 从读JSON改为读wiki页面Markdown并渲染
- 新增 `WikiPageRenderer.tsx`: Markdown + frontmatter渲染
- `wiki.py` API: 新增 `GET /api/wiki/{kb_id}/catalog` 和 `GET /api/wiki/{kb_id}/page/{path}`

---

## Implementation Phases

### Phase 1: Analysis Pipeline
- AnalysisReport数据模型
- Analysis Agent loop
- 5个record工具
- 单元测试

### Phase 2: Catalog Generation
- Catalog Agent
- WriteCatalog tool
- 目录树JSON存储
- 前端catalog浏览

### Phase 3: Page Generation
- Page generator
- 并行处理
- frontmatter模板
- 前端页面渲染

### Phase 4: Enhancement
- Wikilink安全替换引擎
- Louvain社区检测
- 知识缺口可视化
