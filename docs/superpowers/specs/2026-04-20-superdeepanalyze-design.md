# SuperDeepAnalyze - 卷宗深度分析系统设计文档

> **日期:** 2026-04-20
> **状态:** 设计讨论中
> **领域:** 公检法卷宗分析

## Context

公检法领域的卷宗通常超长（数十万到数百万字符），包含大量人物、时间、事件和复杂的关系。传统 RAG 方案（检索即答）无法有效处理这种复杂关联分析。本系统借鉴 LLM Wiki 的知识管理理念、graphify 的图谱构建模式和 Claude Code 的 Agent tool-use loop，构建一套面向超长上下文的预编译+深度分析系统。

---

## 1. 整体架构

```
前端 (React 18 + Vite + Tailwind CSS v4 + Zustand)
  ├── 知识库管理（暗色/明亮主题切换）
  ├── 卷宗上传与进度追踪
  ├── 知识图谱可视化（力导向图）
  ├── Agent 对话分析界面
  └── 系统设置（模型配置）
        │ HTTP + WebSocket (SSE 流式)
后端 (Python FastAPI)
  ├── 文档解析管线 (Docling + VLM OCR + python-docx + calamine)
  ├── 预编译引擎 (L0/L1/L2 三层编译)
  ├── Agent 引擎 (reAct tool-use loop)
  └── 存储管理 (SQLite + FAISS + 文件系统)
        │
LLM Provider (统一 OpenAI 兼容格式: base_url + model_name + api_key)
  ├── main: Agent 主模型 (图谱构建/问答推理)
  ├── embedding: 向量化模型 (FAISS 索引)
  └── vlm: 多模态模型 (PDF 扫描件 OCR)
```

**技术选型理由：**
- Python 后端：Docling、FAISS、NLP 生态成熟
- React 前端：组件生态丰富，Tailwind 快速迭代
- SQLite：轻量、内置 FTS5、better-sqlite3 成熟
- FAISS：向量检索性能好，Python 原生
- OpenAI 兼容格式：适配所有主流 MaaS 平台（通义、智谱、Moonshot 等）

---

## 2. 核心模块设计

### 2.1 文件解析管线

参考 Docling 的 pipeline 模式，根据文件类型自动选择解析器：

| 文件类型 | 检测方法 | 解析器 | 输出 |
|---------|---------|--------|------|
| PDF（文本） | Docling 格式检测 | Docling DocumentConverter | Structured Markdown + 表格 |
| PDF（扫描件） | Docling 返回空白/低文本密度 | VLM 多模态 OCR | Markdown + 图片描述 |
| DOCX | 文件扩展名/magic bytes | python-docx | Markdown（保留标题/列表/表格） |
| XLSX/XLS/CSV | 文件扩展名 | calamine | Markdown 表格 + 结构化数据 |
| 图片（JPG/PNG） | 文件扩展名 | VLM 多模态解析 | Markdown（图片内容描述+OCR文本） |

**PDF 类型自动检测：**
1. 先用 Docling 尝试解析
2. 如果解析后文本密度极低 → 判定为扫描件 → 走 VLM OCR 路径
3. 否则 → 直接使用 Docling 解析结果

**解析结果统一输出为 Structured Markdown，包含：**
- 文档标题层级（H1-H6）
- 正文段落
- 表格（Markdown 格式）
- 图片描述（来自 VLM）
- 元数据（页码、来源文件、格式类型）

### 2.2 预编译管线（纯函数 Pipeline）

```
文件解析 → 缓存检测 → L2 编译 → L1 编译 → L0 编译 → 完成
```

#### 2.2.1 缓存检测（跨知识库复用）

- 计算文件 SHA256 hash
- 检查全局预编译缓存表（SQLite）
- 如果命中 → 直接复用，无需重新编译
- 如果未命中 → 执行完整编译流程
- 支持强制重新编译

#### 2.2.2 智能 Chunking（L2 层）

**策略：优先自然段落，兼顾 token 范围**
1. 先按自然段落切分
2. 如果段落 token 数在 500-1000 之间 → 保持原样
3. 如果段落 token 数 > 1000 → 在句子边界拆分，每段不超过 1000 tokens
4. 如果段落 token 数 < 500 → 尝试合并相邻段落，直到 ≥ 500 tokens
5. 相邻 chunk 之间保留 100 tokens 的 overlap

**每个 chunk 的元数据：**
```json
{
  "chunk_id": "doc_001_chunk_003",
  "doc_id": "doc_001",
  "kb_id": "kb_001",
  "page_range": [3, 4],
  "paragraph_range": [12, 15],
  "token_count": 720,
  "content": "...原文...",
  "file_hash": "sha256...",
  "is_overlap": false
}
```

**Chunk overlap 处理：**
- 相邻 chunk 之间 100 tokens overlap 仅用于检索召回提升
- L0 实体抽取时按 `(name, type)` 去重，合并所有出现位置的引用
- Overlap 区域的内容不重复生成 embedding，标记 `is_overlap` 供去重时参考

#### 2.2.3 L2 层编译（原文索引）

- 保存所有 chunk 到文件系统（`data/kb_001/documents/doc_001/l2_chunks/`）
- 每个 chunk 为一个 Markdown 文件，包含原文和元数据
- 所有 chunk 的 embedding 存入 FAISS
- FTS5 全文索引存入 SQLite

#### 2.2.4 L1 层编译（段落摘要）

**批量调用轻量 LLM 生成：**
- 输入：一组 L2 chunks（如 10-20 个 chunk 为一批）
- 模型选择：优先使用配置的 `lightweight` 角色模型（如 qwen-turbo / gpt-4o-mini），未配置则 fallback 到主力模型
- 输出：
  - 段落摘要（每段 3-5 行）
  - 段落内人物关系标注（人物A ↔ 人物B：关系类型）
  - 矛盾点/疑点标记（时间冲突、陈述矛盾、证据不一致）
- 生成的 embedding 存入 FAISS

**L1 输出格式：**
```json
{
  "doc_id": "doc_001",
  "kb_id": "kb_001",
  "summaries": [
    {
      "chunk_ids": ["chunk_001", "chunk_002"],
      "summary": "张三于2024年3月15日在XX地点...",
      "entities_mentioned": ["张三", "李四", "王五"],
      "relations": [
        {"from": "张三", "to": "李四", "type": "同伙", "confidence": 0.85}
      ],
      "contradictions": [
        {"type": "time_conflict", "description": "张三称3月15日在家，但监控显示其在XX地点", "chunk_refs": ["chunk_001", "chunk_005"]}
      ]
    }
  ],
  "embedding": [...]
}
```

#### 2.2.5 L0 层编译（全局图谱）

**调用 Claude API 高质量推理：**
- 输入：所有 L1 摘要 + 已编译文档的元数据
- 输出：
  - **全局实体库**：人物、组织、地点、时间等
  - **时间线**：按时间排序的事件序列
  - **事件图谱**：事件之间的因果/时序关系 + 参与人物
  - **交叉引用**：文档之间的关联关系

**L0 输出格式：**
```json
{
  "kb_id": "kb_001",
  "entities": [
    {
      "id": "entity_001",
      "name": "张三",
      "type": "person",
      "aliases": ["张某", "张某某"],
      "attributes": {"role": "嫌疑人", "age": 35, "location": "XX市"},
      "mentions": [{"doc_id": "doc_001", "chunk_ids": ["chunk_001", "chunk_003"]}],
      "relations": ["entity_002", "entity_003"],
      "embedding": [...]
    }
  ],
  "timeline": [
    {
      "id": "event_001",
      "time": "2024-03-15T14:30:00",
      "description": "张三在XX地点与李四会面",
      "participants": ["entity_001", "entity_002"],
      "source_refs": [{"doc_id": "doc_001", "chunk_id": "chunk_001"}]
    }
  ],
  "event_graph": {
    "nodes": ["event_001", "event_002", ...],
    "edges": [
      {"from": "event_001", "to": "event_002", "relation": "causes", "confidence": 0.7}
    ]
  },
  "cross_refs": [
    {"doc_id": "doc_001", "ref_doc_id": "doc_003", "relation": "witness_corroboration", "detail": "李四的笔录与张三的陈述相互印证"}
  ]
}
```

### 2.3 存储结构

```
data/
├── sqlite.db                          # SQLite 数据库
│   ├── knowledge_bases                # 知识库元数据
│   ├── documents                      # 文档记录
│   ├── wiki_pages                     # Wiki 页面记录
│   ├── wiki_links                     # Wiki 链接（关系图谱）
│   ├── entities                       # 实体记录
│   ├── timeline_events                # 时间线事件
│   ├── sessions                       # 对话会话
│   ├── messages                       # 对话消息
│   ├── model_configs                  # 模型配置
│   ├── precompile_cache               # 预编译缓存（SHA256 → 结果）
│   └── fts_content                    # FTS5 全文索引
│
├── faiss/                             # FAISS 向量索引
│   ├── l0_entities.index
│   ├── l1_summaries.index
│   └── l2_chunks.index
│
└── knowledge_bases/
    └── kb_001/
        ├── meta.json                  # 知识库元数据
        ├── documents/
        │   └── doc_001/
        │       ├── original.pdf       # 原始文件
        │       ├── parsed.md          # 解析结果
        │       └── l2_chunks/         # L2 原文分段
        │           ├── chunk_001.md
        │           └── ...
        ├── l1_summaries.json          # L1 摘要
        └── l0/
            ├── entities.json          # 全局实体
            ├── timeline.json          # 时间线
            ├── event_graph.json       # 事件图谱
            └── cross_refs.json        # 交叉引用
```

### 2.4 Agent 问答引擎

**参考 Claude Code 的 tool-use loop 模式，自建 reAct 循环：**

```python
async def agent_loop(user_query: str, session_id: str, kb_id: str):
    messages = build_system_prompt(kb_id) + load_conversation_history(session_id)
    messages.append({"role": "user", "content": user_query})
    
    max_iterations = 20
    for _ in range(max_iterations):
        # Step 1: 调用主模型
        response = await call_model(messages, tools=get_tool_definitions())
        
        # Step 2: 解析输出
        if response.tool_calls:
            # Step 3: 执行工具
            for tool_call in response.tool_calls:
                result = await execute_tool(tool_call)
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
            
            # 流式推送工具调用状态到前端
            yield ToolCallEvent(tool_call.name, tool_call.input, result)
            
            # Step 4: 继续循环
            continue
        else:
            # 最终结论
            yield FinalAnswer(response.content)
            break
    
    save_conversation_history(session_id, messages)
```

**渐进式披露策略：**
1. Agent 首先调用 `read_l0` 获取全局摘要和实体列表
2. 根据用户问题，决定是否需要深入
3. 如果需要细节 → `read_l1` 读取相关段落摘要
4. 如果需要原文证据 → `read_l2` 读取具体 chunk
5. 每一层的信息都累积到对话上下文

**工具集（Tool Registry）：**

| 工具名 | 类型 | 功能 | 读取层级 | 输入 | 输出 |
|--------|------|------|----------|------|------|
| `search_vector` | 只读 | 向量语义检索 | L0/L1 | query, top_k, layer | 匹配结果列表 |
| `search_keyword` | 只读 | 关键词全文检索 | L1/L2 | query, top_k | 匹配结果列表 |
| `read_l0` | 只读 | 读取实体/时间线/事件图谱 | L0 | entity_id / event_id | 实体/事件详情 |
| `read_l1` | 只读 | 读取段落摘要和关系标注 | L1 | doc_id, chunk_range | 摘要+关系 |
| `read_l2` | 只读 | 读取原文指定chunk | L2 | doc_id, chunk_id | 原文内容 |
| `expand_entity` | 只读 | 展开某实体的完整关联 | L0→L1→L2 | entity_id | 完整关联链 |
| `get_timeline` | 只读 | 获取时间线片段 | L0 | start_time, end_time | 事件序列 |
| `ask_user` | 交互 | 请求用户补充信息 | - | question | 用户回答 |
| `report_findings` | 只写 | 输出分析结论 | - | findings, evidence_refs | - |

**混合检索实现：**
```python
async def hybrid_search(query: str, kb_id: str, top_k: int = 10):
    # 向量检索
    vec_results = await faiss_search(query, kb_id, top_k)
    
    # 关键词检索 (FTS5)
    kw_results = await sqlite_fts_search(query, kb_id, top_k)
    
    # RRF 融合排序
    merged = rrf_merge(vec_results, kw_results, k=60)
    
    return merged[:top_k]

def rrf_merge(results_a, results_b, k=60):
    scores = {}
    for rank, item in enumerate(results_a, 1):
        scores[item.id] = scores.get(item.id, 0) + 1 / (k + rank)
    for rank, item in enumerate(results_b, 1):
        scores[item.id] = scores.get(item.id, 0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

### 2.5 模型配置层

**统一 OpenAI 兼容格式：**
```json
{
  "models": {
    "main": {
      "base_url": "https://api.openai.com/v1",
      "model_name": "gpt-4o",
      "api_key": "sk-xxx",
      "max_tokens": 8192
    },
    "lightweight": {
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "model_name": "qwen-turbo",
      "api_key": "sk-xxx",
      "max_tokens": 8192
    },
    "embedding": {
      "base_url": "https://api.openai.com/v1",
      "model_name": "text-embedding-3-large",
      "api_key": "sk-xxx",
      "dimension": 3072
    },
    "vlm": {
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "model_name": "qwen2.5-vl-72b-instruct",
      "api_key": "sk-xxx"
    }
  },
  "rrf_k": 60,
  "agent_max_iterations": 15
}
```

**说明：**
- 所有 LLM 调用统一走 OpenAI 兼容格式（`base_url` + `model_name` + `api_key`）
- `lightweight` 为可选配置，未配置时 L1 编译 fallback 到 `main` 模型
- `vlm` 仅配置了 base_url/model_name/api_key 时启用，未配置时跳过 VLM OCR
- `rrf_k` RRF 融合参数，可调范围 10-100，默认 60
- `agent_max_iterations` Agent 最大迭代轮次，可调范围 5-50，默认 15

**系统设置页面：**
- 每个角色模型独立配置 base_url、model_name、api_key
- `lightweight` 和 `vlm` 为可选配置，有开关控制
- 支持测试连接（Test Connection）按钮
- 支持切换不同服务商（OpenAI、通义、智谱、Moonshot 等）
- `rrf_k` 和 `agent_max_iterations` 在高级设置中可配置
- 配置保存到 SQLite 的 `model_configs` 表，含 `config_version` 字段
- 配置变更时 bump version，前端提示"建议重新预编译知识库"

---

## 3. 前端 UI 设计

### 3.1 主题系统

- **暗色主题**（默认）：公检法卷宗档案风格，暖色调
  - 背景: `#1c1917` (stone-900)
  - 卡片: `#292524` (stone-800)
  - 边框: `#44403c` (stone-700)
  - 主文字: `#e7e5e4` (stone-200)
  - 强调色: `#d97706` (amber-600) — 档案/纸张质感
- **明亮主题**：
  - 背景: `#fafaf9` (stone-50)
  - 卡片: `#ffffff`
  - 边框: `#e7e5e4` (stone-200)
  - 主文字: `#1c1917` (stone-900)
  - 强调色: `#d97706` (amber-600)
- **主题切换**：右上角切换按钮，状态持久化到 localStorage

### 3.2 页面布局

```
┌──────────────────────────────────────────────────────────────┐
│ SuperDeepAnalyze  [主题切换]  [设置]                          │
├──────────┬───────────────────────────────────┬───────────────┤
│ 侧边导航  │           主内容区                 │   右侧面板    │
│          │                                   │               │
│ 📁 知识库│  (根据当前选中页面切换)            │ 对话历史      │
│ 📤 上传  │                                   │ 或            │
│ 🕸️ 图谱  │  · 图谱页: 全屏力导向图 + 过滤面板 │ 详情面板      │
│ 💬 对话  │  · 对话页: 对话区 + 工具调用面板   │ (实体/事件详情)│
│ ⚙️ 设置  │  · 设置页: 模型配置表单            │               │
│          │                                   │               │
├──────────┴───────────────────────────────────┴───────────────┤
│ 底部状态栏: 知识库 | 预编译状态 | LLM 状态                     │
└──────────────────────────────────────────────────────────────┘
```

### 3.3 关键页面

**知识库管理页：**
- 卡片网格布局
- 每个卡片显示：知识库名称、卷宗数量、预编译状态、创建时间
- 新建知识库按钮
- 点击卡片进入该知识库的分析页面

**卷宗上传页：**
- 拖拽上传区域
- 上传进度条（实时百分比）
- 解析状态指示器（等待解析 → 解析中 → 预编译中 → 完成）
- 批量上传支持

**知识图谱页：**
- 全屏力导向图（sigma.js / Recharts ForceGraph）
- 左侧过滤面板：按实体类型（人物/组织/地点/事件）筛选、按时间范围筛选
- 节点交互：拖拽、缩放、悬停显示详情、点击高亮关联
- 社区检测：Louvain 聚类，不同颜色区分
- 点击节点 → 右侧面板显示实体详情

**对话分析页：**
- 主区域：对话消息列表
  - 用户消息（右侧气泡）
  - Agent 回复（左侧卡片）
  - 工具调用过程（折叠/可展开）：显示每个工具的名称、输入、输出
  - Agent 思考过程（折叠/可展开）：显示推理链
- 右侧面板：对话历史（会话列表）+ 引用溯源（当前消息引用的卷宗片段）
- 底部输入框：自然语言提问

**系统设置页：**
- 模型配置区：main/embedding/vlm 三个角色的独立配置
- 每个角色：base_url、model_name、api_key、测试连接按钮
- 知识库管理：创建/删除知识库、预编译触发
- 通用设置：主题切换、语言偏好

---

## 4. 项目结构

```
SuperDeepAnalyze/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口
│   │   ├── api/
│   │   │   ├── knowledge_bases.py  # 知识库 CRUD
│   │   │   ├── documents.py        # 文档上传/管理
│   │   │   ├── chat.py             # 对话 API
│   │   │   ├── graph.py            # 图谱数据 API
│   │   │   ├── models.py           # 模型配置 API
│   │   │   └── websocket.py        # WebSocket 流式
│   │   ├── services/
│   │   │   ├── parsing/            # 文档解析
│   │   │   │   ├── docling_parser.py
│   │   │   │   ├── vlm_ocr.py
│   │   │   │   └── chunking.py     # 智能 chunking
│   │   │   ├── compilation/        # 预编译引擎
│   │   │   │   ├── l2_compiler.py
│   │   │   │   ├── l1_compiler.py
│   │   │   │   ├── l0_compiler.py
│   │   │   │   └── cache_manager.py
│   │   │   ├── agent/              # Agent 引擎
│   │   │   │   ├── loop.py         # reAct loop
│   │   │   │   ├── tools/          # 工具注册
│   │   │   │   │   ├── search_vector.py
│   │   │   │   │   ├── search_keyword.py
│   │   │   │   │   ├── read_l0.py
│   │   │   │   │   ├── read_l1.py
│   │   │   │   │   ├── read_l2.py
│   │   │   │   │   ├── expand_entity.py
│   │   │   │   │   ├── get_timeline.py
│   │   │   │   │   └── ask_user.py
│   │   │   │   └── prompt_builder.py
│   │   │   ├── retrieval/          # 检索引擎
│   │   │   │   ├── faiss_index.py
│   │   │   │   ├── fts_search.py
│   │   │   │   └── rrf_merge.py
│   │   │   └── llm/                # LLM 调用层
│   │   │       ├── provider.py     # OpenAI 兼容 provider
│   │   │       └── model_router.py
│   │   ├── models/                 # 数据模型 (SQLAlchemy)
│   │   │   ├── database.py
│   │   │   └── schema.py
│   │   └── config.py               # 配置管理
│   ├── requirements.txt
│   └── pyproject.toml
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── api/
│   │   │   ├── client.ts           # HTTP 客户端
│   │   │   └── websocket.ts        # WebSocket 客户端
│   │   ├── store/
│   │   │   ├── chat.ts             # 对话状态
│   │   │   ├── graph.ts            # 图谱状态
│   │   │   └── settings.ts         # 设置状态
│   │   ├── components/
│   │   │   ├── sidebar/            # 侧边导航
│   │   │   ├── knowledge-base/     # 知识库管理
│   │   │   ├── upload/             # 卷宗上传
│   │   │   ├── graph/              # 知识图谱
│   │   │   ├── chat/               # 对话界面
│   │   │   │   ├── MessageList.tsx
│   │   │   │   ├── ToolCallPanel.tsx
│   │   │   │   └── MessageInput.tsx
│   │   │   ├── settings/           # 系统设置
│   │   │   └── theme/              # 主题切换
│   │   └── index.css               # Tailwind + 主题变量
│   ├── index.html
│   ├── vite.config.ts
│   ├── package.json
│   └── tailwind.config.ts
│
├── data/                           # 运行时数据
│   ├── sqlite.db
│   ├── faiss/
│   └── knowledge_bases/
│
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-04-20-superdeepanalyze-design.md
```

---

## 5. 关键设计决策记录

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 后端语言 | Python | Docling/FAISS/NLP 生态成熟 |
| 前端框架 | React + Vite + Tailwind | 组件生态丰富，开发效率高 |
| 向量数据库 | FAISS (Python 库) | 轻量、性能好、与 Python 原生集成 |
| 全文检索 | SQLite FTS5 | 与 SQLite 统一存储层 |
| 知识图谱存储 | SQLite (关系表) | 力导向图渲染只需节点+边数据 |
| Agent 框架 | 自建 reAct loop | 参考 Claude Code tool-use 模式，轻量可控 |
| 模型调用格式 | OpenAI 兼容 | 适配所有主流 MaaS 平台 |
| Chunking 策略 | 自然段落优先 + token 范围约束 | 适合公检法卷宗的段落结构 |
| 预编译缓存 | SHA256 hash 跨知识库复用 | 同一卷宗不重复编译 |
| 主题系统 | 暗色/明亮双主题 | 用户需求 |
| 文件解析 | Docling + VLM OCR | 覆盖文本 PDF、扫描件、DOCX、Excel、图片 |

---

## 6. 设计审查决议（2026-04-21）

12 个设计审查问题已讨论并决议如下：

### P0 决议

| # | 问题 | 决议 |
|---|------|------|
| 1 | **L1 轻量 LLM 未定义** | 定义 `lightweight` = 成本 ≤ $0.10/M tokens、上下文 ≥ 8K。推荐：qwen-plus / gpt-4o-mini / glm-4-flash。未配置 fallback 到 main |
| 2 | **缺少异步任务队列** | 当前阶段用 `asyncio.create_task` + SQLite 状态追踪。文档 > 50 或并发 > 5 时引入 Celery/RQ |
| 3 | **SQLite 并发风险** | WAL + `busy_timeout=5000` + 批量事务 = 当前足够。编译阶段批量写入减少写次数 |
| 4 | **Claude API vs OpenAI 格式歧义** | 统一 OpenAI 兼容格式（base_url + model_name + api_key）。所有 LLM 调用走同一个 `LLMProvider` 类 |

### P1 决议

| # | 问题 | 决议 |
|---|------|------|
| 5 | **Chunk overlap 处理** | Overlap 区域不重复生成 embedding，标记 `is_overlap`。检索时 overlap chunk 权重降低 50% |
| 6 | **VLM OCR 成本** | VLM 仅在 Docling 文本密度 < 50 字符/页时触发。上传 > 50MB 扫描件需用户确认。设置页显示成本估算 |
| 7 | **max_iterations 可配置** | 设置页"高级设置"区域暴露 `agent_max_iterations`（默认 15，范围 5-50） |
| 8 | **数据库 schema 版本管理** | `schema_version` 表 + 迁移脚本目录 `migrations/`。幂等 SQL（`IF NOT EXISTS`） |

### P2/P3 决议

| # | 问题 | 决议 |
|---|------|------|
| 9 | **FAISS 横向扩展** | 当前单进程足够。KB > 10 万 chunk 时考虑 `IndexIVFFlat` 或分片索引 |
| 10 | **RRF k=60 参数** | 默认 60（经验值），配置层可调（范围 10-100） |
| 11 | **主题风格矛盾** | 采用暖色调琥珀色 `#d97706`（amber-600），已在前端实现。更新设计文档 |
| 12 | **skill workspace 路径** | 后端 `backend/app/services/agent/tools/`。前端无需独立 workspace 概念 |

---

## 7. 验证计划

### 6.1 预编译验证
1. 上传 5 份测试卷宗（2 份文本 PDF、1 份扫描件 PDF、1 份 DOCX、1 份 Excel）
2. 验证 Docling 正确解析文本 PDF，VLM 正确 OCR 扫描件
3. 验证 L2 chunking 符合自然段落优先策略
4. 验证 L1 摘要生成质量
5. 验证 L0 实体/时间线/事件图谱抽取
6. 验证预编译缓存复用（同一文件上传两次）

### 6.2 Agent 问答验证
1. 创建测试会话，提问简单问题（验证基础检索）
2. 提问复杂关联问题（验证多轮 tool-use）
3. 验证渐进式披露（L0→L1→L2 的逐层深入）
4. 验证 ask_user 工具（Agent 主动询问用户）
5. 验证混合检索效果（向量 + 关键词融合）

### 6.3 前端验证
1. 验证暗色/明亮主题切换
2. 验证知识库卡片布局
3. 验证卷宗上传进度条
4. 验证力导向图交互（拖拽/缩放/悬停/点击）
5. 验证对话界面工具调用可视化
6. 验证模型配置表单
