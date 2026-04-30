# SuperDeepAnalyze 系统全面优化设计

**日期:** 2026-04-29
**状态:** Draft
**策略:** Agent 中心突破 — 以 Agent 推理质量为核心，同步改善检索和编译，辐射到 Wiki 和前端

---

## Context

SuperDeepAnalyze 经过前期开发，核心管线已跑通（上传→编译→Wiki→图谱→聊天），多跳推理测试 7/7 通过。但实际使用中存在以下痛点：

1. **Agent 推理质量不稳定** — 检索命中率低、过早停止搜索、分析深度不足
2. **编译性能差** — 20MB 文档需要 ~60 分钟，无增量编译
3. **Wiki 结构扁平** — 缺少结构化导航和交叉引用
4. **前端交互粗糙** — 无 Markdown 渲染、图谱交互弱、Agent 过程不可视

本设计参考 8 个优秀项目的架构模式，采用 **Agent 中心突破** 策略，分 5 个 Phase 依次实施。

---

## Phase 1: Agent Loop 框架重构

**目标:** 提升 Agent 推理质量和稳定性
**参考项目:** Claude Code (QueryEngine 状态机)、OpenViking (IntentAnalyzer)、Lossless-Claw (DAG 上下文管理)
**预计工期:** 3-4 天

### 1.1 意图分析层 (新建)

**文件:** `backend/app/services/agent/intent_analyzer.py` (新建)

参考 OpenViking 的 `intent_analyzer.py`，在 reAct 循环开始前分析用户问题：

```python
@dataclass
class QueryPlan:
    question_type: str         # factual / relational / temporal / analytical / comparative
    complexity: str            # simple / medium / complex
    target_entities: list[str] # 从问题中识别的实体名
    time_range: tuple[str, str] | None
    search_mode: str           # THINKING (thorough) / QUICK (fast)
    suggested_start_level: str # L0 / L1 / L2
    sub_queries: list[str]     # 拆解后的子查询
```

实现方式：使用轻量级模型（如 qwen-turbo）快速分析，不消耗主模型额度。

### 1.2 中文系统提示词重写

**文件:** `backend/app/services/agent/prompt_builder.py` (重写)

当前问题：全英文提示词，国产模型处理中文卷宗时理解偏差大。

改为中文提示词，并增强以下内容：
- 法律卷宗分析的专业术语和推理框架
- 渐进式披露的中文示例（而非裴谦拳击的英文例子）
- 工具使用优先级明确排序
- 每个工具的中文参数说明

### 1.3 DAG 上下文管理重构

**文件:** `backend/app/services/agent/context_manager.py` (重构)

当前问题：
- `auto_compact` 截断到 5000 字符，丢失大量信息
- 压缩后信息无法找回
- 微压缩只按新旧分，不按重要性

参考 Lossless-Claw 的 `compaction.ts`，改进为：
- **DAG 结构:** 每次压缩生成摘要节点，保留指向原始消息的引用
- **多级压缩:** leaf summaries (depth 0) + condensed summaries (depth 1+)
- **动态阈值:** 根据实际模型上下文窗口调整（国产模型通常 4K-128K）
- **升级策略:** normal → aggressive → fallback 三级
- **CJK 感知:** 压缩时考虑中文 token 特性（1.5 token/char vs 0.25/char ASCII）

### 1.4 召回工具 (新建)

**文件:** `backend/app/services/agent/recall_tools.py` (新建)

参考 Lossless-Claw 的 `retrieval.ts`，添加 3 个新工具：

| 工具 | 功能 | 用途 |
|------|------|------|
| `recall_grep` | 正则/关键词搜索已压缩的上下文 | 在被压缩的消息中找回关键信息 |
| `recall_expand` | 展开某个摘要节点的子消息 | 恢复压缩前的详细内容 |
| `recall_describe` | 查看某个摘要节点的内容 | 快速浏览压缩内容 |

这 3 个工具注册为 READ_ONLY，可并行执行。

### 1.5 图谱搜索工具重构

**文件:** `backend/app/services/agent/tools.py` 中 `ProgressiveSearchTool` (重构)

当前问题：L0 搜索只是 `if any(kw in str(e) for kw in query.split())`，对中文完全无效。

改进：
- 使用 NetworkX 图遍历替代字符串匹配
- 基于实体 ID 的邻接查询
- 支持 BFS/DFS 关系路径查找

### 1.6 状态机增强

**文件:** `backend/app/services/agent/loop.py` (修改)

参考 Claude Code 的 `QueryEngine`，增强状态机：

```
INTERPRETING → PLANNING → SEARCHING → DRILL_DOWN
→ EVALUATING → CONSOLIDATING → REPORTING → (终态)
                              ↗ WAITING_USER
                              ↘ COMPACTING
```

新增状态：
- `PLANNING`: 基于意图分析生成搜索计划
- `DRILL_DOWN`: 明确在 L0→L1→L2 之间下钻
- `CONSOLIDATING`: 收集证据准备报告

### 1.7 动态压缩阈值

**文件:** `backend/app/services/agent/context_manager.py` (修改)

适配国产模型上下文窗口：
- 查询模型配置获取实际 `max_tokens`
- 微压缩阈值: 50% → 动态计算
- 自动压缩阈值: 85% → 动态计算
- 添加模型上下文窗口的自动检测

### 测试要求

**Skills:** `verification-before-completion`, `systematic-debugging`
**测试方法:**
1. 单元测试: 每个 Agent 工具的输入/输出
2. 集成测试: 意图分析 → 搜索 → 评估 → 报告完整流程
3. 回归测试: 之前通过的 7/7 多跳推理用例仍必须通过
4. 前后端联调: WebSocket 事件流正常传递，AgentLoopDisplay 正确展示

---

## Phase 2: 检索引擎升级

**目标:** 提升检索命中率和相关性
**参考项目:** LLM Wiki (4信号评分)、OpenViking (分层检索)
**预计工期:** 2-3 天

### 2.1 实体识别查询改写

**文件:** `backend/app/services/retrieval/query_rewriter.py` (新建)

```
用户查询 "张三为什么要杀害李四？"
    → 实体识别: [张三, 李四, 杀害]
    → 子查询生成:
      • "张三 杀人动机"
      • "张三 李四 关系"
      • "李四 死亡 原因"
    → 搜索策略: THINKING 模式, 起始层级 L1
```

使用轻量级模型做实体识别和查询改写，不消耗主模型额度。

### 2.2 图谱关系搜索

**文件:** `backend/app/services/retrieval/graph_search.py` (新建)

基于 NetworkX 构建实体关系图（已有 `community.py` 的基础）：
- 实体邻接查询: 给定实体，返回所有关联实体和关系
- 路径查询: 给定两个实体，查找关系路径
- 子图查询: 给定实体集合，提取相关子图

### 2.3 多信号 RRF 融合

**文件:** `backend/app/services/retrieval/hybrid_search.py` (重构)

从 2 信号扩展到 4 信号：

| 信号 | 来源 | 权重 | 说明 |
|------|------|------|------|
| Signal 1 | 向量搜索 (FAISS) | 3.0 | 语义相似度 |
| Signal 2 | 关键词搜索 (FTS5) | 2.0 | 精确匹配 |
| Signal 3 | 图谱关系 (NetworkX) | 4.0 | 实体关系路径 |
| Signal 4 | 实体亲和度 (Adamic-Adar) | 1.5 | 共现频率 |

RRF 融合使用加权版本，`score = Σ(weight_i / (k + rank_i))`。

### 2.4 实体亲和度评分

**文件:** `backend/app/services/retrieval/entity_affinity.py` (新建)

参考 LLM Wiki 的 Adamic-Adar 评分：
- 构建实体共现矩阵（同一文档/段落中出现的实体对）
- 计算实体间亲和度
- 用于检索结果的相关性增强

### 2.5 结果增强器

**文件:** `backend/app/services/retrieval/result_enricher.py` (新建)

对搜索结果进行增强：
- 添加上下文窗口（前后各 100 字）
- 添加相关实体链接
- 添加置信度标签（EXTRACTED/INFERRED/AMBIGUOUS）
- 添加来源层级标注

### 测试要求

**Skills:** `verification-before-completion`
**测试方法:**
1. 单元测试: 每个信号源的搜索准确性
2. 融合测试: 多信号 RRF 合并结果的相关性
3. 端到端测试: Agent 调用检索引擎的完整路径
4. **前后端联调:** 搜索结果在前端正确渲染，相关性分数正确展示
5. **MCP:** 使用截图分析工具 (`mcp__zai-mcp-server__analyze_image`) 验证前端搜索结果展示

---

## Phase 3: 编译引擎优化

**目标:** 编译速度提升 50%+，支持增量编译和断点续编
**参考项目:** LLM Wiki (SHA256 增量缓存)、OpenDeepWiki (并行超时保护)
**预计工期:** 2-3 天

### 3.1 增量检测接入

**文件:** `backend/app/services/compilation/cache_manager.py` (已存在，需接入)

CacheManager 类已存在但未接入上传端点：
- 在 `documents.py` 的上传流程中检查 SHA256 哈希
- 跨 KB 共享已编译文档的 L1/L2/FAISS 数据
- 复制而非重新编译

### 3.2 L1 动态批处理

**文件:** `backend/app/services/compilation/l1_compiler.py` (优化)

- 动态批量大小: 根据模型响应时间调整（50→100 或 50→20）
- 并行池优化: 动态工作线程数，基于可用模型配置
- 超时保护: 每批设置超时（参考 OpenDeepWiki 的 `DocumentGenerationTimeoutMinutes`）
- 增量保存粒度: 每 10 批 → 每批

### 3.3 精细进度报告

**文件:** `backend/app/api/compile.py` (修改)

WebSocket 进度事件增强：
```json
{
  "type": "compile_progress",
  "phase": "l1",
  "current_batch": 45,
  "total_batches": 1140,
  "percentage": 3.9,
  "eta_seconds": 3120,
  "elapsed_seconds": 180,
  "current_doc": "doc_003.md",
  "docs_completed": 2,
  "docs_total": 5
}
```

### 3.4 编译取消与断点续编

**文件:** `backend/app/api/compile.py` + `backend/app/services/compilation/l1_compiler.py` (修改)

- 取消: 通过 WebSocket 发送取消指令，编译器检查取消标志
- 断点续编: 已有 `compile_queue` 表，完善恢复逻辑
- 部分结果检测: 检测已完成的批次，跳过重新编译

### 3.5 L0 质量门控

**文件:** `backend/app/services/compilation/l0_compiler.py` (增强)

编译完成后检查：
- 实体数量是否合理（不应为 0 或异常多）
- 关系数量是否合理
- 时间线是否非空
- 不通过则标记为 "needs_review" 而非直接使用

### 测试要求

**Skills:** `verification-before-completion`, `webapp-testing`
**测试方法:**
1. 编译性能测试: 对比优化前后的编译时间
2. 增量编译测试: 重复上传同一文件，验证跳过
3. 断点续编测试: 中断编译后恢复
4. 取消测试: 编译中途取消
5. **前后端联调:** WebSocket 进度事件在前端正确展示（使用 `webapp-testing` skill 的 Playwright）
6. **MCP:** 截图分析编译进度 UI (`mcp__zai-mcp-server__analyze_image`)

---

## Phase 4: Wiki 质量提升

**目标:** 从扁平列表升级为结构化导航 Wiki
**参考项目:** OpenDeepWiki (三阶段生成)、Graphify (社区检测 + 置信度审计)、LLM Wiki (安全链接)
**预计工期:** 2-3 天

### 4.1 社区检测驱动目录生成

**文件:** `backend/app/services/wiki/catalog/` (增强)

基于 Louvain 社区检测结果（已有 `community.py`）：
- 每个社区 → 一个主题分类
- 社区内的核心实体 → 页面
- 跨社区关系 → 分类间的导航链接

目录结构模板（法律卷宗专用）：
```
📁 案件概览
├── 📄 案件摘要
└── 📄 当事人一览
📁 人物关系
├── 📄 [按社区聚类的人物页]
📁 关键事件
├── 📄 [按时间线的事件页]
📁 证据分析
├── 📄 [按类型的证据页]
📁 矛盾点
├── 📄 [各文档间的矛盾]
```

### 4.2 专用页面模板

**文件:** `backend/app/services/wiki/pages/templates.py` (增强)

| 模板类型 | 结构 |
|----------|------|
| 人物页 | 基本信息 → 关系网 → 涉及事件 → 证词/陈述 → 可信度评估 |
| 事件页 | 事件经过 → 涉及人物 → 相关证据 → 各方描述对比 → 矛盾标注 |
| 证据页 | 证据内容 → 来源文档 → 争议点 → 关联事件 → 可信度等级 |

### 4.3 安全链接插入

**文件:** `backend/app/services/wiki/enrichment/` (优化)

参考 LLM Wiki 的 `enrich-wikilinks.ts`：
- LLM 只返回 `{links: [{term, target}]}` 映射关系
- **代码执行实际字符串替换** — 防止 LLM 篡改内容
- 双向链接追踪（A 引用 B 时，B 的页面也标注被 A 引用）

### 4.4 思维导图生成

**文件:** `backend/app/services/wiki/mindmap.py` (新建)

参考 OpenDeepWiki 的 `GenerateMindMapAsync`：
- 基于 Wiki 目录结构生成树状 JSON
- 前端用 React Flow 或 D3.js 渲染
- 支持点击节点跳转到对应 Wiki 页面

### 测试要求

**Skills:** `verification-before-completion`, `webapp-testing`
**测试方法:**
1. Wiki 生成质量测试: 检查目录结构、页面内容、链接完整性
2. 健康检查测试: 孤立页面、断链检测
3. **前后端联调:** Wiki 页面导航、`[[wikilink]]` 点击跳转、目录树展开/折叠
4. **MCP:** 截图分析 Wiki 页面展示效果 (`mcp__zai-mcp-server__analyze_image`)
5. **Playwright:** E2E 测试 Wiki 浏览流程（使用 `webapp-testing` skill）

---

## Phase 5: 前端交互体验

**目标:** 提升用户交互质量
**预计工期:** 3-4 天

### 5.1 Agent 循环可视化增强

**文件:** `frontend/src/components/AgentLoopDisplay/` (增强)

参考 Claude Code 的 Agent 循环展示：
- 意图分析结果展示（问题类型、复杂度、搜索策略）
- 检索路径可视化（L0→L1→L2 钻取路线图）
- 实时 token 使用量仪表盘
- 证据收集面板（可展开查看来源原文）
- 推理步骤可折叠/展开

### 5.2 Markdown 渲染

**文件:** `frontend/src/components/` (修改)

新增依赖: `react-markdown` + `remark-gfm` + `react-syntax-highlighter`

- 聊天消息 Markdown 渲染
- 代码块语法高亮
- 表格/列表/加粗/链接
- `[[wikilink]]` 解析为可点击组件
- 证据引用高亮 + 悬浮提示

### 5.3 图谱交互增强

**文件:** `frontend/src/components/pages/GraphView.tsx` (重写)

- 节点拖拽/缩放/平移
- 点击节点 → 侧边栏详情面板
- 关系类型颜色编码
- 社区高亮（来自 Louvain 检测）
- 移除 12 字符中文标签截断

### 5.4 编译进度增强

**文件:** `frontend/src/components/pages/tabs/CompileTab.tsx` (增强)

- 分阶段进度条（L2→L1→L0→Wiki）
- 每阶段 ETA + 已用时间
- 当前处理的批次/文档名称
- 取消按钮

### 5.5 Wiki 导航增强

**文件:** `frontend/src/components/pages/WikiView.tsx` (增强)

- 左侧目录树导航
- `[[wikilink]]` 点击跳转
- 面包屑导航
- 全文搜索

### 测试要求

**Skills:** `webapp-testing`, `frontend-testing-best-practices`, `verification-before-completion`
**测试方法:**
1. **Playwright E2E 测试 (webapp-testing skill):** 每个前端改动的完整用户流程测试
2. **截图对比 (mcp__zai-mcp-server__ui_diff_check):** 改动前后的 UI 对比
3. **截图分析 (mcp__zai-mcp-server__analyze_image):** 验证 UI 渲染正确性
4. **前后端联调:** WebSocket 事件 → 前端展示的完整链路
5. **回归测试:** 确保之前的 7/7 多跳推理在前端仍然正常

---

## 实施顺序和依赖关系

```
Phase 1: Agent Loop (3-4天)
    ↓ (Agent 质量改善立竿见影)
Phase 2: 检索引擎 (2-3天)
    ↓ (检索改善进一步提升 Agent 质量)
Phase 3: 编译引擎 (2-3天)
    ↓ (编译改善提供更好的数据基础)
Phase 4: Wiki (2-3天)
    ↓ (Wiki 改善基于更好的编译数据)
Phase 5: 前端 (3-4天)
    (最终用户感受到所有改进)
```

总工期: 约 12-17 天

每个 Phase 完成后必须:
1. 后端单元测试通过
2. 前端组件测试通过
3. **前后端联调 E2E 测试通过**（使用 `webapp-testing` skill）
4. 使用 `verification-before-completion` skill 确认

---

## 关键参考文件

| 文件 | 用途 |
|------|------|
| `backend/app/services/agent/loop.py` | Agent 循环核心 (Phase 1) |
| `backend/app/services/agent/context_manager.py` | 上下文管理 (Phase 1) |
| `backend/app/services/agent/prompt_builder.py` | 系统提示词 (Phase 1) |
| `backend/app/services/agent/tools.py` | Agent 工具定义 (Phase 1+2) |
| `backend/app/services/retrieval/hybrid_search.py` | 混合搜索 (Phase 2) |
| `backend/app/services/retrieval/faiss_index.py` | FAISS 索引 (Phase 2) |
| `backend/app/services/retrieval/community.py` | 社区检测 (Phase 2+4) |
| `backend/app/services/compilation/l1_compiler.py` | L1 编译 (Phase 3) |
| `backend/app/services/compilation/l0_compiler.py` | L0 编译 (Phase 3) |
| `backend/app/services/wiki/pipeline.py` | Wiki 管线 (Phase 4) |
| `frontend/src/components/AgentLoopDisplay/` | Agent 可视化 (Phase 5) |
| `frontend/src/components/pages/GraphView.tsx` | 图谱视图 (Phase 5) |
| `frontend/src/components/pages/WikiView.tsx` | Wiki 视图 (Phase 5) |

---

## Skills 和 MCP 工具使用计划

### 开发阶段 Skills
| Skill | 使用场景 |
|-------|---------|
| `systematic-debugging` | 遇到 bug 时使用 |
| `verification-before-completion` | 每个 Phase 完成前使用 |
| `writing-plans` | 每个 Phase 开始前制定详细实施计划 |
| `frontend-testing-best-practices` | Phase 5 前端开发时使用 |

### 测试阶段 Skills 和 MCP
| 工具 | 使用场景 |
|------|---------|
| `webapp-testing` (Playwright) | 每个 Phase 的前后端联调 E2E 测试 |
| `mcp__zai-mcp-server__analyze_image` | 截图分析前端 UI 是否正确渲染 |
| `mcp__zai-mcp-server__ui_diff_check` | 改动前后 UI 对比 |
| `mcp__zai-mcp-server__extract_text_from_screenshot` | 提取错误截图中的文字 |
