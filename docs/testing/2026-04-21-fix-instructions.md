# SuperDeepAnalyze - Claude Code 修复指令

> **日期:** 2026-04-21
> **来源:** 用户实测 5 个问题 + 凤歌代码审查
> **文件:** `frontend/src/components/pages/KnowledgeBaseDetail.tsx` + `Sidebar.tsx` + `App.tsx`

---

## 修复任务清单

### 任务 1：修复侧边栏导航（Sidebar.tsx）

**文件：** `frontend/src/components/Sidebar.tsx`

**问题：** 图谱、对话、Wiki 点击没有反应或跳转到旧版独立页面。

**修复：** 让侧边栏导航跳转到当前 KB 的详情页并预激活对应 Tab。

```tsx
import { NavLink, useNavigate } from 'react-router-dom'
import { useAppStore } from '../store/app'

// 替换原来的 navItems
function Sidebar() {
  const navigate = useNavigate()
  const { currentKbId, toggleSidebar } = useAppStore()

  const handleDetailNav = (tab: string, e: React.MouseEvent) => {
    e.preventDefault()
    if (currentKbId) {
      // 保存目标 Tab 到 sessionStorage
      sessionStorage.setItem('activeTab', tab)
      navigate(`/knowledge/${currentKbId}`)
    } else {
      navigate('/knowledge')
    }
  }

  return (
    <aside className="w-56 bg-white dark:bg-slate-800 border-r border-stone-200 dark:border-slate-700 flex flex-col">
      {/* Logo 区域 */}
      <div className="p-4 border-b border-stone-200 dark:border-slate-700 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-stone-800 dark:text-stone-100">SDA</h2>
          <p className="text-xs text-stone-400 dark:text-stone-500">SuperDeepAnalyze</p>
        </div>
        <button onClick={toggleSidebar} className="...">切换主题</button>
      </div>

      {/* 当前知识库 */}
      {currentKbId && (
        <div className="px-4 py-2 border-b border-stone-200 dark:border-slate-700">
          <p className="text-xs text-stone-400 dark:text-stone-500">当前知识库</p>
          <button
            onClick={() => navigate(`/knowledge/${currentKbId}`)}
            className="text-sm text-amber-600 dark:text-amber-400 hover:underline truncate w-full text-left"
          >
            {currentKbId}
          </button>
        </div>
      )}

      <nav className="flex-1 p-3 space-y-1">
        <NavLink to="/" className="...">🏠 首页</NavLink>
        <NavLink to="/knowledge" className="...">📁 知识库</NavLink>

        {/* 功能导航 → 跳转到详情页 */}
        <a
          href="#"
          onClick={(e) => handleDetailNav('graph', e)}
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-slate-700"
        >
          <span>🕸️</span><span>图谱</span>
        </a>
        <a
          href="#"
          onClick={(e) => handleDetailNav('chat', e)}
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-slate-700"
        >
          <span>💬</span><span>对话</span>
        </a>
        <a
          href="#"
          onClick={(e) => handleDetailNav('wiki', e)}
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-slate-700"
        >
          <span>📖</span><span>Wiki</span>
        </a>

        <NavLink to="/settings" className="...">⚙️ 设置</NavLink>
      </nav>
    </aside>
  )
}
```

同时在 `KnowledgeBaseDetail.tsx` 中读取 sessionStorage：

```tsx
// KnowledgeBaseDetail.tsx 的 useEffect 中添加
useEffect(() => {
  if (!kbId) return
  fetch(`${API_BASE}/api/knowledge-bases`)
    .then(r => r.json())
    .then(data => {
      const kb = (Array.isArray(data) ? data : []).find((k: any) => k.id === kbId)
      if (kb) {
        setKbInfo({
          name: kb.name,
          description: kb.description,
          compile_status: kb.compile_status,
          document_count: kb.document_count,
        })
        setCurrentKb(kb.id, kb.name)
      }
      setLoading(false)
    })
    .catch(() => setLoading(false))

  // 读取预设置的 Tab
  const savedTab = sessionStorage.getItem('activeTab')
  if (savedTab && ['documents', 'compile', 'wiki', 'graph', 'chat'].includes(savedTab)) {
    setActiveTab(savedTab as TabType)
    sessionStorage.removeItem('activeTab')
  }
}, [kbId])
```

---

### 任务 2：修复对话消息不立即显示 + "连接中"卡住

**文件：** `KnowledgeBaseDetail.tsx` → `EmbeddedChatView` 组件

**修改 `sendWithWs` 函数：**

1. 发送后立即显示用户消息（乐观更新）
2. 后台异步保存到数据库
3. 添加 30 秒 WS 超时保护
4. WS 失败时自动切换到 HTTP 轮询
5. 完成后正确重置 `wsStatus`

```tsx
const sendWithWs = async (sessionId: string, content: string) => {
  setSending(true)
  setStreamingContent('')
  setToolEvents([])

  // 1. 乐观显示用户消息
  const tempId = `temp_${Date.now()}`
  setMessages(prev => [...prev, { id: tempId, role: 'user' as const, content }])

  // 2. 后台保存（不阻塞 UI）
  fetch(`${API_BASE}/api/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  }).catch(console.error)

  try {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = location.host
    setWsStatus('connecting')
    const ws = new WebSocket(`${proto}//${host}/api/ws/sessions/${sessionId}`)
    wsRef.current = ws

    let finalReceived = false
    const wsTimeout = setTimeout(() => {
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
      try {
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
              const filtered = prev.filter(m => !m.id.startsWith('temp_'))
              return [...filtered, { id: `agent_${Date.now()}`, role: 'assistant' as const, content: data.content }]
            })
            setStreamingContent('')
            setToolEvents([])
            setWsStatus('idle')
            setSending(false)
            // 自动生成标题
            fetch(`${API_BASE}/api/sessions/${sessionId}/title`, { method: 'PUT' })
              .then(r => r.json())
              .then(d => {
                setSessions(prev => prev.map(s => s.id === sessionId ? { ...s, title: d.title } : s))
              })
              .catch(console.error)
            ws.close()
            break
          case 'error':
            finalReceived = true
            clearTimeout(wsTimeout)
            setMessages(prev => {
              const filtered = prev.filter(m => !m.id.startsWith('temp_'))
              return [...filtered, { id: `err_${Date.now()}`, role: 'assistant' as const, content: `错误: ${data.content}` }]
            })
            setSending(false)
            setWsStatus('idle')
            ws.close()
            break
        }
      } catch (e) {
        console.error('Failed to parse WS message:', e)
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
        const assistantMsg = Array.isArray(data) ? data.find((m: ChatMessage) => m.role === 'assistant') : null
        if (assistantMsg) {
          setMessages(prev => {
            const filtered = prev.filter(m => !m.id.startsWith('temp_'))
            return [...filtered, assistantMsg]
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
      // 移除临时消息
      setMessages(prev => prev.filter(m => !m.id.startsWith('temp_')))
    }
  }, 3000)
}
```

**修改 `sendMessage` 函数（新建会话时）：**

```tsx
const sendMessage = async () => {
  if (!input.trim() || sending) return

  const messageContent = input.trim()
  setInput('')  // 立即清空输入框

  if (!currentSession) {
    // 创建新会话
    try {
      const res = await fetch(`${API_BASE}/api/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kb_id: kbId, title: messageContent.slice(0, 20) }),
      })
      if (res.ok) {
        const data = await res.json()
        setSessions(prev => [data, ...prev])
        setCurrentSession(data.id)
        setMessages([])
        sendWithWs(data.id, messageContent)
      }
    } catch (e) {
      console.error('Failed to create session:', e)
      setSending(false)
    }
    return
  }

  sendWithWs(currentSession, messageContent)
}
```

**修改新建会话时的消息清空逻辑：**

```tsx
const createSession = async () => {
  try {
    const res = await fetch(`${API_BASE}/api/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kb_id: kbId, title: '新对话' }),
    })
    if (res.ok) {
      const data = await res.json()
      setSessions(prev => [data, ...prev])
      setCurrentSession(data.id)
      setMessages([])  // 新会话，清空消息
    }
  } catch (e) {
    console.error('Failed to create session:', e)
  }
}
```

---

### 任务 3：修复编译 Tab 切换失效

**文件：** `KnowledgeBaseDetail.tsx` → `CompileTab` 组件

**修改方案：组件挂载时检查编译状态**

```tsx
function CompileTab({ kbId, onCompileDone }: { kbId: string; onCompileDone?: () => void }) {
  const [compiling, setCompiling] = useState(false)
  const [compileProgress, setCompileProgress] = useState<CompileProgress | null>(null)
  const [compileResult, setCompileResult] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // 组件挂载时检查编译状态
  useEffect(() => {
    fetch(`${API_BASE}/api/compile/${kbId}/status`)
      .then(r => r.json())
      .then(data => {
        if (data.status === 'processing') {
          // 后端仍在编译，重新连接
          reconnectToCompile()
        } else if (data.status === 'completed') {
          setCompileResult('编译已完成')
        } else if (data.status === 'failed') {
          setCompileResult('上次编译失败，请重试')
        }
      })
      .catch(console.error)
  }, [kbId])

  const reconnectToCompile = () => {
    setCompiling(true)
    setCompileProgress({ type: 'status', phase: 'connecting', progress: 0, message: '重新连接...' })

    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = location.host
    const ws = new WebSocket(`${proto}//${host}/api/compile/ws/${kbId}`)
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setCompileProgress(data)
        if (data.type === 'done') {
          setCompiling(false)
          const stats = data.stats || {}
          setCompileResult(`编译完成! ${stats.documents_processed || 0} 文档处理, ${stats.chunks_generated || 0} chunks`)
          onCompileDone?.()
          ws.close()
        } else if (data.type === 'error') {
          setCompiling(false)
          setCompileResult(`编译失败: ${data.message}`)
          ws.close()
        }
      } catch (e) {
        console.error('Failed to parse compile WS message:', e)
      }
    }

    ws.onclose = () => { setCompiling(false) }
    ws.onerror = () => { setCompiling(false); setCompileResult('编译连接失败，请重试') }
  }

  const handleCompile = async () => {
    setCompiling(true)
    setCompileProgress({ type: 'status', phase: 'connecting', progress: 0, message: '连接中...' })
    setCompileResult(null)

    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = location.host
    const ws = new WebSocket(`${proto}//${host}/api/compile/ws/${kbId}`)
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setCompileProgress(data)
        if (data.type === 'done') {
          setCompiling(false)
          const stats = data.stats || {}
          setCompileResult(`编译完成! ${stats.documents_processed || 0} 文档处理, ${stats.documents_skipped || 0} 跳过, ${stats.chunks_generated || 0} chunks, ${stats.l1_summaries || 0} L1 摘要`)
          onCompileDone?.()
          ws.close()
        } else if (data.type === 'error') {
          setCompiling(false)
          setCompileResult(`编译失败: ${data.message}`)
          ws.close()
        }
      } catch (e) {
        console.error('Failed to parse compile WS message:', e)
      }
    }

    ws.onclose = () => { setCompiling(false) }
    ws.onerror = () => { setCompiling(false); setCompileResult('编译连接失败，请重试') }
  }

  // ... render (保持不变)
}
```

---

### 任务 4：分离文档解析和编译状态

**文件：** `KnowledgeBaseDetail.tsx` → `DocumentsTab` 组件

**修改文档列表渲染：**

```tsx
function DocumentsTab({ kbId, onRefresh }: { kbId: string; onRefresh: () => void }) {
  const [docs, setDocs] = useState<DocInfo[]>([])
  const [kbCompileStatus, setKbCompileStatus] = useState<string>('pending')
  // ... existing state and functions

  // 获取 KB 编译状态
  useEffect(() => {
    fetchDocs()
    fetch(`${API_BASE}/api/knowledge-bases`)
      .then(r => r.json())
      .then(data => {
        const kb = (Array.isArray(data) ? data : []).find((k: any) => k.id === kbId)
        if (kb) setKbCompileStatus(kb.compile_status)
      })
      .catch(console.error)
  }, [kbId])

  const compileStatusLabels: Record<string, { label: string; color: string }> = {
    pending: { label: '待编译', color: 'bg-stone-100 text-stone-500 dark:bg-stone-700 dark:text-stone-400' },
    processing: { label: '编译中', color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' },
    completed: { label: '已编译', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' },
    failed: { label: '编译失败', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
    partial: { label: '部分编译', color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' },
  }

  return (
    <div className="h-full overflow-y-auto">
      {/* KB 编译状态 */}
      <div className="mb-4 flex items-center gap-3 p-3 bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700">
        <span className="text-sm text-stone-500 dark:text-stone-400">知识库编译状态：</span>
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${compileStatusLabels[kbCompileStatus]?.color || 'bg-gray-100'}`}>
          {compileStatusLabels[kbCompileStatus]?.label || kbCompileStatus}
        </span>
      </div>

      {/* Upload area (保持不变) */}
      {/* ... */}

      {/* Document list */}
      <div className="space-y-2">
        {docs.length === 0 && <p className="text-sm text-stone-400 dark:text-stone-500 text-center py-8">暂无文档，请上传</p>}
        {docs.map((doc) => (
          <div key={doc.id} className="flex items-center justify-between p-3 bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700">
            <div className="flex items-center gap-3">
              <span className="text-lg">{doc.file_type === 'pdf' ? '📕' : doc.file_type === 'docx' ? '📘' : '📄'}</span>
              <div>
                <p className="text-sm font-medium text-stone-800 dark:text-stone-100">{doc.filename}</p>
                <p className="text-xs text-stone-400 dark:text-stone-500">{formatSize(doc.file_size)} · {typeLabels[doc.file_type] || doc.file_type} · {new Date(doc.created_at).toLocaleDateString('zh-CN')}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {/* 解析状态 */}
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                doc.parse_status === 'completed'
                  ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                  : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
              }`}>
                {doc.parse_status === 'completed' ? '已解析' : doc.parse_status}
              </span>
              {/* 编译状态 */}
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${compileStatusLabels[kbCompileStatus]?.color || 'bg-gray-100'}`}>
                {compileStatusLabels[kbCompileStatus]?.label || kbCompileStatus}
              </span>
              {/* 删除按钮 */}
              <button onClick={() => handleDeleteDoc(doc.id)} className="p-1.5 text-stone-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors" title="删除">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
```

---

### 任务 5：Wiki 总览页签

**文件：** `KnowledgeBaseDetail.tsx` → `EmbeddedWikiView` 组件

**添加"总览" Tab：**

```tsx
function EmbeddedWikiView({ kbId }: { kbId: string }) {
  const [overview, setOverview] = useState<WikiOverview | null>(null)
  const [selectedEntity, setSelectedEntity] = useState<EntityDetail | null>(null)
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [activeTab, setActiveTab] = useState<'overview' | 'entities' | 'timeline'>('overview')  // 默认总览
  const [loading, setLoading] = useState(false)
  const [entityLoading, setEntityLoading] = useState(false)
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set())

  useEffect(() => {
    fetchWiki()
    fetchTimeline()
  }, [kbId])

  // ... existing fetch functions

  return (
    <div className="h-full flex gap-4 min-h-0">
      {/* 左侧面板 */}
      <div className="w-72 bg-white dark:bg-slate-800 rounded-xl border border-stone-200 dark:border-slate-700 flex flex-col overflow-hidden">
        {/* 三个 Tab 按钮 */}
        <div className="flex border-b border-stone-200 dark:border-slate-700">
          <button onClick={() => { setActiveTab('overview'); setSelectedEntity(null) }} className={`flex-1 px-3 py-2.5 text-xs font-medium transition-colors ${activeTab === 'overview' ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-b-2 border-amber-500' : 'text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'}`}>总览</button>
          <button onClick={() => { setActiveTab('entities'); setSelectedEntity(null) }} className={`flex-1 px-3 py-2.5 text-xs font-medium transition-colors ${activeTab === 'entities' ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-b-2 border-amber-500' : 'text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'}`}>实体</button>
          <button onClick={() => { setActiveTab('timeline'); setSelectedEntity(null) }} className={`flex-1 px-3 py-2.5 text-xs font-medium transition-colors ${activeTab === 'timeline' ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-b-2 border-amber-500' : 'text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'}`}>时间线</button>
        </div>

        {/* Tab 内容 */}
        <div className="flex-1 overflow-y-auto p-2">
          {activeTab === 'overview' && overview && overview.entity_count > 0 && (
            <div className="space-y-3">
              <div className="text-xs text-stone-500 dark:text-stone-400 text-center pb-2 border-b border-stone-200 dark:border-slate-700">
                {overview.entity_count} 实体 · {overview.timeline_count} 事件 · {Object.keys(overview.type_counts).length} 类型
              </div>
              {Object.entries(overview.type_counts).map(([type, count]) => (
                <button
                  key={type}
                  onClick={() => { setActiveTab('entities'); setFilterType(type) }}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-stone-600 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700 transition-colors"
                >
                  <span>{TYPE_ICONS[type] || '📋'}</span>
                  <span className="flex-1 text-left">{TYPE_LABELS[type] || type}</span>
                  <span className="text-stone-400 dark:text-stone-500">{count}</span>
                </button>
              ))}
              {timeline.length > 0 && (
                <div className="pt-2 border-t border-stone-200 dark:border-slate-700">
                  <p className="text-xs font-medium text-stone-500 dark:text-stone-400 mb-1">最近事件</p>
                  {timeline.slice(0, 3).map((ev, i) => (
                    <div key={i} className="px-3 py-1.5 text-xs text-stone-600 dark:text-stone-400">
                      <p className="truncate">{ev.title}</p>
                      {ev.time && <p className="text-stone-400 dark:text-stone-500 font-mono">{ev.time}</p>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {activeTab === 'overview' && (!overview || overview.entity_count === 0) && (
            <p className="text-xs text-stone-400 dark:text-stone-500 text-center py-8">暂无 Wiki 数据，请先编译</p>
          )}

          {/* 实体 Tab 内容（保持不变） */}
          {activeTab === 'entities' && /* existing entity tree */}

          {/* 时间线 Tab 内容（保持不变） */}
          {activeTab === 'timeline' && /* existing timeline */}
        </div>
      </div>

      {/* 右侧详情面板 */}
      <div className="flex-1 bg-white dark:bg-slate-800 rounded-xl border border-stone-200 dark:border-slate-700 overflow-y-auto">
        {activeTab === 'overview' && overview && overview.entity_count > 0 && (
          <div className="p-6 space-y-6">
            {/* 统计卡片 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4">
                <p className="text-xs text-stone-500 dark:text-stone-400">实体总数</p>
                <p className="text-2xl font-bold text-stone-800 dark:text-stone-100">{overview.entity_count}</p>
              </div>
              <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4">
                <p className="text-xs text-stone-500 dark:text-stone-400">时间线事件</p>
                <p className="text-2xl font-bold text-stone-800 dark:text-stone-100">{overview.timeline_count}</p>
              </div>
              <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4">
                <p className="text-xs text-stone-500 dark:text-stone-400">实体类型</p>
                <p className="text-2xl font-bold text-stone-800 dark:text-stone-100">{Object.keys(overview.type_counts).length}</p>
              </div>
              <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4">
                <p className="text-xs text-stone-500 dark:text-stone-400">人物</p>
                <p className="text-2xl font-bold text-stone-800 dark:text-stone-100">{overview.type_counts.person || 0}</p>
              </div>
            </div>

            {/* 实体类型分布 */}
            <div className="bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700 p-4">
              <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-3">实体类型分布</h3>
              <div className="space-y-2">
                {Object.entries(overview.type_counts).map(([type, count]) => {
                  const percentage = Math.round((count / overview.entity_count) * 100)
                  return (
                    <div key={type} className="flex items-center gap-3">
                      <span className="text-xs w-20 text-stone-500 dark:text-stone-400">{TYPE_ICONS[type] || '📋'} {TYPE_LABELS[type] || type}</span>
                      <div className="flex-1 bg-stone-200 dark:bg-slate-700 rounded-full h-4 overflow-hidden">
                        <div className="h-full bg-amber-500 rounded-full transition-all" style={{ width: `${percentage}%` }} />
                      </div>
                      <span className="text-xs text-stone-500 dark:text-stone-400 w-20 text-right">{count} ({percentage}%)</span>
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
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-stone-700 dark:text-stone-300 truncate">{entity.name}</p>
                      <p className="text-xs text-stone-400 dark:text-stone-500">{TYPE_LABELS[entity.type] || entity.type}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* 最近事件 */}
            {timeline.length > 0 && (
              <div className="bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700 p-4">
                <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-3">最近事件</h3>
                <div className="space-y-2">
                  {timeline.slice(0, 5).map((ev, i) => (
                    <div key={i} className="flex items-start gap-3 p-3 bg-stone-50 dark:bg-slate-700/50 rounded-lg">
                      <div className="w-2 h-2 rounded-full bg-amber-400 dark:bg-amber-600 mt-1.5 flex-shrink-0"></div>
                      <div className="min-w-0">
                        <p className="text-sm text-stone-700 dark:text-stone-300">{ev.title}</p>
                        {ev.time && <p className="text-xs text-stone-400 dark:text-stone-500 font-mono">{ev.time}</p>}
                        {ev.description && <p className="text-xs text-stone-500 dark:text-stone-400 mt-0.5 line-clamp-2">{ev.description}</p>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 实体详情（保持不变） */}
        {!entityLoading && activeTab === 'entities' && !selectedEntity && /* existing */}
        {!entityLoading && selectedEntity && /* existing */}

        {/* 时间线详情（保持不变） */}
        {activeTab === 'timeline' && /* existing */}
      </div>
    </div>
  )
}
```

---

## 修复优先级

| 优先级 | 任务 | 预估时间 | 涉及文件 |
|--------|------|---------|---------|
| P0 | 任务 1：侧边栏导航 | 30min | Sidebar.tsx, KnowledgeBaseDetail.tsx |
| P0 | 任务 2：对话消息 + WS | 1h | KnowledgeBaseDetail.tsx (ChatTab) |
| P1 | 任务 3：编译 Tab 恢复 | 30min | KnowledgeBaseDetail.tsx (CompileTab) |
| P1 | 任务 4：文档状态分离 | 30min | KnowledgeBaseDetail.tsx (DocumentsTab) |
| P2 | 任务 5：Wiki 总览 | 1h | KnowledgeBaseDetail.tsx (WikiTab) |

---

*请直接按照以上指令修改代码，完成后通知凤歌进行测试验证。*
