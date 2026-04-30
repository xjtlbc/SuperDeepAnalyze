# Agent Loop Claude Code 风格上下文管理设计

**日期**: 2026-04-21
**状态**: 待审批
**作者**: Claude Code (brainstorming session)

---

## 1. 问题陈述

当前 Agent Loop 存在以下核心问题：

1. **硬编码迭代限制**：`_FORCE_ANSWER_THRESHOLD = 10` 在第 10 轮就强制终止，对于需要 20+ 轮的多跳推理（如 "A 是 B 的师父，B 的拳法是跟谁学的"）完全不够
2. **过于激进的饱和度检测**：`_is_information_saturated` 只看结果长度（< 200 chars），多跳推理中间步骤经常只得到少量信息，被误杀
3. **无上下文管理**：每轮都把完整 tool result 追加到 messages，30+ 轮后必然超出模型上下文窗口
4. **工具串行执行**：所有工具串行调用，每轮耗时长

**目标**：让 Agent 能跑 30-50 轮处理多跳深度推理和复杂案件多文档交叉验证，同时通过上下文管理防止消息列表无限增长。

---

## 2. 整体架构

核心思想来自 Claude Code：**管理上下文，而不是限制迭代次数**。

```
┌─────────────────────────────────────────────────────────┐
│                    AgentLoop.run()                       │
│                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────┐ │
│  │ LLM Chat │→│ 工具并行执行  │→│ ContextManager     │ │
│  │          │  │ (读工具并发)  │  │                   │ │
│  │ 产出     │  │ 产出结果     │  │ ① classify_result  │ │
│  │ 工具调用 │  │              │  │ ② microcompact     │ │
│  │ 或答案   │  │              │  │ ③ auto_compact_if  │ │
│  └──────────┘  └──────────────┘  │ ④ check_saturation│ │
│                                  └───────────────────┘ │
│                                                         │
│  循环条件：                                             │
│  - LLM 产出了 tool_use → 继续                            │
│  - LLM 产出纯文本 → 停止（final_answer）                 │
│  - max_iterations 50（安全上限，非主动触发）             │
│  - InformationTracker 判断饱和 → 停止                   │
│  - Context too full → auto_compact → 继续               │
└─────────────────────────────────────────────────────────┘
```

### 关键决策
- 去掉 `_FORCE_ANSWER_THRESHOLD = 10` 硬限制
- `max_iterations = 50` 作为安全兜底（不会主动触发，只在失控时兜底）
- 新增 `ContextManager` 类，负责上下文生命周期管理
- 新增 `InformationTracker` 类，负责信息增益跟踪
- 读工具并行执行（最多 5 个并发）

---

## 3. ContextManager 三层上下文管理

### 3.1 层 1：工具结果分类与存储

每次工具执行后，ContextManager 对结果进行分类：

```python
class ToolResultEntry:
    tool_name: str          # "search_vector", "read_l1" 等
    query: str             # 原始查询
    result_text: str       # 完整结果（可能很大）
    summary: str           # 压缩后的摘要
    importance: str        # "critical" | "normal" | "transient"
    consumed: bool         # 是否已被 LLM "消费"
    entities_found: set    # 新发现的实体
    relations_found: set   # 新发现的关系
    docs_referenced: set   # 涉及的文档
```

**分类规则：**

| 重要性 | 何时标记 | 保留策略 |
|--------|---------|---------|
| `critical` | 发现了关键实体、关系、时间线索 | **始终保留原文**，不压缩 |
| `normal` | 常规搜索，有结果但非关键 | microcompact 时可压缩为摘要 |
| `transient` | 空结果、重复查询 | 立即丢弃，不入 messages |

### 3.2 层 2：Microcompact（工具结果压缩）

**触发条件**：工具结果总 token 数 > 30K

**行为**：
- 保留最近 3 轮的工具结果原文
- 将更早的、且已被 LLM 用于下一步推理的结果替换为摘要
- 摘要格式：`"[已压缩] {tool_name} 查询了 '{query}'，返回 {n} 条结果，关键发现：{summary}"`

**实现**：遍历 messages 列表，找到已消费的 tool result message，替换其 content 为摘要。

### 3.3 层 3：Auto-Compact（对话摘要）

**触发条件**：messages 总 token 数 > 模型上下文窗口 - 15K buffer

**行为**：
- 调用 LLM 对整个对话进行摘要
- System prompt: "你是一个卷宗分析助手。请将以下对话摘要化，保留所有关键实体、关系和发现。"
- 保留：原始用户问题、所有 critical 结果、最近 2 轮的正常结果
- 将早期对话替换为：`"[上下文已压缩] 在搜索过程中发现：{llm_generated_summary}"`

**回退机制**：
1. 尝试压缩所有 normal 工具结果为摘要
2. 如果仍超过阈值 → 压缩为极简摘要（一行）
3. 如果仍超过阈值 → 终止循环，返回 "无法压缩到安全范围内"

**连续失败保护**：连续 3 次 auto-compact 失败 → 终止循环

---

## 4. InformationTracker 信息增益检测

### 4.1 问题

旧的 `_is_information_saturated` 只看结果长度（最近 3 次 < 200 chars），对多跳推理误杀严重。

### 4.2 新方案：基于信息增益

```python
class InformationTracker:
    all_entities: set[str]      # 全局已发现实体
    all_relations: set[str]     # 全局已发现关系
    all_docs: set[str]          # 全局已涉及文档
    recent_gains: deque[int]    # 每次工具调用的新发现数量
```

**`record_gain(tool_name, result)`**：
- 从结果中提取实体、关系、文档引用
- 计算增量：`delta = len(new - all)`
- 更新全局集合
- 记录增量到 recent_gains

**`is_saturated(min_recent_calls=5)`**：
- 最近 5 次工具调用的总信息增益 = 0 → 饱和
- 注入 system 消息要求 LLM 产出答案
- 给 LLM 一次机会，如果仍调用工具 → 继续（信任 LLM 判断）

### 4.3 新旧对比

| 场景 | 旧方案 | 新方案 |
|------|--------|--------|
| 短结果但有新实体 | ❌ 误杀 | ✅ 不饱和 |
| 长结果但无新信息 | ✅ 不饱和 | ✅ 可能饱和 |
| 连续空结果 | ✅ 不计入 | ✅ 增益 = 0 |
| 重复搜索已知实体 | ❌ 可能不触发 | ✅ 饱和（delta = 0） |

---

## 5. 工具并行执行

### 5.1 工具分类

| 并行 | 工具 |
|------|------|
| ✅ 可并行（读工具） | search_vector, search_keyword, read_l0, read_l1, read_l2, expand_entity, get_timeline |
| ❌ 必须串行 | ask_user, report_findings |

### 5.2 实现

```python
READ_ONLY_TOOLS = {
    "search_vector", "search_keyword", "read_l0",
    "read_l1", "read_l2", "expand_entity", "get_timeline",
}

async def execute_tool_calls(self, tool_calls, kb_id):
    read_tools = [tc for tc in tool_calls if tc.tool_name in READ_ONLY_TOOLS]
    write_tools = [tc for tc in tool_calls if tc.tool_name not in READ_ONLY_TOOLS]

    # 读工具并行（最多 5 并发）
    if read_tools:
        semaphore = asyncio.Semaphore(5)
        results = await asyncio.gather(
            *[self._execute_with_sem(tc, semaphore, kb_id) for tc in read_tools]
        )

    # 写工具串行
    for tc in write_tools:
        results.append(await self._execute_single(tc, kb_id))
```

### 5.3 收益估算

- 多跳推理中，LLM 同时调用 3 个读工具：串行 6s → 并行 2s
- 30 轮节省约 2 分钟总体响应时间

---

## 6. 错误处理

### 6.1 LLM API 错误
- `prompt_too_long` → 触发 auto-compact → 重试
- 连续 3 次 auto-compact 失败 → 返回 "上下文已满"
- 其他错误 → 重试一次 → 再失败返回错误

### 6.2 工具执行错误
- 单个工具失败 → 记录错误，不影响其他并行工具
- 全部工具失败 → 注入 system 消息，让 LLM 尝试其他方式

### 6.3 无限循环保护
- `max_iterations = 50`：安全兜底
- `InformationTracker.is_saturated()`：零新发现 → 终止
- 重复调用检测（已有）：跳过相同参数调用

---

## 7. 文件变更清单

| 文件 | 变更类型 | 内容 |
|------|---------|------|
| `backend/app/services/agent/context_manager.py` | **新增** | ContextManager 类，三层上下文管理 |
| `backend/app/services/agent/information_tracker.py` | **新增** | InformationTracker 类，信息增益跟踪 |
| `backend/app/services/agent/loop.py` | **修改** | 集成 ContextManager + InformationTracker + 并行执行，去掉硬限制 |
| `backend/app/services/agent/tools.py` | **修改** | 添加 READ_ONLY_TOOLS 分类常量 |
| `backend/app/services/agent/prompt_builder.py` | **修改** | 更新系统提示 |
| `frontend/src/components/pages/ChatView.tsx` | **修改** | 上下文占用百分比显示 |

---

## 8. 验证方法

1. **多跳推理测试**："陈平安是裴钱的师父，裴钱的拳法主要是跟谁学的"
   - 预期：Agent 能在 20-40 轮内完成推理链
   - 不应被 10 轮限制或信息饱和度误杀终止

2. **上下文管理测试**：创建一个包含 10+ 文档的知识库，问需要多文档交叉验证的复杂问题
   - 预期：microcompact 在 30K token 时触发
   - auto-compact 在接近窗口上限时触发
   - 最终能产出答案而不报 API 错误

3. **并行执行测试**：问一个需要多工具同时查询的问题
   - 预期：读工具并行执行，总体耗时减少

4. **信息增益测试**：
   - 连续搜索已知实体 → 应触发饱和检测
   - 搜索新实体有发现 → 不应触发饱和
