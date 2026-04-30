# SuperDeepAnalyze - 详细测试报告

> **日期:** 2026-04-21 14:30
> **测试人:** 凤歌
> **测试范围:** 编译流程 + 前端交互 + 5 个用户反馈问题
> **测试知识库:** lbctest_jl (kb_386a7d20)

---

## 📊 测试结果汇总

| 问题 | 状态 | 严重程度 | 根因 |
|------|------|----------|------|
| 编译无反应/卡住 | 🔴 发现根因 | P0 | Backend bug + Vite WS 代理问题 |
| 1. 侧边栏导航无反应 | ⚠️ 部分确认 | P0 | App.tsx 路由重定向导致 |
| 2. 编译 Tab 切换失效 | 🔴 发现根因 | P0 | 组件卸载 + WS 连接断开 |
| 3. 对话 WS 连接失败 | 🔴 发现根因 | P0 | 同编译 WS 问题 |
| 4. 文档状态未分离 | ⚠️ 部分实现 | P1 | UI 已有 KB 级别状态，但缺文档级别 |
| 5. Wiki 缺少总览 | ⚠️ 未实现 | P1 | 只有实体/时间线 Tab |

---

## 🔴 P0 问题：编译流程完全分析

### 现状确认

```
知识库: lbctest_jl (kb_386a7d20)
文档: 1 个 (doc_3e7ff0d5, 20MB 文本文件)
L2 Chunks: 17,108 个 ✅ 已完成
L1 摘要: 0 条 ❌ 未开始
L0 图谱: 无 ❌ 未开始
状态: partial (部分完成)
```

### 问题 1: Backend Bug - sqlite3.Row.get() 不存在

**位置:** `backend/app/api/compile.py` 第 63 行

```python
for i, doc in enumerate(docs):
    doc_id = doc["id"]
    doc_name = doc.get("filename", doc_id)  # ❌ BUG: sqlite3.Row 没有 .get() 方法
```

**错误信息:**
```
'sqlite3.Row' object has no attribute 'get'
```

**影响:** HTTP API 触发编译时立即失败

**修复方案:**
```python
# 方案 1: 使用下标访问
doc_name = doc["filename"] if doc["filename"] else doc_id

# 方案 2: 转换为 dict
doc = dict(doc)
doc_name = doc.get("filename", doc_id)
```

---

### 问题 2: WebSocket 编译连接问题

**前端 WebSocket URL 构建:**
```javascript
const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
const host = location.host  // 127.0.0.1:5174 (Vite dev server)
const ws = new WebSocket(`${proto}//${host}/api/compile/ws/${kbId}`)
```

**预期行为:**
- 前端: `ws://127.0.0.1:5174/api/compile/ws/kb_386a7d20`
- Vite 代理 → `ws://127.0.0.1:8000/api/compile/ws/kb_386a7d20`
- 后端 WebSocket 端点接收

**实际情况:**
- 点击"一键编译"后，前端显示"编译中..."
- 但后端无任何日志（未收到连接）
- 5分钟后仍然"编译中..."，无进度更新

**Vite 代理配置:**
```javascript
proxy: {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
  '/ws': {
    target: 'ws://127.0.0.1:8000',
    ws: true,
  },
}
```

**问题分析:**
- `/api/compile/ws/...` 会被 `/api` 规则匹配并转发到 `http://127.0.0.1:8000/api/compile/ws/...`
- 但 HTTP 代理和 WebSocket 代理是两套机制
- `/api` 规则没有 `ws: true`，可能无法正确处理 WebSocket 升级

**修复方案:**
```javascript
// 方案 1: 在 /api 规则中添加 ws: true
proxy: {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
    ws: true,  // 添加这行
  },
}

// 方案 2: 添加专门的 /api/compile/ws 规则
proxy: {
  '/api/compile/ws': {
    target: 'ws://127.0.0.1:8000',
    ws: true,
  },
}
```

---

### 问题 3: L1 编译任务量过大

**数据:**
- L2 Chunks: 17,108 个
- L1 batch_size: 15 chunks/批
- L1 批次数: 17,108 / 15 ≈ **1,140 批次**

**每个批次需要:**
1. 调用 LLM API 生成摘要
2. 提取实体和关系
3. 检测矛盾点

**预估时间:**
- 每个批次 LLM 调用: ~2-5 秒
- 总 L1 时间: 1,140 × 3秒 ≈ **57 分钟** (仅 L1)
- L0 构建还需要处理 1,140 条摘要，又需要大量 LLM 调用

**问题:**
- 用户看到"编译中"后，如果不知道内部耗时，会以为卡住
- 没有分阶段进度显示（只有整体百分比）
- 没有每个阶段的预估时间

**优化建议:**
1. 增加 `batch_size` 到 50-100 减少 API 调用次数
2. 添加分阶段进度："L1 摘要生成中 (第 150/1140 批)"
3. 添加预估剩余时间
4. 对于超大文档，建议先抽样编译测试

---

## ⚠️ P0/P1 问题：侧边栏导航

### 问题描述

点击侧边栏"🕸️ 图谱"、"💬 对话"、"📖 Wiki"没有反应。

### 根因

**App.tsx 路由配置:**
```tsx
<Routes>
  <Route path="/" element={<Home />} />
  <Route path="/knowledge" element={<KnowledgeBaseList />} />
  <Route path="/knowledge/:kbId" element={<KnowledgeBaseDetail />} />
  <Route path="/upload" element={<Navigate to="/knowledge" replace />} />
  <Route path="/graph" element={<Navigate to="/knowledge" replace />} />   // 重定向到列表
  <Route path="/chat" element={<Navigate to="/knowledge" replace />} />    // 重定向到列表
  <Route path="/wiki" element={<Navigate to="/knowledge" replace />} />     // 重定向到列表
  <Route path="/settings" element={<Settings />} />
</Routes>
```

**侧边栏导航链接:**
```tsx
{ path: '/graph', label: '图谱', icon: '🕸️' },
{ path: '/chat', label: '对话', icon: '💬' },
{ path: '/wiki', label: 'Wiki', icon: '📖' },
```

**问题:**
- 点击这些链接 → 跳转到 `/graph` 等
- 但路由配置将其 redirect 到 `/knowledge`
- 用户期望：点击后跳转到当前 KB 的对应 Tab

### 修复建议

让侧边栏记住当前 KB 并导航到详情页对应 Tab：
```tsx
// Sidebar.tsx
const { currentKbId } = useAppStore()

const handleNavClick = (path: string, tab?: string) => {
  if (tab && currentKbId) {
    navigate(`/knowledge/${currentKbId}`)
    // 通过 state 或 sessionStorage 传递 tab
    sessionStorage.setItem('pendingTab', tab)
  } else {
    navigate(path)
  }
}

// KnowledgeBaseDetail.tsx
useEffect(() => {
  const pendingTab = sessionStorage.getItem('pendingTab')
  if (pendingTab) {
    setActiveTab(pendingTab as TabType)
    sessionStorage.removeItem('pendingTab')
  }
}, [])
```

---

## ⚠️ P1 问题：编译 Tab 切换状态丢失

### 问题描述

在编译过程中切换 Tab，再切回来时编译状态丢失。

### 根因

```tsx
function CompileTab({ kbId, onCompileDone }: ...) {
  const [compiling, setCompiling] = useState(false)
  const [compileProgress, setCompileProgress] = useState(null)
  const wsRef = useRef<WebSocket | null>(null)
  
  // 组件卸载时 WebSocket 断开
  // 状态全部重置为初始值
}
```

切换 Tab 时 `CompileTab` 组件卸载，WebSocket 连接断开，状态全部丢失。

### 修复方案

**方案 A (推荐):** 状态提升到父组件
```tsx
function KnowledgeBaseDetail() {
  const [compiling, setCompiling] = useState(false)
  const [compileProgress, setCompileProgress] = useState(null)
  const compileWsRef = useRef<WebSocket | null>(null)
  
  // 传递给 CompileTab
  {activeTab === 'compile' && (
    <CompileTab
      kbId={kbId!}
      compiling={compiling}
      compileProgress={compileProgress}
      onStartCompile={startCompile}
      onCompileDone={onCompileDone}
    />
  )}
}
```

**方案 B:** Tab 切换时保持连接
```tsx
// 使用 React Portal 将编译状态提升到全局
// 或使用 useEffect 的 cleanup 返回空函数避免断开
```

---

## ⚠️ P1 问题：文档状态未分离

### 现状

文档列表已显示两个状态标签（解析 + 编译），但编译状态是 KB 级别的，不是文档级别的。

### 用户期望

每个文档应该有独立的编译状态：
- 文档 A: 已解析 + 已编译
- 文档 B: 已解析 + 待编译
- 文档 C: 解析中 + 待编译

### 修复建议

1. 数据库增加 `document_compile_status` 字段
2. 前端显示文档级编译状态
3. 支持单独编译某个文档

---

## ⚠️ P1 问题：Wiki 缺少总览 Tab

### 现状

Wiki Tab 只有"实体"和"时间线"两个子 Tab。

### 用户期望

"总览" Tab 应该显示：
- 统计卡片（实体数、事件数、类型数）
- 实体类型分布图
- 主要实体速览网格
- 最近事件列表

### 修复建议

```tsx
function WikiTab({ kbId }: { kbId: string }) {
  const [activeTab, setActiveTab] = useState<'overview' | 'entities' | 'timeline'>('overview')
  
  return (
    <>
      <div className="tab-bar">
        <button onClick={() => setActiveTab('overview')}>总览</button>
        <button onClick={() => setActiveTab('entities')}>实体</button>
        <button onClick={() => setActiveTab('timeline')}>时间线</button>
      </div>
      
      {activeTab === 'overview' && <WikiOverview kbId={kbId} />}
      {activeTab === 'entities' && <WikiEntities kbId={kbId} />}
      {activeTab === 'timeline' && <WikiTimeline kbId={kbId} />}
    </>
  )
}
```

---

## 🔧 修复优先级

### 立即修复 (P0)

| 优先级 | 问题 | 修复位置 | 修复方案 |
|--------|------|----------|----------|
| P0 | sqlite3.Row.get() bug | compile.py:63 | `doc.get()` → `doc["filename"]` |
| P0 | Vite WS 代理配置 | vite.config.ts | 添加 `ws: true` 到 `/api` 规则 |
| P0 | 编译状态不持久 | KnowledgeBaseDetail | 将编译状态提升到父组件 |
| P0 | 侧边栏导航 | Sidebar.tsx | 导航到 KB 详情对应 Tab |

### 短期优化 (P1)

| 优先级 | 问题 | 修复位置 |
|--------|------|----------|
| P1 | L1 批次过大 | l1_compiler.py batch_size |
| P1 | 无分阶段进度 | compile.py 进度推送 |
| P1 | L1 批次进度不精细 | compile.py L1 进度计算逻辑 |
| P1 | 文档级编译状态 | 数据库 + 前端 |
| P1 | Wiki 总览 Tab | WikiView.tsx |

### 长期优化 (P2)

| 优先级 | 问题 |
|--------|------|
| P2 | 编译取消功能 |
| P2 | 断点续编译 |
| P2 | 编译历史记录 |

---

## 💡 体验优化建议：L1 编译进度精细化

### 问题
L1 编译有 ~1,140 批次，当前只推送批次消息，没有精细的进度（当前批次/总批次），用户感觉不到进展。

### 优化方案

#### 后端修改 (`backend/app/api/compile.py`)

**当前代码问题:**
```python
def make_l1_cb(dn: str, total: int):
    async def cb(msg: str):
        await _send_progress(progress_cb, {
            "type": "status",
            "phase": "compiling_l1",
            "progress": 40 + int(30 * (i + 0.5) / total_docs),  # ❌ 只按文档进度，不按批次
            "message": f"L1 摘要 {dn}: {msg}",
        })
    return cb
```

**优化后的代码:**
```python
# 在循环外记录批次计数器
l1_batch_index = 0  # 新增
l1_total_batches = sum(
    (len(chunk_text(open(settings.KB_DIR / kb_id / "documents" / doc_id / "parsed.md").read(), doc_id=doc_id, kb_id=kb_id)) + batch_size - 1) // batch_size
    for doc in docs if not (settings.KB_DIR / kb_id / "documents" / doc_id / "l1_summaries.json").exists()
)  # 新增：预先计算总批次数

for i, doc in enumerate(docs):
    # ... 现有代码 ...
    
    # L1 编译时传递批次计数器
    def make_l1_cb(dn: str, total_batches: int):  # 修改签名
        async def cb(msg: str, batch_idx: int = 0, batch_total: int = 0):  # 修改回调签名
            # 计算整体进度: L1 占 40-70%
            batch_progress = int(40 + 30 * batch_idx / batch_total) if batch_total > 0 else 40
            await _send_progress(progress_cb, {
                "type": "status",
                "phase": "compiling_l1",
                "progress": batch_progress,
                "message": f"L1 摘要 {dn}: 第 {batch_idx}/{batch_total} 批 — {msg}",
            })
        return cb

    l1_results = await l1.compile_batch(chunks, progress_cb=make_l1_cb(doc_name, l1_total_batches))
```

**L1Compiler 修改 (`backend/app/services/compilation/l1_compiler.py`):**

```python
async def compile_batch(self, chunks: list[Chunk], batch_size: int = 15, progress_cb=None) -> list[dict]:
    results = []
    total_batches = (len(chunks) + batch_size - 1) // batch_size
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        batch_num = i // batch_size + 1
        
        if progress_cb:
            # 传递 batch_idx 和 batch_total
            progress_cb(f"正在生成第 {batch_num}/{total_batches} 批", batch_idx=batch_num, batch_total=total_batches)
        
        summary = await self.generate_summary(batch)
        results.append(summary)
        
        if progress_cb:
            progress_cb(f"第 {batch_num}/{total_batches} 批完成", batch_idx=batch_num, batch_total=total_batches)
    return results
```

#### 前端修改 (`frontend/src/components/pages/KnowledgeBaseDetail.tsx`)

**进度条显示优化:**
```tsx
{compiling && compileProgress && (
  <div className="mt-4 p-4 bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700">
    <div className="flex items-center gap-2 text-sm mb-2">
      <span className="text-lg">{phaseIcons[compileProgress.phase] || '⚙️'}</span>
      <span className="text-stone-600 dark:text-stone-300 font-medium">{compileProgress.message}</span>
      <span className="ml-auto text-amber-600 dark:text-amber-400 font-mono text-sm">{compileProgress.progress}%</span>
    </div>
    <div className="w-full bg-stone-200 dark:bg-slate-700 rounded-full h-2.5 overflow-hidden">
      <div 
        className="h-full bg-gradient-to-r from-amber-400 to-amber-600 rounded-full transition-all duration-500 ease-out" 
        style={{ width: `${compileProgress.progress}%` }} 
      />
    </div>
    {/* 显示预估剩余时间 */}
    {compileProgress.estimated_remaining && (
      <div className="mt-2 text-xs text-stone-400 dark:text-stone-500">
        预计剩余时间: ~{compileProgress.estimated_remaining}
      </div>
    )}
  </div>
)}
```

### 预期效果

优化后用户看到的进度消息：
```
🔨 L2 索引 1-28世纪裁判校验.txt — 17108 个文本块，正在构建向量与关键词索引... 35%
📝 L1 摘要 1-28世纪裁判校验.txt: 第 1/1140 批 — 正在生成... 40%
📝 L1 摘要 1-28世纪裁判校验.txt: 第 2/1140 批 — 正在生成... 41%
📝 L1 摘要 1-28世纪裁判校验.txt: 第 150/1140 批 — 正在生成... 44%
...
🕸️ L0 全局图谱构建 (基于 1140 条摘要)... 75%
✅ 编译完成! 1 文档, 17108 chunks, 1140 L1 摘要 100%
```

---

## 📋 给 Claude Code 的修复指令

### 1. 修复 sqlite3.Row.get() Bug

**文件:** `backend/app/api/compile.py`
**行号:** 63

```python
# 找到
doc_name = doc.get("filename", doc_id)

# 替换为
doc_name = doc["filename"] if doc["filename"] else doc_id
```

### 2. 修复 Vite WebSocket 代理

**文件:** `frontend/vite.config.ts`

```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:8000',
      changeOrigin: true,
      ws: true,  // 新增：支持 WebSocket
    },
  },
}
```

### 3. 提升编译状态到父组件

**文件:** `frontend/src/components/pages/KnowledgeBaseDetail.tsx`

需要将 `CompileTab` 中的以下状态提升到 `KnowledgeBaseDetail`:
- `compiling`
- `compileProgress`
- `compileLog`
- `wsRef`

然后通过 props 传递给 `CompileTab`。

### 4. 修复侧边栏导航

**文件:** `frontend/src/components/Sidebar.tsx`

修改导航逻辑，记住当前 KB 并导航到详情页对应 Tab。

---

## 📊 测试数据

### lbctest_jl 知识库详情

```
ID: kb_386a7d20
名称: lbctest_jl
文档数: 1
文件: 1-28世纪裁判校验.txt (20MB)
解析状态: completed
编译状态: partial (L2完成, L1/L0未完成)
L2 Chunks: 17,108 个
```

### 编译预估时间

| 阶段 | 批次数 | 预估时间 |
|------|--------|----------|
| L1 摘要 | ~1,140 批 | 50-60 分钟 |
| L0 图谱 | 1 次 | 5-10 分钟 |
| **总计** | | **55-70 分钟** |

---

## 📸 测试截图

| 截图 | 描述 |
|------|------|
| test-screenshot-01.png | 知识库列表 |
| test-screenshot-02.png | KB 详情页 Tab bar |
| test-screenshot-03.png | 编译 Tab（未开始） |
| test-screenshot-04.png | 编译 Tab（点击后卡住） |

---

*本报告由凤歌（OpenClaw）于 2026-04-21 整理*
