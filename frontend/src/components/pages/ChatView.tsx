import { useState, useEffect, useRef } from 'react'
import { useAppStore } from '../../store/app'
import { SearchIcon, DatabaseIcon, FileTextIcon, DocumentIcon, ExternalLinkIcon, ClockIcon, SettingsIcon, ChatIcon } from '../Icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const API_BASE = import.meta.env.VITE_API_BASE || ''

interface KB {
  id: string
  name: string
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at?: string
}

interface ToolEvent {
  type: string
  content?: string
  tool?: string
  input?: Record<string, unknown>
  output?: string
  duration?: number
  iteration?: number
  max_iterations?: number
  tool_calls_count?: number
  token_usage?: number
  token_limit?: number
  action?: string
}

const TOOL_ICON_MAP: Record<string, React.ComponentType<{className?: string}>> = {
  search_vector: SearchIcon,
  search_keyword: SearchIcon,
  read_l0: DatabaseIcon,
  read_l1: FileTextIcon,
  read_l2: DocumentIcon,
  expand_entity: ExternalLinkIcon,
  get_timeline: ClockIcon,
}

const TOOL_LABELS: Record<string, string> = {
  search_vector: '向量搜索',
  search_keyword: '关键词搜索',
  read_l0: '读取 L0 全局',
  read_l1: '读取 L1 摘要',
  read_l2: '读取 L2 原文',
  expand_entity: '展开实体链',
  get_timeline: '查询时间线',
}

function ToolCallCard({ event }: { event: ToolEvent }) {
  const [expanded, setExpanded] = useState(false)
  const IconComp = TOOL_ICON_MAP[event.tool || ''] || SettingsIcon
  const label = TOOL_LABELS[event.tool || ''] || event.tool || '未知工具'
  const inputPreview = event.input ? JSON.stringify(event.input).slice(0, 80) : ''
  const outputPreview = (event.output || '').slice(0, 100)

  return (
    <div className="border-l-2 border-amber-400 pl-3 py-1.5">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-xs text-stone-600 dark:text-stone-400 hover:text-amber-600 dark:hover:text-amber-400 transition-colors w-full text-left"
      >
        <IconComp className="w-4 h-4" />
        <span className="font-medium">{label}</span>
        {event.duration && (
          <span className="text-stone-400 dark:text-stone-500 ml-auto">{event.duration}s</span>
        )}
        <span className={`text-stone-400 ml-auto transition-transform ${expanded ? 'rotate-90' : ''}`}>
          ▸
        </span>
      </button>
      {expanded && (
        <div className="mt-2 space-y-1 text-xs">
          {inputPreview && (
            <div className="bg-stone-100 dark:bg-slate-700 rounded px-2 py-1.5">
              <span className="text-stone-500 dark:text-stone-400">输入：</span>
              <code className="text-stone-700 dark:text-stone-300">{inputPreview}</code>
            </div>
          )}
          {outputPreview && (
            <div className="bg-stone-100 dark:bg-slate-700 rounded px-2 py-1.5">
              <span className="text-stone-500 dark:text-stone-400">输出：</span>
              <p className="text-stone-700 dark:text-stone-300 mt-1 whitespace-pre-wrap">{outputPreview}{(event.output || '').length > 100 ? '...' : ''}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function ChatView() {
  const { currentKbId, setCurrentKbId } = useAppStore()
  const [kbs, setKbs] = useState<KB[]>([])
  const [sessions, setSessions] = useState<{ id: string; title: string }[]>([])
  const [currentSession, setCurrentSession] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [toolEvents, setToolEvents] = useState<ToolEvent[]>([])
  const [wsStatus, setWsStatus] = useState<'idle' | 'connecting' | 'connected' | 'disconnected'>('idle')
  const [agentProgress, setAgentProgress] = useState<{ iteration: number; max: number; tools: number } | null>(null)
  const [contextUsage, setContextUsage] = useState<{ percent: number; action: string } | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/knowledge-bases`)
      .then(r => r.json())
      .then(data => {
        setKbs(Array.isArray(data) ? data : [])
        if (!currentKbId && data.length > 0) setCurrentKbId(data[0].id)
      })
      .catch(console.error)
  }, [])

  useEffect(() => {
    if (currentKbId) fetchSessions()
  }, [currentKbId])

  useEffect(() => {
    if (currentSession) fetchMessages()
  }, [currentSession])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent, toolEvents])

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [])

  const fetchSessions = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${currentKbId}`)
      if (res.ok) {
        const data = await res.json()
        setSessions(Array.isArray(data) ? data : [])
      }
    } catch (e) {
      console.error('Failed to fetch sessions:', e)
    }
  }

  const fetchMessages = async () => {
    if (!currentSession) return
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${currentSession}/messages`)
      if (res.ok) {
        const data = await res.json()
        setMessages(Array.isArray(data) ? data : [])
      }
    } catch (e) {
      console.error('Failed to fetch messages:', e)
    }
  }

  const createSession = async () => {
    if (!currentKbId) return
    try {
      const res = await fetch(`${API_BASE}/api/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kb_id: currentKbId, title: '新对话' }),
      })
      if (res.ok) {
        const data = await res.json()
        setSessions((prev) => [data, ...prev])
        setCurrentSession(data.id)
        setMessages([])
      }
    } catch (e) {
      console.error('Failed to create session:', e)
    }
  }

  const deleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('确定删除此会话？')) return
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, { method: 'DELETE' })
      if (res.ok || res.status === 204) {
        setSessions((prev) => prev.filter((s) => s.id !== sessionId))
        if (currentSession === sessionId) setCurrentSession(null)
      }
    } catch (e) {
      console.error('Failed to delete session:', e)
    }
  }

  const sendWithWs = async (sessionId: string, content: string) => {
    setSending(true)
    setStreamingContent('')
    setToolEvents([])
    setAgentProgress(null)
    setContextUsage(null)
    setWsStatus('idle')

    const userMsgId = `umsg_${Date.now()}`
    setMessages((prev) => [...prev, { id: userMsgId, role: 'user', content }])

    try {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const host = location.host
      setWsStatus('connecting')
      const ws = new WebSocket(`${proto}//${host}/api/ws/sessions/${sessionId}`)
      wsRef.current = ws

      let finalReceived = false

      const wsTimeout = setTimeout(() => {
        if (!finalReceived) { ws.close(); setWsStatus('disconnected'); startHttpPoll(sessionId) }
      }, 60000)

      ws.onopen = () => {
        setWsStatus('connected')
        ws.send(JSON.stringify({ content }))
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          switch (data.type) {
            case 'thinking':
            case 'tool_call':
              setToolEvents((prev) => [...prev, data])
              break
            case 'progress':
              setAgentProgress({
                iteration: data.iteration || 0,
                max: data.max_iterations || 15,
                tools: data.tool_calls_count || 0,
              })
              break
            case 'context_update':
              setContextUsage({
                percent: data.token_limit ? Math.round((data.token_usage / data.token_limit) * 100) : 0,
                action: data.action || '',
              })
              break
            case 'chunk':
              setStreamingContent((prev) => prev + data.content)
              break
            case 'final_answer':
              finalReceived = true; clearTimeout(wsTimeout)
              setAgentProgress(null); setStreamingContent(''); setToolEvents([])
              setWsStatus('idle'); setSending(false)
              ws.close()
              fetch(`${API_BASE}/api/sessions/${sessionId}/messages`).then(r => r.json()).then(d => {
                setMessages(Array.isArray(d) ? d : [])
              }).catch(() => {
                setMessages(prev => [...prev, { id: `agent_${Date.now()}`, role: 'assistant', content: data.content }])
              })
              fetch(`${API_BASE}/api/sessions/${sessionId}/title`, { method: 'PUT' })
                .then(r => r.ok ? r.json() : null)
                .then(d => { if (d) setSessions(prev => prev.map(s => s.id === sessionId ? { ...s, title: d.title } : s)) })
                .catch(console.error)
              break
            case 'error':
              finalReceived = true; clearTimeout(wsTimeout)
              setMessages((prev) => [...prev, { id: `err_${Date.now()}`, role: 'assistant', content: `错误: ${data.content}` }])
              setStreamingContent(''); setToolEvents([])
              setSending(false); setWsStatus('idle'); ws.close()
              break
          }
        } catch (e) {
          console.error('Failed to parse WS message:', e)
        }
      }

      ws.onclose = () => { clearTimeout(wsTimeout); if (!finalReceived) { setWsStatus('disconnected'); startHttpPoll(sessionId) } }
      ws.onerror = () => { clearTimeout(wsTimeout); setWsStatus('disconnected') }
    } catch (e) {
      setWsStatus('disconnected'); setSending(false)
    }
  }

  const startHttpPoll = (sessionId: string) => {
    let attempts = 0; const maxAttempts = 20
    const pollInterval = setInterval(async () => {
      attempts++
      try {
        const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`)
        if (res.ok) {
          const data = await res.json()
          const msgs = Array.isArray(data) ? data : []
          const hasAssistant = msgs.some((m: Message) => m.role === 'assistant')
          if (hasAssistant) { setMessages(msgs); setWsStatus('idle'); setSending(false); clearInterval(pollInterval); return }
        }
      } catch (e) {}
      if (attempts >= maxAttempts) { clearInterval(pollInterval); setSending(false) }
    }, 3000)
  }

  const sendMessage = async () => {
    if (!input.trim() || sending) return
    if (!currentSession) {
      if (!currentKbId) return
      setSending(true)
      try {
        const res = await fetch(`${API_BASE}/api/sessions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ kb_id: currentKbId, title: '新对话' }),
        })
        if (res.ok) {
          const data = await res.json()
          setSessions((prev) => [data, ...prev])
          setCurrentSession(data.id)
          setMessages([])
          sendWithWs(data.id, input.trim())
        }
      } catch (e) {
        console.error('Failed to create session:', e)
        setSending(false)
      }
      setInput('')
      return
    }
    sendWithWs(currentSession, input.trim())
    setInput('')
  }

  if (kbs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <ChatIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
        <p className="text-stone-600 dark:text-stone-300 font-medium">暂无知识库，请先创建</p>
      </div>
    )
  }

  if (!currentKbId) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <ChatIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
        <p className="text-stone-600 dark:text-stone-300 font-medium mb-4">选择知识库开始对话</p>
        <select
          value=""
          onChange={(e) => setCurrentKbId(e.target.value)}
          className="px-4 py-2 rounded-lg border border-stone-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-stone-800 dark:text-stone-100 text-sm"
        >
          <option value="">请选择...</option>
          {kbs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
        </select>
      </div>
    )
  }

  return (
    <div className="h-full flex">
      <div className="w-56 border-r border-stone-200 dark:border-slate-700 flex flex-col bg-white/50 dark:bg-slate-800/50">
        <div className="p-3 border-b border-stone-200 dark:border-slate-700 flex items-center justify-between gap-2">
          <select
            value={currentKbId}
            onChange={(e) => { setCurrentKbId(e.target.value); setCurrentSession(null) }}
            className="flex-1 px-2 py-1.5 rounded-lg border border-stone-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-stone-800 dark:text-stone-100 text-xs truncate"
          >
            {kbs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
          </select>
          <button
            onClick={createSession}
            className="px-2 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-medium transition-colors"
          >
            +
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`group flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs transition-colors ${
                currentSession === s.id
                  ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 font-medium'
                  : 'text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-slate-700'
              }`}
            >
              <button
                onClick={() => setCurrentSession(s.id)}
                className="flex-1 text-left truncate"
              >
                <p className="truncate">{s.title}</p>
                <p className="text-stone-400 dark:text-stone-500 mt-0.5 font-mono">{s.id.slice(0, 12)}</p>
              </button>
              <button
                onClick={(e) => deleteSession(s.id, e)}
                className="opacity-0 group-hover:opacity-100 p-1 text-stone-400 hover:text-red-500 transition-opacity"
                title="删除会话"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 flex flex-col min-w-0">
        {currentSession ? (
          <>
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* Connection status indicator */}
              {wsStatus === 'connecting' && (
                <div className="flex justify-center">
                  <div className="flex items-center gap-2 px-3 py-1.5 bg-stone-100 dark:bg-slate-700 rounded-full text-xs text-stone-500 dark:text-stone-400">
                    <div className="animate-spin rounded-full h-3 w-3 border-2 border-stone-400 border-t-transparent"></div>
                    连接中...
                  </div>
                </div>
              )}
              {wsStatus === 'disconnected' && (
                <div className="flex justify-center">
                  <div className="flex items-center gap-2 px-3 py-1.5 bg-red-50 dark:bg-red-900/20 rounded-full text-xs text-red-500 dark:text-red-400 border border-red-200 dark:border-red-800">
                    <div className="w-2 h-2 rounded-full bg-red-500"></div>
                    连接已断开，请刷新页面重试
                  </div>
                </div>
              )}

              {messages.map((msg) => (
                <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className="flex flex-col max-w-2xl">
                    <span className={`text-xs text-stone-400 dark:text-stone-500 mb-1 px-1 ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
                      {msg.role === 'user' ? '我' : '智能助手'}
                    </span>
                    <div className={`px-4 py-3 rounded-xl text-sm leading-relaxed ${
                      msg.role === 'user'
                        ? 'bg-amber-600 text-white rounded-br-sm'
                        : 'bg-white dark:bg-slate-700 text-stone-800 dark:text-stone-100 rounded-bl-sm border border-stone-200 dark:border-slate-600'
                    }`}>
                      {msg.role === 'assistant' ? (
                        <div className="prose prose-sm dark:prose-invert max-w-none">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.content}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        <p className="whitespace-pre-wrap">{msg.content}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              {/* Real-time tool calls */}
              {(toolEvents.length > 0 || agentProgress) && (
                <div className="flex justify-start">
                  <div className="max-w-2xl bg-amber-50 dark:bg-amber-900/10 rounded-xl border border-amber-200 dark:border-amber-800 p-3 space-y-2">
                    {/* Progress bar */}
                    {agentProgress && (
                      <div className="flex items-center gap-3 text-xs">
                        <div className="animate-spin rounded-full h-3 w-3 border-2 border-amber-500 border-t-transparent flex-shrink-0"></div>
                        <span className="text-amber-600 dark:text-amber-400 font-medium">
                          第 {agentProgress.iteration}/{agentProgress.max} 轮搜索
                        </span>
                        <span className="text-stone-400 dark:text-stone-500">
                          已调用 {agentProgress.tools} 次工具
                        </span>
                      </div>
                    )}
                    {/* Context usage bar */}
                    {contextUsage && contextUsage.percent > 0 && (
                      <div className="flex items-center gap-2 text-xs mt-1">
                        <div className="flex-1 h-1.5 bg-stone-200 dark:bg-slate-600 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${
                              contextUsage.percent > 80 ? 'bg-red-500' :
                              contextUsage.percent > 60 ? 'bg-amber-500' :
                              'bg-green-500'
                            }`}
                            style={{ width: `${contextUsage.percent}%` }}
                          />
                        </div>
                        <span className="text-stone-400 dark:text-stone-500 w-10 text-right">
                          {contextUsage.percent}%
                        </span>
                        {contextUsage.action && (
                          <span className="text-stone-400 dark:text-stone-500 italic">
                            {contextUsage.action === 'microcompact' ? '已压缩早期结果' :
                             contextUsage.action === 'auto_compact' ? '已生成对话摘要' : ''}
                          </span>
                        )}
                      </div>
                    )}
                    {/* Tool call cards */}
                    {toolEvents.map((ev, i) => (
                      ev.type === 'tool_call' ? (
                        <ToolCallCard key={i} event={ev} />
                      ) : ev.type === 'thinking' && ev.content?.includes('跳过') ? (
                        <div key={i} className="text-xs text-stone-400 dark:text-stone-500 italic">
                          {ev.content}
                        </div>
                      ) : ev.type === 'thinking' && !ev.content?.startsWith('正在分析') && !ev.content?.startsWith('正在思考') && !ev.content?.startsWith('信息趋于饱和') ? (
                        <div key={i} className="text-xs text-stone-500 dark:text-stone-400 italic">
                          {ev.content}
                        </div>
                      ) : null
                    ))}
                  </div>
                </div>
              )}

              {/* Streaming content */}
              {streamingContent && (
                <div className="flex justify-start">
                  <div className="max-w-2xl px-4 py-3 rounded-xl text-sm leading-relaxed bg-white dark:bg-slate-700 text-stone-800 dark:text-stone-100 rounded-bl-sm border border-amber-300 dark:border-amber-600">
                    <p className="whitespace-pre-wrap">{streamingContent}</p>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            <div className="p-4 border-t border-stone-200 dark:border-slate-700">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
                  placeholder="输入问题..."
                  disabled={sending}
                  className="flex-1 px-4 py-2.5 rounded-xl border border-stone-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-stone-800 dark:text-stone-100 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 disabled:opacity-50"
                />
                <button
                  onClick={sendMessage}
                  disabled={sending || !input.trim()}
                  className="px-5 py-2.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white rounded-xl text-sm font-medium transition-colors"
                >
                  {sending ? (
                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                  ) : (
                    '发送'
                  )}
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center flex-1">
            <ChatIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
            <p className="text-stone-500 dark:text-stone-400 mb-4">开始新的对话</p>
            <button
              onClick={createSession}
              className="px-6 py-2.5 bg-amber-600 hover:bg-amber-700 text-white rounded-xl text-sm font-medium transition-colors"
            >
              创建对话
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
