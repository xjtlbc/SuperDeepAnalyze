import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { API_BASE } from './shared'
import { ChatIcon } from '../../Icons'
import { AgentLoopDisplay } from '../../AgentLoopDisplay'
import { AskUserBlock } from '../../AgentLoopDisplay/AskUserBlock'
import { ConfirmDialog } from '../../ConfirmDialog'
import type { AgentEvent } from '../../../types/agent'

interface ChatMessage { id: string; role: 'user' | 'assistant'; content: string; created_at?: string }

export function ChatTab({ kbId }: { kbId: string }) {
  return <EmbeddedChatView kbId={kbId} />
}

function EmbeddedChatView({ kbId }: { kbId: string }) {
  const [sessions, setSessions] = useState<{ id: string; title: string }[]>([])
  const [currentSession, setCurrentSession] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [thinkingEvents, setThinkingEvents] = useState<AgentEvent[]>([])
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([])
  const [wsStatus, setWsStatus] = useState<'idle' | 'connecting' | 'connected' | 'disconnected'>('idle')
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [pendingAskUser, setPendingAskUser] = useState<AgentEvent | null>(null)
  const [askUserDisabled, setAskUserDisabled] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => { fetchSessions() }, [kbId])
  useEffect(() => { if (currentSession) fetchMessages() }, [currentSession])
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, streamingContent, thinkingEvents, agentEvents])
  useEffect(() => { return () => { wsRef.current?.close(); wsRef.current = null } }, [])

  const fetchSessions = async () => {
    try { const res = await fetch(`${API_BASE}/api/sessions/${kbId}`); if (res.ok) { const data = await res.json(); setSessions(Array.isArray(data) ? data : []) } } catch (e) { console.error('Failed to fetch sessions:', e) }
  }

  const fetchMessages = async () => {
    if (!currentSession) return
    try { const res = await fetch(`${API_BASE}/api/sessions/${currentSession}/messages`); if (res.ok) { const data = await res.json(); setMessages(Array.isArray(data) ? data : []) } } catch (e) { console.error('Failed to fetch messages:', e) }
  }

  const createSession = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/sessions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kb_id: kbId, title: '新对话' }) })
      if (res.ok) { const data = await res.json(); setSessions((prev) => [data, ...prev]); setCurrentSession(data.id); setMessages([]) }
    } catch (e) { console.error('Failed to create session:', e) }
  }

  const executeDeleteSession = async () => {
    const sessionId = confirmDelete
    setConfirmDelete(null)
    if (!sessionId) return
    try { const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, { method: 'DELETE' }); if (res.ok || res.status === 204) { setSessions((prev) => prev.filter((s) => s.id !== sessionId)); if (currentSession === sessionId) setCurrentSession(null) } } catch (e) { console.error('Failed to delete session:', e) }
  }

  const sendWithWs = async (sessionId: string, content: string, isNewSession: boolean = false) => {
    setSending(true); setStreamingContent(''); setThinkingEvents([]); setAgentEvents([]); setWsStatus('idle')

    const userMsgId = `umsg_${Date.now()}`
    const userMsg: ChatMessage = { id: userMsgId, role: 'user' as const, content }
    if (isNewSession) { setMessages([userMsg]) }
    else { setMessages(prev => [...prev, userMsg]) }

    try {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const host = location.host
      setWsStatus('connecting')
      const ws = new WebSocket(`${proto}//${host}/api/ws/sessions/${sessionId}`)
      wsRef.current = ws
      let finalReceived = false
      let idleTimer: ReturnType<typeof setTimeout> | null = null

      const clearIdleTimer = () => { if (idleTimer) { clearTimeout(idleTimer); idleTimer = null } }
      const resetIdleTimer = () => {
        clearIdleTimer()
        idleTimer = setTimeout(() => {
          if (!finalReceived) { ws.close(); setWsStatus('disconnected'); startHttpPoll(sessionId) }
        }, 300_000)
      }
      resetIdleTimer()

      ws.onopen = () => { setWsStatus('connected'); ws.send(JSON.stringify({ content })) }

      ws.onmessage = (event) => {
        resetIdleTimer()
        try {
          const data = JSON.parse(event.data)
          const agentEvent: AgentEvent = {
            id: data.id || `evt_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            type: data.type as AgentEvent['type'],
            timestamp: data.timestamp || Date.now(),
            content: data.content,
            tool_name: data.tool || data.tool_name,
            tool_args: data.input || data.tool_args,
            tool_result: data.output || data.tool_result,
            level: data.level,
            relevance_score: data.relevance_score,
            confidence: data.confidence,
            drill_path: data.drill_path,
            duration_ms: data.duration_ms || data.duration ? data.duration * 1000 : undefined,
            question_type: data.question_type,
            complexity: data.complexity,
            sub_queries: data.sub_queries,
            answered_aspects: data.answered_aspects,
            missing_aspects: data.missing_aspects,
            evidence_strength: data.evidence_strength,
            phase: data.phase,
            token_usage: data.token_usage,
            token_limit: data.token_limit,
            action: data.action,
            workflow_mode: data.workflow_mode,
            workflow_steps: data.steps,
            workflow_synthesis: data.synthesis_preview,
            workflow_total_entities: data.total_entities,
            workflow_total_duration: data.total_duration,
          }
          switch (data.type) {
            case 'thinking':
            case 'phase':
              setThinkingEvents(prev => [...prev, agentEvent])
              break
            case 'intent_analysis':
            case 'reflection':
            case 'turn_summary':
            case 'progress':
            case 'context_update':
              setThinkingEvents(prev => [...prev, agentEvent])
              break
            case 'ask_user':
              setPendingAskUser(agentEvent)
              break
            case 'tool_call': case 'tool_result': case 'retrieval_hit': case 'decision': case 'workflow_result':
              setAgentEvents(prev => [...prev, agentEvent])
              break
            case 'chunk':
              setStreamingContent(prev => prev + data.content)
              break
            case 'final_answer':
              finalReceived = true; clearIdleTimer()
              setStreamingContent(''); setThinkingEvents([]); setAgentEvents([])
              setWsStatus('idle'); setSending(false)
              ws.close()
              fetch(`${API_BASE}/api/sessions/${sessionId}/messages`).then(r => r.json()).then(data => {
                setMessages(Array.isArray(data) ? data : [])
              }).catch(() => {
                setMessages(prev => [...prev, { id: `agent_${Date.now()}`, role: 'assistant' as const, content: data.content }])
              })
              fetch(`${API_BASE}/api/sessions/${sessionId}/title`, { method: 'PUT' }).then(r => r.json()).then(d => {
                setSessions(prev => prev.map(s => s.id === sessionId ? { ...s, title: d.title } : s))
              }).catch(console.error)
              break
            case 'error':
              finalReceived = true; clearIdleTimer()
              setMessages(prev => [...prev, { id: `err_${Date.now()}`, role: 'assistant' as const, content: `错误: ${data.content}` }])
              setStreamingContent(''); setThinkingEvents([]); setAgentEvents([])
              setSending(false); setWsStatus('idle'); ws.close()
              break
          }
        } catch (e) { console.error('Failed to parse WS message:', e) }
      }

      ws.onclose = () => { clearIdleTimer(); if (!finalReceived) { setWsStatus('disconnected'); startHttpPoll(sessionId) } }
      ws.onerror = () => { clearIdleTimer(); if (!finalReceived) { setWsStatus('disconnected') } }
    } catch (e) { setWsStatus('disconnected'); setSending(false) }
  }

  const startHttpPoll = (sessionId: string) => {
    let attempts = 0; const maxAttempts = 120
    const pollInterval = setInterval(async () => {
      attempts++
      try {
        const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`)
        if (res.ok) {
          const data = await res.json()
          const msgs = Array.isArray(data) ? data : []
          const hasAssistant = msgs.some((m: ChatMessage) => m.role === 'assistant')
          if (hasAssistant) { setMessages(msgs); setWsStatus('idle'); setSending(false); clearInterval(pollInterval); return }
        }
      } catch (e) {}
      if (attempts >= maxAttempts) { clearInterval(pollInterval); setSending(false) }
    }, 5000)
  }

  const replyToAskUser = (answer: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    setAskUserDisabled(true)
    wsRef.current.send(JSON.stringify({ type: 'user_response', answer }))
    setPendingAskUser(null)
    setAskUserDisabled(false)
  }

  const sendMessage = async () => {
    if (!input.trim() || sending) return
    const messageContent = input.trim(); setInput('')
    if (!currentSession) {
      setSending(true)
      try {
        const res = await fetch(`${API_BASE}/api/sessions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kb_id: kbId, title: messageContent.slice(0, 20) }) })
        if (res.ok) { const data = await res.json(); setSessions((prev) => [data, ...prev]); setCurrentSession(data.id); sendWithWs(data.id, messageContent, true) }
        else { setSending(false) }
      } catch (e) { console.error('Failed to create session:', e); setSending(false) }
      return
    }
    sendWithWs(currentSession, messageContent)
  }

  const isThinking = sending && thinkingEvents.length === 0 && agentEvents.length === 0

  return (
    <div className="chat-container">
      <ConfirmDialog open={confirmDelete !== null} title="删除会话" message="确定删除此会话？所有聊天记录将被永久删除。" onConfirm={executeDeleteSession} onCancel={() => setConfirmDelete(null)} />

      {/* Session sidebar */}
      <div className="chat-sidebar">
        <div className="chat-sidebar-header">
          <button onClick={createSession} className="chat-new-session-btn">+ 新对话</button>
        </div>
        <div className="chat-session-list">
          {sessions.map((s) => (
            <div key={s.id} className={`chat-session-item ${currentSession === s.id ? 'chat-session-item--active' : ''}`}>
              <button onClick={() => setCurrentSession(s.id)} className="chat-session-btn">
                <p className="chat-session-title">{s.title}</p>
                <p className="chat-session-id">{s.id.slice(0, 12)}</p>
              </button>
              <button onClick={() => setConfirmDelete(s.id)} className="chat-session-delete-btn" title="删除会话">
                <svg className="chat-session-delete-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Main chat area */}
      <div className="chat-main">
        {currentSession ? (
          <>
            <div className="chat-message-list">
              {/* Connection status */}
              {wsStatus === 'connecting' && (
                <div className="chat-status-bar">
                  <div className="chat-status-pill chat-status-pill--connecting">
                    <div className="chat-spinner chat-spinner--sm"></div>
                    连接中...
                  </div>
                </div>
              )}
              {wsStatus === 'disconnected' && (
                <div className="chat-status-bar">
                  <div className="chat-status-pill chat-status-pill--disconnected">
                    <div className="chat-disconnected-dot"></div>
                    连接已断开，请刷新页面重试
                  </div>
                </div>
              )}

              {/* Messages */}
              {messages.map((msg) => (
                <div key={msg.id} className={`chat-message-row ${msg.role === 'user' ? 'chat-message-row--user' : 'chat-message-row--assistant'}`}>
                  <div className="chat-message-col">
                    <span className={`chat-message-sender ${msg.role === 'user' ? 'chat-message-sender--user' : 'chat-message-sender--assistant'}`}>
                      {msg.role === 'user' ? '我' : '智能助手'}
                    </span>
                    <div className={`chat-message-bubble ${msg.role === 'user' ? 'chat-message-bubble--user' : 'chat-message-bubble--assistant'}`}>
                      {msg.role === 'assistant' ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                          p: ({ children }) => <p className="chat-md-p">{children}</p>,
                          a: ({ href, children }) => <a href={href} className="chat-md-link" target="_blank" rel="noopener noreferrer">{children}</a>,
                          code: ({ children }) => <code className="chat-md-inline-code">{children}</code>,
                          pre: ({ children }) => <pre className="chat-md-pre">{children}</pre>,
                        }}>{msg.content}</ReactMarkdown>
                      ) : (
                        <p className="chat-message-user-text">{msg.content}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              {/* Agent thinking / streaming area */}
              {(thinkingEvents.length > 0 || agentEvents.length > 0 || streamingContent) && (
                <div className="chat-message-row chat-message-row--assistant">
                  <div className="chat-agent-panel">
                    <div className="chat-agent-header">
                      {streamingContent ? (
                        <CheckCircleIcon className="chat-agent-check-icon" />
                      ) : (
                        <div className="chat-spinner chat-spinner--accent"></div>
                      )}
                      {streamingContent ? '正在生成回答...' : 'Agent 正在思考...'}
                    </div>
                    <AgentLoopDisplay thinkingEvents={thinkingEvents} actionEvents={agentEvents} onClear={() => { setThinkingEvents([]); setAgentEvents([]) }} />
                    {streamingContent && (
                      <div className="chat-streaming-content">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                          p: ({ children }) => <p className="chat-md-p">{children}</p>,
                          a: ({ href, children }) => <a href={href} className="chat-md-link" target="_blank" rel="noopener noreferrer">{children}</a>,
                          code: ({ children }) => <code className="chat-md-inline-code">{children}</code>,
                          pre: ({ children }) => <pre className="chat-md-pre">{children}</pre>,
                        }}>{streamingContent}</ReactMarkdown>
                        <span className="chat-cursor" />
                      </div>
                    )}
                    {pendingAskUser && (
                      <AskUserBlock
                        event={pendingAskUser}
                        onReply={replyToAskUser}
                        disabled={askUserDisabled}
                      />
                    )}
                  </div>
                </div>
              )}

              {/* Initial thinking indicator */}
              {isThinking && !streamingContent && (
                <div className="chat-message-row chat-message-row--assistant">
                  <div className="chat-thinking-indicator">
                    <div className="chat-bouncing-dots">
                      <div className="chat-bouncing-dot" style={{ animationDelay: '0ms' }}></div>
                      <div className="chat-bouncing-dot" style={{ animationDelay: '150ms' }}></div>
                      <div className="chat-bouncing-dot" style={{ animationDelay: '300ms' }}></div>
                    </div>
                    <span className="chat-thinking-text">正在连接 Agent...</span>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Input area */}
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
                <button onClick={sendMessage} disabled={sending || !input.trim()} className="chat-send-btn">
                  {sending ? <div className="chat-spinner chat-spinner--white"></div> : '发送'}
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="chat-empty-state">
            <ChatIcon className="chat-empty-icon" />
            <p className="chat-empty-text">开始新的对话</p>
            <button onClick={createSession} className="chat-empty-btn">创建对话</button>
          </div>
        )}
      </div>
    </div>
  )
}

function CheckCircleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  )
}
