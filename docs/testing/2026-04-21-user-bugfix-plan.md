# SuperDeepAnalyze - 用户实测 5 个问题的根因分析与修复方案

> **日期:** 2026-04-21
> **测试人:** 刘炳成 (用户实测)
> **分析人:** 凤歌 (代码审查)
> **参考知识库:** lbctest_jl

---

## 问题 1：左侧导航栏的图谱、对话、Wiki 点击没有反应

### 根因分析

**代码位置:** `frontend/src/components/Sidebar.tsx`

```tsx
const navItems = [
  { path: '/', label: '首页', icon: '🏠' },
  { path: '/knowledge', label: '知识库', icon: '📁' },
  { path: '/upload', label: '上传', icon: '📤' },
  { path: '/graph', label: '图谱', icon: '🕸️' },    // ← 旧路由
  { path: '/chat', label: '对话', icon: '💬' },       // ← 旧路由
  { path: '/wiki', label: 'Wiki', icon: '📖' },       // ← 旧路由
  { path: '/settings', label: '设置', icon: '⚙️' },
]
```

旧路由 `/graph`、`/chat`、`/wiki` 指向独立页面组件。这些组件的代码逻辑是：

```tsx
// 以 GraphView.tsx 为例
if (!currentKbId) {
  return <div>...选择知识库查看图谱...<select onChange={(e) => setCurrentKbId(e.target.value)}>...</select></div>
}
```

当 `currentKbId` 为 null 时，页面显示一个下拉选择器而不是图谱内容。如果用户之前进入过详情页（`setCurrentKb` 被调用），`currentKbId` 有值，旧页面会显示内容，但：
- **没有 Tab 切换能力**，只能看单一功能
- **状态与详情页不同步**，操作详情后旧页面不会更新

### 修复方案

**方案 A（推荐）：** 让侧边栏导航跳转到当前 KB 详情页 + 预激活 Tab

```tsx
// Sidebar.tsx 修改
import { useAppStore } from '../store/app'

function Sidebar() {
  const { currentKbId } = useAppStore()
  const navigate = useNavigate()

  const handleNavClick = (path: string, tab?: string) => {
    if (tab && currentKbId) {
      // 跳转到详情页并激活对应 Tab
      navigate(`/knowledge/${currentKbId}`)
      // 通过 URL hash 或 sessionStorage 传递 tab 信息
      sessionStorage.setItem('activeTab', tab)
    } else {
      navigate(path)
    }
  }

  return (
    <nav>
      <NavLink onClick={() => handleNavClick('/graph', 'graph')}>🕸️ 图谱</NavLink>
      <NavLink onClick={() => handleNavClick('/chat', 'chat')}>💬 对话</NavLink>
      <NavLink onClick={() => handleNavClick('/wiki', 'wiki')}>📖 Wiki</NavLink>
    </nav>
  )
}

// KnowledgeBaseDetail.tsx 读取 sessionStorage
useEffect(() => {
  const savedTab = sessionStorage.getItem('activeTab')
  if (savedTab && ['documents', 'compile', 'wiki', 'graph', 'chat'].includes(savedTab)) {
    setActiveTab(savedTab as TabType)
  }
  sessionStorage.removeItem('activeTab')
}, [])
```

**方案 B（简化）：** 将旧路由重定向到知识库列表

```tsx
// App.tsx
import { Navigate } from 'react-router-dom'

<Route path="/graph" element={<Navigate to="/knowledge" replace />} />
<Route path="/chat" element={<Navigate to="/knowledge" replace />} />
<Route path="/wiki" element={<Navigate to="/knowledge" replace />} />
```

> **推荐先执行方案 A**，用户体验更好。方案 B 作为备选。

---

## 问题 2：编译中切换 Tab 导致界面失效

### 根因分析

**代码位置:** `KnowledgeBaseDetail.tsx` → `CompileTab` 组件

```tsx
function CompileTab({ kbId, onCompileDone }: { kbId: string; onCompileDone?: () => void }) {
  const [compiling, setCompiling] = useState(false)  // ← 组件卸载时丢失
  const [compileProgress, setCompileProgress] = useState<CompileProgress | null>(null)  // ← 丢失
  const wsRef = useRef<WebSocket | null>(null)  // ← 组件卸载时 WS 断开

  const handleCompile = async () => {
    setCompiling(true)
    setCompileProgress({ type: 'status', phase: 'connecting', progress: 0, message: '连接中...' })
    const ws = new WebSocket(`${proto}//${host}/api/compile/ws/${kbId}`)
    wsRef.current = ws

    ws.onclose = () => { setCompiling(false) }  // ← 切换 Tab 触发 onclose → 状态重置
  }
}
```

**问题链路：**
1. 用户点击"编译" → WebSocket 连接建立 → `compiling=true`
2. 用户切换到"文档" Tab → `CompileTab` 卸载 → `wsRef.current` 被 GC → WebSocket 断开
3. 后端编译仍在继续（不受前端 WS 断开影响）
4. 用户切回"编译" Tab → `CompileTab` 重新挂载 → 所有 state 重置为初始值
5. 用户看到"一键编译"按钮可点击 → 再次点击可能创建第二个编译任务

### 修复方案

**方案 A：从父组件管理编译状态**

```tsx
// KnowledgeBaseDetail.tsx 中提升编译状态
function KnowledgeBaseDetail() {
  const [compiling, setCompiling] = useState(false)
  const [compileProgress, setCompileProgress] = useState<CompileProgress | null>(null)
  const compileWsRef = useRef<WebSocket | null>(null)

  // 启动编译（在父组件中）
  const startCompile = useCallback(() => {
    setCompiling(true)
    setCompileProgress({ type: 'status', phase: 'connecting', progress: 0, message: '连接中...' })
    const ws = new WebSocket(`${proto}//${host}/api/compile/ws/${kbId}`)
    compileWsRef.current = ws
    // ... WS handlers
  }, [kbId])

  // 传递给子组件
  {activeTab === 'compile' && (
    <CompileTab
      kbId={kbId!}
      compiling={compiling}
      compileProgress={compileProgress}
      onStartCompile={startCompile}
      onCompileDone={() => {/* refresh */}}
    />
  )}
}
```

**方案 B：Tab 切换时查询编译状态**

```tsx
function CompileTab({ kbId }: { kbId: string }) {
  const [compiling, setCompiling] = useState(false)
  const [compileProgress, setCompileProgress] = useState<CompileProgress | null>(null)

  // 组件挂载时检查编译状态
  useEffect(() => {
    fetch(`${API_BASE}/api/compile/${kbId}/status`)
      .then(r => r.json())
      .then(data => {
        if (data.status === 'processing') {
          // 后端仍在编译，重新连接 WS
          reconnectToCompile()
        }
      })
  }, [kbId])

  const reconnectToCompile = () => {
    // 重新建立 WS 连接
  }
}
```

> **推荐方案 A**，因为编译状态是整个 KB 的上下文，放在父组件更合理。
> **方案 B 更轻量**，如果不想大幅重构可以用。

---

## 问题 3：对话"连接中"卡住 + 消息不立即显示 + 无 Agent Loop

### 3.1 "连接中"卡住

**根因分析:**

```tsx
const sendWithWs = async (sessionId: string, content: string) => {
  setWsStatus('connecting')  // ← 设置为 connecting

  const ws = new WebSocket(...)
  let wsReceived = false  // ← 闭包变量

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.type === 'final_answer') {
      wsReceived = true  // ← 标记为已接收
      setMessages(prev => [...prev, { ... }])
      setWsStatus('idle')  // ← 重置状态
      setSending(false)
      ws.close()
    }
  }

  ws.onclose = () => {
    if (!wsReceived) {  // ← 如果 final_answer 未被处理
      setWsStatus('disconnected')  // ← 或保持 connecting
      // 启动 HTTP fallback 轮询
    }
  }
}
```

**可能的问题场景：**

1. **后端 WS 端点不发送 `final_answer`**：后端 `agent.run()` 可能只发送 `chunk` 事件，不发送 `final_answer`。WS 连接关闭后 `wsReceived=false`，`wsStatus` 变为 `disconnected`。

2. **WS 连接立即关闭**：如果后端 WS 端点 `/api/ws/sessions/{sessionId}` 在处理完请求后立即关闭连接（而不是保持长连接），前端会收到 `onclose`，此时 `wsReceived=false`。

3. **HTTP POST 成功但 WS 失败**：用户消息通过 HTTP POST 保存成功，但 WS 连接失败 → `wsStatus='disconnected'`，消息显示正常但后续交互失败。

### 修复方案

```tsx
const sendWithWs = async (sessionId: string, content: string) => {
  setSending(true)
  setStreamingContent('')
  setToolEvents([])
  setWsStatus('idle')

  // 1. 立即显示用户消息（乐观更新）
  const tempUserMsg: ChatMessage = {
    id: `temp_${Date.now()}`,
    role: 'user',
    content,
  }
  setMessages(prev => [...prev, tempUserMsg])

  // 2. 后台保存消息到数据库
  fetch(`${API_BASE}/api/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  }).catch(console.error)  // 不阻塞 UI

  // 3. 尝试 WebSocket
  try {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = location.host
    setWsStatus('connecting')
    const ws = new WebSocket(`${proto}//${host}/api/ws/sessions/${sessionId}`)

    let finalReceived = false
    let wsTimeout: ReturnType<typeof setTimeout>

    // 超时保护：30 秒后切换到 HTTP 轮询
    wsTimeout = setTimeout(() => {
      if (!finalReceived) {
        ws.close()
        setWsStatus('disconnected')
        startHttpPoll(sessionId)
      }
    }, 30000)

    ws.onopen = () => {
      setWsStatus('connected')
      ws.send(JSON.stringify({ content }))
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      switch (data.type) {
        case 'thinking':
          setToolEvents(prev => [...prev, data])
          break
        case 'tool_call':
          setToolEvents(prev => [...prev, data])
          break
        case 'chunk':
          setStreamingContent(prev => prev + data.content)
          break
        case 'final_answer':
          finalReceived = true
          clearTimeout(wsTimeout)
          setMessages(prev => {
            // 移除临时用户消息
            const filtered = prev.filter(m => !m.id.startsWith('temp_'))
            return [
              ...filtered,
              { id: `agent_${Date.now()}`, role: 'assistant', content: data.content },
            ]
          })
          setStreamingContent('')
          setToolEvents([])
          setWsStatus('idle')
          setSending(false)
          ws.close()
          break
        case 'error':
          finalReceived = true
          clearTimeout(wsTimeout)
          setMessages(prev => {
            const filtered = prev.filter(m => !m.id.startsWith('temp_'))
            return [...filtered, { id: `err_${Date.now()}`, role: 'assistant', content: `错误: ${data.content}` }]
          })
          setSending(false)
          ws.close()
          break
      }
    }

    ws.onclose = () => {
      clearTimeout(wsTimeout)
      if (!finalReceived) {
        setWsStatus('disconnected')
        startHttpPoll(sessionId)
      }
    }

    ws.onerror = () => {
      clearTimeout(wsTimeout)
      setWsStatus('disconnected')
    }
  } catch (e) {
    setWsStatus('disconnected')
  }
}

// HTTP 轮询 fallback
const startHttpPoll = (sessionId: string) => {
  let attempts = 0
  const maxAttempts = 20  // 60 秒
  const pollInterval = setInterval(async () => {
    attempts++
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`)
      if (res.ok) {
        const data = await res.json()
        if (Array.isArray(data) && data.some((m: ChatMessage) => m.role === 'assistant')) {
          setMessages(prev => {
            // 移除临时消息，替换为服务器数据
            const filtered = prev.filter(m => !m.id.startsWith('temp_'))
            return [...filtered, data[data.length - 1]]
          })
          setWsStatus('idle')
          setSending(false)
          clearInterval(pollInterval)
          return
        }
      }
    } catch (e) {}
    if (attempts >= maxAttempts) {
      clearInterval(pollInterval)
      setSending(false)
    }
  }, 3000)
}
```

### 3.2 消息不立即显示

**根因：** 当前逻辑是 `POST 保存 → GET 获取 → 更新 UI`。如果 GET 失败或延迟，用户消息不显示。

**修复方案：** 乐观更新（上面代码中已包含）。

### 3.3 无 Agent Loop 前端展示

**根因：** 取决于后端 Agent Loop 的事件流。检查后端代码：

```python
# backend/app/api/chat.py
@router.websocket("/ws/sessions/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    agent = _build_agent(kb_id, llm_client, router_obj)
    async for event in agent.run(user_query=content, kb_id=kb_id):
        await websocket.send_text(json.dumps(event))
```

后端 `agent.run()` 的 `event` 格式由 `backend/app/services/agent/loop.py` 决定。

**需要确认：** Agent Loop 是否 emit `thinking` 和 `tool_call` 事件？

**如果后端不发送这些事件，前端无法凭空展示。需要检查后端 Agent Loop 的实现。**

---

## 问题 4：文档状态应分离解析和编译

### 根因分析

当前文档列表只显示 `parse_status`（已解析/待解析）：

```tsx
<span className={`... ${doc.parse_status === 'completed' ? 'bg-green-100...' : 'bg-amber-100...'}`}>
  {doc.parse_status === 'completed' ? '已解析' : doc.parse_status}
</span>
```

但用户期望看到两个维度的状态：
1. **解析状态**（per document）：已解析 / 解析中 / 失败
2. **编译状态**（per KB）：待编译 / 已编译

### 修复方案

```tsx
function DocumentsTab({ kbId, onRefresh }: { kbId: string; onRefresh: () => void }) {
  const [docs, setDocs] = useState<DocInfo[]>([])
  const [kbCompileStatus, setKbCompileStatus] = useState<string>('pending')

  useEffect(() => {
    fetchDocs()
    // 获取 KB 编译状态
    fetch(`${API_BASE}/api/knowledge-bases`)
      .then(r => r.json())
      .then(data => {
        const kb = (Array.isArray(data) ? data : []).find((k: any) => k.id === kbId)
        if (kb) setKbCompileStatus(kb.compile_status)
      })
  }, [kbId])

  return (
    <div>
      {/* KB 编译状态 */}
      <div className="mb-4 flex items-center gap-2">
        <span className="text-sm text-stone-500">编译状态：</span>
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
          compileStatusMap[kbCompileStatus]?.color || 'bg-gray-100'
        }`}>
          {compileStatusMap[kbCompileStatus]?.label || kbCompileStatus}
        </span>
        {kbCompileStatus === 'completed' && (
          <span className="text-xs text-stone-400 ml-2">所有文档已编译</span>
        )}
      </div>

      {/* 文档列表 */}
      {docs.map((doc) => (
        <div key={doc.id} className="...">
          <div>
            <p>{doc.filename}</p>
            <p>{formatSize(doc.file_size)} · {typeLabels[doc.file_type]}</p>
          </div>
          <div className="flex items-center gap-2">
            {/* 解析状态 */}
            <span className={`px-2 py-0.5 rounded-full text-xs ${
              doc.parse_status === 'completed'
                ? 'bg-green-100 text-green-700'
                : 'bg-amber-100 text-amber-700'
            }`}>
              {doc.parse_status === 'completed' ? '已解析' : doc.parse_status}
            </span>
            {/* 编译状态 */}
            <span className={`px-2 py-0.5 rounded-full text-xs ${
              kbCompileStatus === 'completed'
                ? 'bg-blue-100 text-blue-700'
                : kbCompileStatus === 'processing'
                ? 'bg-yellow-100 text-yellow-700'
                : 'bg-stone-100 text-stone-500'
            }`}>
              {kbCompileStatus === 'completed' ? '已编译' :
               kbCompileStatus === 'processing' ? '编译中' : '待编译'}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
```

### 状态矩阵

| 解析状态 | 编译状态 | 显示效果 |
|---------|---------|---------|
| 已解析 | 待编译 | 🟢 已解析 + ⚪ 待编译 |
| 已解析 | 编译中 | 🟢 已解析 + 🟡 编译中 |
| 已解析 | 已完成 | 🟢 已解析 + 🔵 已编译 |
| 解析中 | 待编译 | 🟡 解析中 + ⚪ 待编译 |
| 失败 | - | 🔴 失败 |

---

## 问题 5：Wiki 需要总览页签

### 当前状态

Wiki Tab 只有两个子 Tab：
- 实体：按类型分组的实体列表 + 详情面板
- 时间线：时间线事件列表

### 修复方案

新增"总览" Tab，提供直观的可视化：

```tsx
function WikiTab({ kbId }: { kbId: string }) {
  return <EmbeddedWikiView kbId={kbId} />
}

function EmbeddedWikiView({ kbId }: { kbId: string }) {
  const [overview, setOverview] = useState<WikiOverview | null>(null)
  const [selectedEntity, setSelectedEntity] = useState<EntityDetail | null>(null)
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [activeTab, setActiveTab] = useState<'overview' | 'entities' | 'timeline'>('overview')
  // ...
}
```

### 总览页签设计

```tsx
{/* 总览 Tab */}
{activeTab === 'overview' && overview && overview.entity_count > 0 && (
  <div className="p-6 space-y-6">
    {/* 统计卡片 */}
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4">
        <p className="text-xs text-stone-500">实体总数</p>
        <p className="text-2xl font-bold text-stone-800 dark:text-stone-100">{overview.entity_count}</p>
      </div>
      <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4">
        <p className="text-xs text-stone-500">时间线事件</p>
        <p className="text-2xl font-bold text-stone-800 dark:text-stone-100">{overview.timeline_count}</p>
      </div>
      <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4">
        <p className="text-xs text-stone-500">实体类型</p>
        <p className="text-2xl font-bold text-stone-800 dark:text-stone-100">{Object.keys(overview.type_counts).length}</p>
      </div>
      <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4">
        <p className="text-xs text-stone-500">人物数量</p>
        <p className="text-2xl font-bold text-stone-800 dark:text-stone-100">{overview.type_counts.person || 0}</p>
      </div>
    </div>

    {/* 实体类型分布图 */}
    <div className="bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700 p-4">
      <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-3">实体类型分布</h3>
      <div className="space-y-2">
        {Object.entries(overview.type_counts).map(([type, count]) => {
          const percentage = Math.round((count / overview.entity_count) * 100)
          return (
            <div key={type} className="flex items-center gap-3">
              <span className="text-xs w-16 text-stone-500">{TYPE_ICONS[type] || '📋'} {TYPE_LABELS[type] || type}</span>
              <div className="flex-1 bg-stone-200 dark:bg-slate-700 rounded-full h-4 overflow-hidden">
                <div
                  className="h-full bg-amber-500 rounded-full transition-all"
                  style={{ width: `${percentage}%` }}
                />
              </div>
              <span className="text-xs text-stone-500 w-16 text-right">{count} ({percentage}%)</span>
            </div>
          )
        })}
      </div>
    </div>

    {/* 主要实体速览 */}
    <div className="bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700 p-4">
      <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-3">主要实体</h3>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {overview.entities.slice(0, 6).map(entity => (
          <button
            key={entity.id}
            onClick={() => { setActiveTab('entities'); fetchEntity(entity.id) }}
            className="flex items-center gap-2 p-3 bg-stone-50 dark:bg-slate-700/50 rounded-lg hover:bg-amber-50 dark:hover:bg-amber-900/20 transition-colors text-left"
          >
            <span className="text-lg">{TYPE_ICONS[entity.type] || '📋'}</span>
            <div>
              <p className="text-sm font-medium text-stone-700 dark:text-stone-300">{entity.name}</p>
              <p className="text-xs text-stone-400">{TYPE_LABELS[entity.type] || entity.type}</p>
            </div>
          </button>
        ))}
      </div>
    </div>

    {/* 最近时间线事件 */}
    {timeline.length > 0 && (
      <div className="bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700 p-4">
        <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-3">最近事件</h3>
        <div className="space-y-2">
          {timeline.slice(0, 3).map((ev, i) => (
            <div key={i} className="flex items-start gap-3 p-3 bg-stone-50 dark:bg-slate-700/50 rounded-lg">
              <div className="w-2 h-2 rounded-full bg-amber-400 mt-1.5"></div>
              <div>
                <p className="text-sm text-stone-700 dark:text-stone-300">{ev.title}</p>
                {ev.time && <p className="text-xs text-stone-400 font-mono">{ev.time}</p>}
              </div>
            </div>
          ))}
        </div>
      </div>
    )}
  </div>
)}
```

### 三个子 Tab 布局

```
┌──────────────────────────────────────┐
│ [总览] [实体] [时间线]               │
├──────────────┬───────────────────────┤
│              │                       │
│  总览:       │   统计卡片             │
│  - 统计卡片   │   类型分布条形图       │
│  - 分布图     │   主要实体速览         │
│  - 最近事件   │   最近时间线事件       │
│              │                       │
│  实体:       │   实体树 + 详情面板    │
│  时间线:     │   时间线列表 + 详情    │
│              │                       │
└──────────────┴───────────────────────┘
```

---

## 修改优先级

| 优先级 | 问题 | 预估工时 | 修改文件 |
|--------|------|---------|---------|
| P0 | 问题 1：侧边栏导航无反应 | 1h | Sidebar.tsx, App.tsx |
| P0 | 问题 3.2：消息不立即显示 | 1h | KnowledgeBaseDetail.tsx (ChatTab) |
| P0 | 问题 3.1："连接中"卡住 | 1.5h | KnowledgeBaseDetail.tsx (ChatTab) |
| P1 | 问题 3.3：Agent Loop 不展示 | 2h* | 后端 agent/loop.py + 前端 |
| P1 | 问题 2：编译 Tab 切换失效 | 2h | KnowledgeBaseDetail.tsx |
| P1 | 问题 4：文档状态分离 | 1h | KnowledgeBaseDetail.tsx (DocumentsTab) |
| P2 | 问题 5：Wiki 总览页签 | 2h | KnowledgeBaseDetail.tsx (WikiTab) |

> *问题 3.3 取决于后端 Agent Loop 是否 emit `thinking` 和 `tool_call` 事件。需要检查 `backend/app/services/agent/loop.py` 的实现。

---

## 给 Claude Code 的具体指令

### 第一轮修改（P0 — 立即修复）

```
请修复 SuperDeepAnalyze 以下 3 个问题：

1. 修复侧边栏导航（Sidebar.tsx）：
   - 图谱/对话/Wiki 点击后跳转到当前 KB 的详情页并激活对应 Tab
   - 如果没有选中 KB，跳转到知识库列表页
   - 使用 sessionStorage 传递 Tab 信息

2. 修复对话消息立即显示（KnowledgeBaseDetail.tsx ChatTab）：
   - 发送消息后立即在 UI 显示（乐观更新）
   - 后台异步保存到数据库
   - 如果 WS 失败，使用 HTTP 轮询获取结果

3. 修复"连接中"卡住：
   - 添加 30 秒超时保护
   - WS 断开后自动切换到 HTTP 轮询
   - 完成后正确重置 wsStatus 为 idle
```

### 第二轮修改（P1 — 功能增强）

```
请修复以下 2 个问题：

1. 修复编译 Tab 切换失效（KnowledgeBaseDetail.tsx）：
   - 方案：Tab 切换时查询编译状态 API
   - 如果后端仍在编译，重新连接 WebSocket 或显示"编译进行中"状态
   - 编译完成后自动刷新 KB 信息

2. 分离文档解析和编译状态（KnowledgeBaseDetail.tsx DocumentsTab）：
   - 每个文档显示两个标签：解析状态 + 编译状态
   - 解析状态：已解析 / 解析中 / 失败
   - 编译状态：待编译 / 编译中 / 已编译（继承 KB 的 compile_status）
```

### 第三轮修改（P2 — 体验优化）

```
请添加 Wiki 总览页签（KnowledgeBaseDetail.tsx WikiTab）：

1. 新增"总览" Tab（默认激活）
2. 统计卡片：实体总数、时间线事件数、实体类型数、人物数
3. 实体类型分布：水平条形图显示各类型占比
4. 主要实体速览：前 6 个实体，点击跳转到实体详情
5. 最近事件：前 3 个时间线事件
```

---

*本报告由凤歌（OpenClaw）通过代码审查整理*
