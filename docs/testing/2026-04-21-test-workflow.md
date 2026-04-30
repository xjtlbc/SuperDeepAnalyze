# SuperDeepAnalyze - 完整测试工作流

> **日期:** 2026-04-21
> **目的:** 5 个用户反馈问题的验证测试流程
> **前置条件:** Claude Code 完成优化修改
> **测试知识库:** lbctest_jl（建议）/ 其他已有数据的知识库
> **测试工具:** agent-browser CLI（前端）+ HTTP API（后端）

---

## 📋 测试前检查清单

### 环境状态
- [ ] 后端运行在 `http://127.0.0.1:8000`
- [ ] 前端运行在 `http://127.0.0.1:5173`
- [ ] 知识库 lbctest_jl 存在且已有上传文档
- [ ] agent-browser CLI 可用（`agent-browser --version`）

### 测试数据
```bash
# 确认知识库存在且有数据
curl http://127.0.0.1:8000/api/knowledge-bases
# 预期: 返回包含 lbctest_jl 的列表

# 确认文档已上传
curl http://127.0.0.1:8000/api/documents/list/<kb_id>
# 预期: 返回文档列表
```

---

## 🧪 问题 1：侧边栏导航测试

### 测试目标
验证图谱、对话、Wiki 导航按钮是否正常工作

### 测试步骤

```bash
# 1. 打开前端首页
agent-browser open "http://127.0.0.1:5173/"

# 2. 等待加载
agent-browser wait 2000

# 3. 截图保存初始状态
agent-browser screenshot
```

**测试点 1.1：首页导航**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 点击侧边栏"🏠 首页" | 跳转到首页，显示 SuperDeepAnalyze 标题 |
| 2 | 点击"📁 知识库" | 跳转到知识库列表页 |
| 3 | 点击"⚙️ 设置" | 跳转到设置页 |

**测试点 1.2：知识库详情页 Tab 导航**

```bash
# 1. 进入知识库 lbctest_jl
# 假设知识库 ID 为 lbctest_jl_id，先获取 ID
# 通过点击知识库列表中的卡片进入详情页

# 2. 截图当前状态
agent-browser screenshot

# 3. 点击 Tab bar 上的"🕸️ 图谱"
agent-browser click "text=🕸️ 图谱"
agent-browser wait 1000
agent-browser screenshot

# 4. 验证图谱 Tab 内容
# 预期: 切换到图谱视图，显示图谱Canvas或空状态引导
```

**测试点 1.3：侧边栏直接导航**

```bash
# 1. 在图谱 Tab 下，直接点击侧边栏的"📖 Wiki"
agent-browser click "text=📖 Wiki"
agent-browser wait 1000
agent-browser screenshot

# 预期: 
# - 如果有选中 KB → 跳转到该 KB 的 Wiki Tab
# - 如果没有 KB → 跳转到知识库列表
```

**测试点 1.4：对话导航**

```bash
# 1. 点击侧边栏"💬 对话"
agent-browser click "text=💬 对话"
agent-browser wait 1000
agent-browser screenshot

# 预期: 
# - 如果有选中 KB → 显示对话界面（包含会话列表）
# - 如果没有 KB → 跳转知识库列表
```

### 验证标准

| 功能 | 验证点 | 状态 |
|------|--------|------|
| 首页导航 | 点击各导航项正常跳转 | ❌ / ⚠️ / ✅ |
| Tab 切换 | 详情页 Tab bar 切换正常 | ❌ / ⚠️ / ✅ |
| 侧边栏 → 图谱 | 跳转 KB 详情图谱 Tab | ❌ / ⚠️ / ✅ |
| 侧边栏 → Wiki | 跳转 KB 详情 Wiki Tab | ❌ / ⚠️ / ✅ |
| 侧边栏 → 对话 | 跳转 KB 详情对话 Tab | ❌ / ⚠️ / ✅ |

### 回归检查
- 知识库列表页是否正常显示
- 主题切换是否正常
- 设置页是否正常

---

## 🧪 问题 2：编译 Tab 切换测试

### 测试目标
验证编译过程中切换 Tab 后，状态是否正确保持或恢复

### 前置条件
知识库 lbctest_jl 已有上传文档

### 测试步骤

```bash
# 1. 进入知识库 lbctest_jl 详情页
agent-browser open "http://127.0.0.1:5173/knowledge"
agent-browser wait 2000

# 2. 点击知识库卡片进入详情页
agent-browser snapshot -i
# 找到 lbctest_jl 的卡片并点击

# 3. 切换到"🔨 编译" Tab
agent-browser click "text=🔨 编译"
agent-browser wait 1000
agent-browser screenshot
```

**测试点 2.1：编译状态保持**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 点击"一键编译全部"按钮 | 显示"连接编译服务..."，进度条出现 |
| 2 | 立即切换到"📄 文档" Tab | 编译继续后台运行 |
| 3 | 等待 3 秒，切换回"🔨 编译" Tab | 进度状态保持或已更新 |
| 4 | 验证编译进度 | 显示正确的编译阶段和百分比 |

**测试点 2.2：编译中状态重连**

```bash
# 1. 开始编译
agent-browser click "text=一键编译全部"
agent-browser wait 2000

# 2. 切换到其他 Tab
agent-browser click "text=📄 文档"
agent-browser wait 3000

# 3. 切回编译 Tab
agent-browser click "text=🔨 编译"
agent-browser wait 1000
agent-browser screenshot

# 预期:
# - 如果编译仍在进行 → 显示当前进度（不是重新开始）
# - 如果编译已完成 → 显示"编译完成"结果
# - 如果编译失败 → 显示错误信息
```

**测试点 2.3：编译完成验证**

```bash
# 等待编译完成（可能需要几分钟）
# 可以通过 API 轮询检查状态

# 后端 API 检查编译状态
curl http://127.0.0.1:8000/api/knowledge-bases | jq '.[] | select(.name=="lbctest_jl") | .compile_status'

# 预期: "completed" 或 "processing"
```

### 验证标准

| 功能 | 验证点 | 状态 |
|------|--------|------|
| 编译启动 | 点击按钮后 WebSocket 连接 | ❌ / ⚠️ / ✅ |
| Tab 切换保持 | 切换后编译状态不丢失 | ❌ / ⚠️ / ✅ |
| 状态恢复 | 切回编译 Tab 显示正确进度 | ❌ / ⚠️ / ✅ |
| 编译完成 | 完成后显示正确的结果统计 | ❌ / ⚠️ / ✅ |
| 错误处理 | 编译失败时显示错误信息 | ❌ / ⚠️ / ✅ |

---

## 🧪 问题 3：对话功能测试

### 测试目标
验证 WebSocket 连接、消息显示、Agent Loop 展示

### 测试步骤

```bash
# 1. 进入知识库 lbctest_jl 的对话 Tab
agent-browser open "http://127.0.0.1:5173/knowledge"
agent-browser wait 2000

# 2. 点击知识库卡片
agent-browser snapshot -i
# 找到并点击 lbctest_jl

# 3. 切换到"💬 对话" Tab
agent-browser click "text=💬 对话"
agent-browser wait 1000
agent-browser screenshot
```

**测试点 3.1：会话列表**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 查看左侧会话列表 | 显示已有会话或空状态 |
| 2 | 点击"+ 新对话"按钮 | 创建新会话，输入框可用 |
| 3 | 会话列表显示新会话 | 新会话出现在列表顶部 |

**测试点 3.2：WebSocket 连接**

```bash
# 1. 创建或选择会话后，观察连接状态
agent-browser wait 2000
agent-browser snapshot -i

# 预期: 不应显示"连接中..."或"连接失败"
# 应该显示"idle"或直接可输入
```

**测试点 3.3：发送消息（乐观更新）**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 在输入框输入"你好" | 输入框显示文字 |
| 2 | 点击"发送"按钮 | 输入框立即清空 |
| 3 | **观察点：消息是否立即显示** | 用户消息**立即**出现在对话区 |
| 4 | 等待 Agent 回复 | Agent 回复出现（可能需要 10-30 秒） |

```bash
# 1. 输入消息
agent-browser fill "placeholder=输入问题..." "分析一下这个案件的主要人物"
agent-browser wait 500

# 2. 点击发送
agent-browser click "text=发送"
agent-browser wait 500
agent-browser screenshot

# 预期: 用户消息立即显示（乐观更新）
```

**测试点 3.4：WebSocket 连接状态**

```bash
# 观察发送后的状态
agent-browser wait 2000
agent-browser snapshot -i

# 检查是否有以下状态显示：
# - "连接中..." → WebSocket 正在连接
# - "连接已断开" → WebSocket 连接失败
# - 空白 → 连接正常或使用 HTTP fallback
```

**测试点 3.5：Agent Loop 展示**

```bash
# 发送一个需要多步推理的问题
agent-browser fill "placeholder=输入问题..." "张三和李四是什么关系？他们之间有什么事件？"
agent-browser click "text=发送"
agent-browser wait 3000
agent-browser screenshot

# 观察是否显示：
# 1. "🤔 Agent 思考中..." 指示器
# 2. 工具调用卡片（🔍 向量搜索、📝 读取 L1 等）
# 3. 工具输入/输出详情（可展开）
```

**Agent Loop 展示检查清单：**
- [ ] 思考指示器显示
- [ ] 工具调用名称显示（search_vector, read_l0 等）
- [ ] 工具耗时显示（XXms）
- [ ] 工具输入详情可展开查看
- [ ] 工具输出摘要可展开查看
- [ ] 引用溯源显示（如果有）
- [ ] 最终答案显示

**测试点 3.6：HTTP Fallback**

```bash
# 如果 WebSocket 持续失败，验证 HTTP 轮询是否工作

# 1. 发送消息后等待 30 秒
agent-browser wait 30000
agent-browser screenshot

# 预期: 
# - 如果 WS 成功 → 收到回复
# - 如果 WS 失败 → 应该切换到 HTTP 轮询，仍收到回复
# - 不应卡在"连接中"状态
```

### 验证标准

| 功能 | 验证点 | 状态 |
|------|--------|------|
| 会话创建 | 新建会话正常 | ❌ / ⚠️ / ✅ |
| 会话删除 | 删除按钮存在且有效 | ❌ / ⚠️ / ✅ |
| 消息乐观更新 | 发送后立即显示 | ❌ / ⚠️ / ✅ |
| WS 连接 | 连接成功不卡住 | ❌ / ⚠️ / ✅ |
| WS 失败处理 | 自动切换 HTTP 轮询 | ❌ / ⚠️ / ✅ |
| Agent Loop - 思考 | 显示思考指示器 | ❌ / ⚠️ / ✅ |
| Agent Loop - 工具调用 | 显示工具卡片 | ❌ / ⚠️ / ✅ |
| Agent Loop - 详情 | 工具输入输出可展开 | ❌ / ⚠️ / ✅ |
| 最终回复 | 回复内容正确显示 | ❌ / ⚠️ / ✅ |

---

## 🧪 问题 4：文档状态分离测试

### 测试目标
验证文档列表显示解析状态和编译状态两个维度

### 测试步骤

```bash
# 1. 进入知识库 lbctest_jl 的文档 Tab
agent-browser open "http://127.0.0.1:5173/knowledge"
agent-browser wait 2000
agent-browser click "text=lbctest_jl"  # 假设卡片文本包含名称
agent-browser wait 1000
agent-browser click "text=📄 文档"
agent-browser wait 1000
agent-browser screenshot
```

### 验证标准

**文档标签检查：**

每个文档应显示**两个**状态标签：

| 文档状态 | 解析标签 | 编译标签 | 示例 |
|---------|---------|---------|------|
| 已上传未编译 | 已解析 / 解析中 / 失败 | 待编译 | 🟢 已解析 + ⚪ 待编译 |
| 编译中 | 已解析 | 编译中 | 🟢 已解析 + 🟡 编译中 |
| 已完成 | 已解析 | 已编译 | 🟢 已解析 + 🔵 已编译 |

```bash
# 截图并检查文档列表中的标签
agent-browser screenshot

# 预期: 每个文档右侧有两个标签，不是只有一个
```

### 详细检查清单

- [ ] 文档列表显示"解析状态"标签
- [ ] 文档列表显示"编译状态"标签
- [ ] 解析状态：已解析 / 解析中 / 失败 正确显示
- [ ] 编译状态：待编译 / 编译中 / 已编译 正确显示
- [ ] 知识库级别的编译状态指示器正确

---

## 🧪 问题 5：Wiki 总览 Tab 测试

### 测试目标
验证 Wiki 页面有"总览"页签，并正确显示统计数据

### 测试步骤

```bash
# 1. 进入知识库 lbctest_jl 的 Wiki Tab
agent-browser open "http://127.0.0.1:5173/knowledge"
agent-browser wait 2000
agent-browser click "text=lbctest_jl"
agent-browser wait 1000
agent-browser click "text=📖 Wiki"
agent-browser wait 1000
agent-browser screenshot
```

### 验证标准

**Tab 布局：**

Wiki 区域应有**三个**子 Tab 按钮：
- "总览"（默认激活）
- "实体"
- "时间线"

```bash
# 检查 Tab 按钮存在
agent-browser snapshot -i

# 预期看到:
# - [总览] [实体] [时间线] 三个按钮
# - "总览" 默认高亮（底部有边框）
```

**总览页签内容：**

```bash
agent-browser screenshot

# 预期显示:
# 1. 统计卡片（4 个）：
#    - 实体总数
#    - 时间线事件数
#    - 实体类型数
#    - 人物数量
#
# 2. 实体类型分布图（水平条形图）
#
# 3. 主要实体速览（网格布局，显示前 6 个）
#
# 4. 最近事件（如果有，显示前 3-5 个）
```

**Tab 切换：**

```bash
# 1. 点击"实体" Tab
agent-browser click "text=实体"
agent-browser wait 1000
agent-browser screenshot

# 预期: 显示实体列表（按类型分组）

# 2. 点击"时间线" Tab
agent-browser click "text=时间线"
agent-browser wait 1000
agent-browser screenshot

# 预期: 显示时间线视图（垂直时间轴）

# 3. 点击"总览" Tab
agent-browser click "text=总览"
agent-browser wait 1000
agent-browser screenshot

# 预期: 返回总览视图
```

### 详细检查清单

- [ ] Wiki 有三个 Tab：总览、实体、时间线
- [ ] "总览"是默认激活 Tab
- [ ] 总览显示统计卡片（实体总数/事件数/类型数/人物数）
- [ ] 总览显示实体类型分布条形图
- [ ] 总览显示主要实体速览网格
- [ ] 总览显示最近事件列表
- [ ] 实体 Tab 可按类型筛选
- [ ] 时间线 Tab 显示时间轴视图
- [ ] 点击实体可查看详情

---

## 🧪 问题 6：Agent 多跳推理能力测试

> 详细测试用例见: `2026-04-21-multi-hop-test-cases.md`

### 测试目标
验证 Agent 能否通过多次工具调用、信息串联、逻辑推理得出正确答案，而非在第 10 轮被强制终止后给出无关答案。

### 核心测试问题

| 用例 ID | 问题 | 预期跳数 | 难度 |
|---------|------|---------|------|
| TC-MH-01 | "陈平安是裴钱的师父，请问裴钱的拳法主要是跟谁学的。" | 2-3 | ⭐⭐⭐ |
| TC-MH-02 | "崔东山和齐静春是什么关系？他们之间有什么关联事件？" | 2 | ⭐⭐ |
| TC-MH-03 | "剑气长城为什么重要？它在整个故事中扮演什么角色？" | 2-3 | ⭐⭐ |
| TC-MH-04 | "陈平安第一次离开小镇是什么时候？离开前发生了什么？" | 2 | ⭐⭐ |
| TC-MH-05 | "关于陈平安的性格特点，不同文档中是如何描述的？" | 2 | ⭐⭐ |
| TC-MH-11 | "陈平安的本命瓷是谁打碎的？打碎后发生了什么？这对陈平安的修行有什么影响？" | 3-4 | ⭐⭐⭐⭐ |

### 测试步骤

```bash
# 1. 进入 jltest 知识库的对话 Tab
agent-browser open "http://127.0.0.1:5173/knowledge"
agent-browser wait 2000
# 点击 jltest 知识库卡片 → 切换到对话 Tab

# 2. 发送核心测试问题
agent-browser fill "placeholder=输入问题..." "陈平安是裴钱的师父，请问裴钱的拳法主要是跟谁学的。"
agent-browser click "text=发送"

# 3. 等待 Agent 回复（多跳问题可能需要 2-5 分钟）
agent-browser wait 120000
agent-browser screenshot

# 4. 检查 Agent Loop 详情 — 工具调用链是否合理
```

### 关键检查点

| 检查项 | 通过标准 | 失败模式 |
|--------|---------|---------|
| 推理轮次 | >= 需要的跳数 + 1 | 10 轮被强制终止 |
| 工具多样性 | 至少使用 2 种不同工具 | 只搜索一次就给答案 |
| 答案正确性 | 答案与文档内容一致 | 答案错误或无关 |
| 答案引用 | 引用了具体文档/chunk | 无引用、凭空编造 |
| 循环检测 | 不重复执行相同查询 | 陷入循环或误杀 |
| 信息饱和 | 真正穷尽后才触发 | 精准查询被误判 |

### 执行方式

**推荐：后端 API 直接测试**（更可靠，不受前端 UI 影响）

```bash
# 1. 获取知识库 ID
curl http://127.0.0.1:8000/api/knowledge-bases | jq '.[] | select(.name=="jltest") | .id'

# 2. 创建会话
curl -X POST http://127.0.0.1:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"kb_id": "<kb_id>", "title": "多跳推理测试-MH01"}'

# 3. 发送测试问题
curl -X POST http://127.0.0.1:8000/api/sessions/<session_id>/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "陈平安是裴钱的师父，请问裴钱的拳法主要是跟谁学的。", "role": "user"}'

# 4. 等待 2-3 分钟后查询结果
curl http://127.0.0.1:8000/api/sessions/<session_id>/messages | jq '.[] | select(.role=="assistant")'
```

### 验证标准

| 功能 | 验证点 | 状态 |
|------|--------|------|
| TC-MH-01 师徒关系 | 正确推理出裴钱的拳法来源 | ❌ / ⚠️ / ✅ |
| TC-MH-02 人物关系 | 找到崔东山和齐静春的关联 | ❌ / ⚠️ / ✅ |
| TC-MH-03 事件因果 | 归纳剑气长城的重要性 | ❌ / ⚠️ / ✅ |
| TC-MH-04 时间线 | 定位离开小镇的时间和前置事件 | ❌ / ⚠️ / ✅ |
| TC-MH-05 跨文档 | 引用多份文档的描述 | ❌ / ⚠️ / ✅ |
| TC-MH-11 长链推理 | 完成 3 跳以上的推理链 | ❌ / ⚠️ / ✅ |
| TC-BH-01 轮次充足 | 不被 10 轮阈值过早截断 | ❌ / ⚠️ / ✅ |
| TC-BH-02 工具多样 | 使用多种工具进行推理 | ❌ / ⚠️ / ✅ |
| TC-BH-05 答案质量 | 基于搜索结果的真实答案 | ❌ / ⚠️ / ✅ |

---

## 📊 综合验证测试

### 全流程 E2E 测试

完成所有问题修复验证后，执行完整流程测试：

```bash
# 场景：从空白知识库到完整对话分析

# 1. 创建新知识库
agent-browser open "http://127.0.0.1:5173/knowledge"
agent-browser click "text=+ 新建知识库"
agent-browser wait 1000
agent-browser screenshot

# 2. 上传文档
# （进入 KB 详情 → 文档 Tab → 拖拽上传）

# 3. 执行编译
# （编译 Tab → 一键编译 → 等待完成）

# 4. 查看图谱
# （图谱 Tab → 验证节点和边显示）

# 5. 查看 Wiki
# （Wiki Tab → 切换总览/实体/时间线）

# 6. 对话分析
# （对话 Tab → 发送问题 → 验证 Agent Loop）
```

### 回归测试检查清单

| 模块 | 检查点 | 状态 |
|------|--------|------|
| 知识库管理 | 创建/删除知识库 | ❌ / ⚠️ / ✅ |
| 文档上传 | 拖拽上传功能 | ❌ / ⚠️ / ✅ |
| 主题切换 | 暗色/明亮主题 | ❌ / ⚠️ / ✅ |
| 设置页 | 模型配置保存 | ❌ / ⚠️ / ✅ |
| 导航 | 侧边栏所有链接 | ❌ / ⚠️ / ✅ |
| 编译 | WebSocket 进度推送 | ❌ / ⚠️ / ✅ |
| 图谱 | 节点渲染和交互 | ❌ / ⚠️ / ✅ |
| 对话 | WebSocket 实时通信 | ❌ / ⚠️ / ✅ |
| Agent 多跳推理 | 多跳问题正确回答 | ❌ / ⚠️ / ✅ |

---

## 🐛 问题记录模板

发现问题时，使用以下格式记录：

```markdown
### [问题编号] 问题标题

**页面:** 
**操作步骤:**
1. 
2. 
3. 

**预期行为:**


**实际行为:**


**截图:** 


**严重程度:** P0 / P1 / P2

**复现概率:** 100% / 50% / 10%

**可能原因:**


**建议修复:**
```

---

## 📝 测试报告模板

```markdown
# SuperDeepAnalyze 测试报告 - [日期]

**测试人:** 凤歌
**测试范围:** 用户反馈 5 个问题验证 + Agent 多跳推理能力
**测试知识库:** lbctest_jl / jltest

## 测试结果汇总

| 问题 | 验证结果 | 阻塞问题 |
|------|---------|---------|
| 问题 1：侧边栏导航 | ✅ 通过 / ⚠️ 部分通过 / ❌ 未通过 | 是 / 否 |
| 问题 2：编译 Tab 切换 | ✅ 通过 / ⚠️ 部分通过 / ❌ 未通过 | 是 / 否 |
| 问题 3.1：WS 连接 | ✅ 通过 / ⚠️ 部分通过 / ❌ 未通过 | 是 / 否 |
| 问题 3.2：消息立即显示 | ✅ 通过 / ⚠️ 部分通过 / ❌ 未通过 | 是 / 否 |
| 问题 3.3：Agent Loop | ✅ 通过 / ⚠️ 部分通过 / ❌ 未通过 | 是 / 否 |
| 问题 4：文档状态分离 | ✅ 通过 / ⚠️ 部分通过 / ❌ 未通过 | 是 / 否 |
| 问题 5：Wiki 总览 | ✅ 通过 / ⚠️ 部分通过 / ❌ 未通过 | 是 / 否 |
| 问题 6：Agent 多跳推理 | ✅ 通过 / ⚠️ 部分通过 / ❌ 未通过 | 是 / 否 |

## Agent 多跳推理详细结果

| 用例 | 轮次 | 工具数 | 强制终止 | 答案质量 | 耗时 | 备注 |
|------|------|--------|---------|---------|------|------|
| TC-MH-01 | | | | | | |
| TC-MH-02 | | | | | | |
| TC-MH-03 | | | | | | |
| TC-MH-11 | | | | | | |

### Agent 行为指标

| 指标 | 通过 | 失败 | 备注 |
|------|------|------|------|
| TC-BH-01 推理轮次充足性 | | | |
| TC-BH-02 工具调用多样性 | | | |
| TC-BH-03 循环检测有效性 | | | |
| TC-BH-04 信息饱和度判断 | | | |
| TC-BH-05 最终答案质量 | | | |

## 详细测试记录

### 问题 1：侧边栏导航

**测试步骤:** [描述]

**测试结果:** 
- 图谱导航: ✅ 正常 / ❌ 异常
- Wiki 导航: ✅ 正常 / ❌ 异常
- 对话导航: ✅ 正常 / ❌ 异常

**发现问题:** [如有]

---

## 遗留问题

| 优先级 | 问题描述 | 状态 |
|--------|---------|------|
| P0 | | 待修复 |
| P1 | | 待修复 |
| P2 | | 优化项 |

## 总结

[总体评估]
```

---

*本测试工作流由凤歌（OpenClaw）整理*
*最后更新: 2026-04-21*
