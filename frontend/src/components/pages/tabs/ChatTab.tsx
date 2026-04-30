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
        }, 300_000)  // 300s idle timeout — resets on every event
      }
      resetIdleTimer()  // Start the idle timer

      ws.onopen = () => { setWsStatus('connected'); ws.send(JSON.stringify({ content })) }

      ws.onmessage = (event) => {
        resetIdleTimer()  // Activity — reset idle timeout
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
            case 'tool_call': case 'tool_result': case 'retrieval_hit': case 'decision':
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
    let attempts = 0; const maxAttempts = 120  // Poll up to ~10 min (120 × 5s)
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
    <div className="h-full flex">
      <ConfirmDialog open={confirmDelete !== null} title="删除会话" message="确定删除此会话？所有聊天记录将被永久删除。" onConfirm={executeDeleteSession} onCancel={() => setConfirmDelete(null)} />
      <div className="w-56 border-r border-stone-200 dark:border-slate-700 flex flex-col bg-white/50 dark:bg-slate-800/50">
        <div className="p-3 border-b border-stone-200 dark:border-slate-700">
          <button onClick={createSession} className="w-full px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-medium transition-colors">+ 新对话</button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sessions.map((s) => (
            <div key={s.id} className={`group flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs transition-colors ${currentSession === s.id ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 font-medium' : 'text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-slate-700'}`}>
              <button onClick={() => setCurrentSession(s.id)} className="flex-1 text-left truncate"><p className="truncate">{s.title}</p><p className="text-stone-400 dark:text-stone-500 mt-0.5 font-mono">{s.id.slice(0, 12)}</p></button>
              <button onClick={() => setConfirmDelete(s.id)} className="opacity-0 group-hover:opacity-100 p-1 text-stone-400 hover:text-red-500 transition-opacity" title="删除会话"><svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg></button>
            </div>
          ))}
        </div>
      </div>
      <div className="flex-1 flex flex-col min-w-0">
        {currentSession ? (
          <>
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {wsStatus === 'connecting' && (<div className="flex justify-center"><div className="flex items-center gap-2 px-3 py-1.5 bg-stone-100 dark:bg-slate-700 rounded-full text-xs text-stone-500 dark:text-stone-400"><div className="animate-spin rounded-full h-3 w-3 border-2 border-stone-400 border-t-transparent"></div>连接中...</div></div>)}
              {wsStatus === 'disconnected' && (<div className="flex justify-center"><div className="flex items-center gap-2 px-3 py-1.5 bg-red-50 dark:bg-red-900/20 rounded-full text-xs text-red-500 dark:text-red-400 border border-red-200 dark:border-red-800"><div className="w-2 h-2 rounded-full bg-red-500"></div>连接已断开，请刷新页面重试</div></div>)}
              {messages.map((msg) => (<div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}><div className="flex flex-col max-w-2xl"><span className={`text-xs text-stone-400 dark:text-stone-500 mb-1 px-1 ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>{msg.role === 'user' ? '我' : '智能助手'}</span><div className={`px-4 py-3 rounded-xl text-sm leading-relaxed ${msg.role === 'user' ? 'bg-amber-600 text-white rounded-br-sm' : 'bg-white dark:bg-slate-700 text-stone-800 dark:text-stone-100 rounded-bl-sm border border-stone-200 dark:border-slate-600'}`}>{msg.role === 'assistant' ? <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ p: ({ children }) => <p className="mb-1 last:mb-0">{children}</p>, a: ({ href, children }) => <a href={href} className="text-amber-600 dark:text-amber-400 underline hover:text-amber-700" target="_blank" rel="noopener noreferrer">{children}</a>, code: ({ children }) => <code className="bg-stone-200 dark:bg-slate-600 px-1 py-0.5 rounded text-xs font-mono">{children}</code>, pre: ({ children }) => <pre className="bg-stone-100 dark:bg-slate-800 rounded-lg p-3 my-2 overflow-x-auto text-xs font-mono">{children}</pre> }}>{msg.content}</ReactMarkdown> : <p className="whitespace-pre-wrap">{msg.content}</p>}</div></div></div>))}

              {(thinkingEvents.length > 0 || agentEvents.length > 0 || streamingContent) && (
                <div className="flex justify-start"><div className="max-w-2xl bg-amber-50 dark:bg-amber-900/10 rounded-xl border border-amber-200 dark:border-amber-800 p-3 w-full">
                  <div className="flex items-center gap-2 text-xs text-amber-600 dark:text-amber-400 font-medium mb-2">
                    {streamingContent ? (
                      <CheckCircleIcon className="w-3.5 h-3.5 text-green-500" />
                    ) : (
                      <div className="animate-spin rounded-full h-3 w-3 border-2 border-amber-500 border-t-transparent"></div>
                    )}
                    {streamingContent ? '正在生成回答...' : 'Agent 正在思考...'}
                  </div>
                  <AgentLoopDisplay thinkingEvents={thinkingEvents} actionEvents={agentEvents} onClear={() => { setThinkingEvents([]); setAgentEvents([]) }} />
                  {streamingContent && (
                    <div className="mt-3 p-3 bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-600 text-sm text-stone-800 dark:text-stone-100 leading-relaxed">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ p: ({ children }) => <p className="mb-1 last:mb-0">{children}</p>, a: ({ href, children }) => <a href={href} className="text-amber-600 dark:text-amber-400 underline hover:text-amber-700" target="_blank" rel="noopener noreferrer">{children}</a>, code: ({ children }) => <code className="bg-stone-200 dark:bg-slate-600 px-1 py-0.5 rounded text-xs font-mono">{children}</code>, pre: ({ children }) => <pre className="bg-stone-100 dark:bg-slate-800 rounded-lg p-3 my-2 overflow-x-auto text-xs font-mono">{children}</pre> }}>{streamingContent}</ReactMarkdown>
                      <span className="inline-block w-2 h-4 bg-amber-500 animate-pulse ml-0.5 align-middle" />
                    </div>
                  )}
                  {pendingAskUser && (
                    <AskUserBlock
                      event={pendingAskUser}
                      onReply={replyToAskUser}
                      disabled={askUserDisabled}
                    />
                  )}
                </div></div>
              )}

              {isThinking && !streamingContent && (
                <div className="flex justify-start"><div className="max-w-2xl bg-stone-50 dark:bg-slate-700/50 rounded-xl border border-stone-200 dark:border-slate-600 p-4 flex items-center gap-3">
                  <div className="flex gap-1"><div className="w-2 h-2 rounded-full bg-amber-500 animate-bounce" style={{animationDelay: '0ms'}}></div><div className="w-2 h-2 rounded-full bg-amber-500 animate-bounce" style={{animationDelay: '150ms'}}></div><div className="w-2 h-2 rounded-full bg-amber-500 animate-bounce" style={{animationDelay: '300ms'}}></div></div>
                  <span className="text-sm text-stone-500 dark:text-stone-400">正在连接 Agent...</span>
                </div></div>
              )}

              <div ref={messagesEndRef} />
            </div>
            <div className="p-4 border-t border-stone-200 dark:border-slate-700">
              <div className="flex gap-2">
                <input type="text" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()} placeholder="输入问题..." disabled={sending} className="flex-1 px-4 py-2.5 rounded-xl border border-stone-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-stone-800 dark:text-stone-100 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 disabled:opacity-50" />
                <button onClick={sendMessage} disabled={sending || !input.trim()} className="px-5 py-2.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white rounded-xl text-sm font-medium transition-colors">{sending ? <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div> : '发送'}</button>
              </div>
            </div>
          </>
        ) : (<div className="flex flex-col items-center justify-center flex-1"><ChatIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" /><p className="text-stone-500 dark:text-stone-400 mb-4">开始新的对话</p><button onClick={createSession} className="px-6 py-2.5 bg-amber-600 hover:bg-amber-700 text-white rounded-xl text-sm font-medium transition-colors">创建对话</button></div>)}
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
