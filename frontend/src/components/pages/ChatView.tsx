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
    <div className="chat-tool-call">
      <button
        onClick={() => setExpanded(!expanded)}
        className="chat-tool-call__toggle"
      >
        <IconComp className="icon-sm" />
        <span className="font-medium">{label}</span>
        {event.duration && (
          <span className="chat-tool-call__duration">{event.duration}s</span>
        )}
        <span className={`chat-tool-call__chevron ${expanded ? 'chat-tool-call__chevron--expanded' : ''}`}>
          {'▸'}
        </span>
      </button>
      {expanded && (
        <div className="chat-tool-call__details">
          {inputPreview && (
            <div className="chat-tool-call__detail-block">
              <span className="chat-tool-call__detail-label">{'输入：'}</span>
              <code className="chat-tool-call__detail-code">{inputPreview}</code>
            </div>
          )}
          {outputPreview && (
            <div className="chat-tool-call__detail-block">
              <span className="chat-tool-call__detail-label">{'输出：'}</span>
              <p className="chat-tool-call__detail-output">{outputPreview}{(event.output || '').length > 100 ? '...' : ''}</p>
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
      <div className="chat-empty-state">
        <ChatIcon className="chat-empty-icon" />
        <p className="chat-view__center-text">{'暂无知识库，请先创建'}</p>
      </div>
    )
  }

  if (!currentKbId) {
    return (
      <div className="chat-empty-state">
        <ChatIcon className="chat-empty-icon" />
        <p className="chat-view__center-text chat-empty-text">{'选择知识库开始对话'}</p>
        <select
          value=""
          onChange={(e) => setCurrentKbId(e.target.value)}
          className="chat-view__select"
        >
          <option value="">{'请选择...'}</option>
          {kbs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
        </select>
      </div>
    )
  }

  return (
    <div className="chat-container">
      <div className="chat-sidebar">
        <div className="chat-sidebar-header">
          <div className="chat-sidebar-header__row">
            <select
              value={currentKbId}
              onChange={(e) => { setCurrentKbId(e.target.value); setCurrentSession(null) }}
              className="chat-view__select chat-view__select--xs"
            >
              {kbs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
            </select>
            <button
              onClick={createSession}
              className="chat-view__new-session-btn"
            >
              {'+'}
            </button>
          </div>
        </div>
        <div className="chat-session-list">
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`chat-session-item ${currentSession === s.id ? 'chat-session-item--active' : ''}`}
            >
              <button
                onClick={() => setCurrentSession(s.id)}
                className="chat-session-btn"
              >
                <p className="chat-session-title">{s.title}</p>
                <p className="chat-session-id">{s.id.slice(0, 12)}</p>
              </button>
              <button
                onClick={(e) => deleteSession(s.id, e)}
                className="chat-session-delete-btn"
                title="删除会话"
              >
                <svg className="chat-session-delete-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="chat-main">
        {currentSession ? (
          <>
            <div className="chat-message-list">
              {/* Connection status indicator */}
              {wsStatus === 'connecting' && (
                <div className="chat-status-bar">
                  <div className="chat-status-pill chat-status-pill--connecting">
                    <div className="chat-spinner chat-spinner--sm"></div>
                    {'连接中...'}
                  </div>
                </div>
              )}
              {wsStatus === 'disconnected' && (
                <div className="chat-status-bar">
                  <div className="chat-status-pill chat-status-pill--disconnected">
                    <div className="chat-disconnected-dot"></div>
                    {'连接已断开，请刷新页面重试'}
                  </div>
                </div>
              )}

              {messages.map((msg) => (
                <div key={msg.id} className={`chat-message-row ${msg.role === 'user' ? 'chat-message-row--user' : 'chat-message-row--assistant'}`}>
                  <div className="chat-message-col">
                    <span className={`chat-message-sender ${msg.role === 'user' ? 'chat-message-sender--user' : 'chat-message-sender--assistant'}`}>
                      {msg.role === 'user' ? '我' : '智能助手'}
                    </span>
                    <div className={`chat-message-bubble ${msg.role === 'user' ? 'chat-message-bubble--user' : 'chat-message-bubble--assistant'}`}>
                      {msg.role === 'assistant' ? (
                        <div className="chat-md-content">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.content}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        <p className="chat-message-user-text">{msg.content}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              {/* Real-time tool calls */}
              {(toolEvents.length > 0 || agentProgress) && (
                <div className="chat-message-row chat-message-row--assistant">
                  <div className="chat-agent-panel">
                    {/* Progress bar */}
                    {agentProgress && (
                      <div className="chat-agent-header">
                        <div className="chat-spinner chat-spinner--accent"></div>
                        <span className="chat-agent-header">
                          {'第 '}{agentProgress.iteration}{'/'}{agentProgress.max}{' 轮搜索'}
                        </span>
                        <span className="chat-agent-progress-tools">
                          {'已调用 '}{agentProgress.tools}{' 次工具'}
                        </span>
                      </div>
                    )}
                    {/* Context usage bar */}
                    {contextUsage && contextUsage.percent > 0 && (
                      <div className="chat-context-usage">
                      <div className="chat-context-usage__bar">
                          <div
                            className={`chat-context-usage__fill ${contextUsage.percent > 80 ? 'chat-context-usage__fill--danger' : contextUsage.percent > 60 ? 'chat-context-usage__fill--warning' : 'chat-context-usage__fill--ok'}`}
                            style={{ width: `${contextUsage.percent}%` }}
                          />
                        </div>
                        <span className="chat-context-usage__label">
                          {contextUsage.percent}%
                        </span>
                        {contextUsage.action && (
                          <span className="chat-context-usage__action">
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
                        <div key={i} className="chat-thinking-italic">
                          {ev.content}
                        </div>
                      ) : ev.type === 'thinking' && !ev.content?.startsWith('正在分析') && !ev.content?.startsWith('正在思考') && !ev.content?.startsWith('信息趋于饱和') ? (
                        <div key={i} className="chat-thinking-italic">
                          {ev.content}
                        </div>
                      ) : null
                    ))}
                  </div>
                </div>
              )}

              {/* Streaming content */}
              {streamingContent && (
                <div className="chat-message-row chat-message-row--assistant">
                  <div className="chat-streaming-content">
                    <p className="whitespace-pre-wrap">{streamingContent}</p>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            <div className="chat-input-area">
              <div className="chat-input-row">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
                  placeholder="输入问题..."
                  disabled={sending}
                  className="chat-input-field"
                />
                <button
                  onClick={sendMessage}
                  disabled={sending || !input.trim()}
                  className="chat-send-btn"
                >
                  {sending ? (
                    <div className="chat-spinner chat-spinner--white"></div>
                  ) : (
                    '发送'
                  )}
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="chat-empty-state">
            <ChatIcon className="chat-empty-icon" />
            <p className="chat-empty-text">{'开始新的对话'}</p>
            <button
              onClick={createSession}
              className="chat-empty-btn"
            >
              {'创建对话'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
