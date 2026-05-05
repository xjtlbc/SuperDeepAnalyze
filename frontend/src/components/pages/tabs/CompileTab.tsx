import { useState, useEffect, useRef } from 'react'
import { API_BASE } from './shared'
import { FileTextIcon, RefreshIcon, DocumentIcon, GraphIcon, ChevronRightIcon, PlayIcon, CheckCircleIcon, InfoIcon, CompileIcon, PauseIcon } from '../../Icons'

interface CompileProgress {
  type: string
  phase: string
  progress: number
  message: string
  stats?: Record<string, unknown>
}

export function CompileTab({ kbId, onCompileDone }: { kbId: string; onCompileDone?: () => void }) {
  const [compiling, setCompiling] = useState(false)
  const [compileProgress, setCompileProgress] = useState<CompileProgress | null>(null)
  const [compileLog, setCompileLog] = useState<{ time: string; phase: string; message: string; progress: number }[]>([])
  const [compileResult, setCompileResult] = useState<string | null>(null)
  const [isPaused, setIsPaused] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [compileLog])

  useEffect(() => {
    return () => {
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [])

  const addLog = (phase: string, message: string, progress: number) => {
    setCompileLog(prev => [...prev, { time: new Date().toLocaleTimeString('zh-CN'), phase, message, progress }])
  }

  useEffect(() => {
    fetch(`${API_BASE}/api/knowledge-bases`)
      .then(r => r.json())
      .then(data => {
        const kb = (Array.isArray(data) ? data : []).find((k: any) => k.id === kbId)
        if (kb) {
          if (kb.compile_status === 'processing') {
            reconnectToCompile()
          } else if (kb.compile_status === 'paused') {
            setIsPaused(true)
            setCompileResult('上次编译已暂停，可继续编译')
          } else if (kb.compile_status === 'completed') {
            setCompileResult('编译已完成')
          } else if (kb.compile_status === 'failed') {
            setCompileResult('上次编译失败，请重试')
          }
        }
      })
      .catch(console.error)
  }, [kbId])

  const reconnectToCompile = () => {
    setCompiling(true)
    setCompileResult(null)
    addLog('reconnecting', '检测到编译进行中，正在重连...', 0)

    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = location.host
    const ws = new WebSocket(`${proto}//${host}/api/compile/ws/${kbId}`)
    wsRef.current = ws

    let receivedResult = false

    ws.onopen = () => { addLog('connected', '已连接编译服务', 0) }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setCompileProgress(data)
        addLog(data.phase || 'status', data.message, data.progress || 0)
        if (data.type === 'done') {
          receivedResult = true
          setCompiling(false); setIsPaused(false)
          const stats = data.stats || {}
          setCompileResult(`编译完成! ${stats.documents_processed || 0} 文档, ${stats.chunks_generated || 0} chunks, ${stats.l1_summaries || 0} L1 摘要`)
          onCompileDone?.()
          ws.close()
        } else if (data.type === 'error') {
          receivedResult = true
          setCompiling(false); setIsPaused(false)
          setCompileResult(`编译失败: ${data.message}`)
          ws.close()
        } else if (data.type === 'paused') {
          receivedResult = true
          setCompiling(false); setIsPaused(true)
          setCompileResult(`编译已暂停: ${data.message}`)
          ws.close()
        }
      } catch (e) { console.error('Failed to parse compile WS message:', e) }
    }

    ws.onclose = () => {
      if (!receivedResult) {
        fetch(`${API_BASE}/api/knowledge-bases`)
          .then(r => r.json())
          .then(data => {
            const kb = (Array.isArray(data) ? data : []).find((k: any) => k.id === kbId)
            if (kb?.compile_status === 'completed') { setCompiling(false); setCompileResult('编译已完成（重连时编译已结束）') }
            else if (kb?.compile_status === 'failed') { setCompiling(false); setCompileResult('编译失败（重连时检测到）') }
            else { setCompiling(false); setCompileResult('编译连接已断开，请刷新重试') }
          })
          .catch(() => { setCompiling(false); setCompileResult('编译连接已断开，请刷新重试') })
      }
    }
    ws.onerror = () => { if (!receivedResult) { setCompiling(false); setCompileResult('编译连接失败，请重试') } }
  }

  const handleCompile = async () => {
    setCompiling(true); setIsPaused(false)
    setCompileLog([]); setCompileResult(null)
    addLog('connecting', '连接编译服务...', 0)

    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = location.host
    const ws = new WebSocket(`${proto}//${host}/api/compile/ws/${kbId}`)
    wsRef.current = ws

    let receivedResult = false

    ws.onopen = () => { addLog('connected', '已连接，开始编译...', 0) }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setCompileProgress(data)
        addLog(data.phase || 'status', data.message, data.progress || 0)
        if (data.type === 'done') {
          receivedResult = true
          setCompiling(false); setIsPaused(false)
          const stats = data.stats || {}
          setCompileResult(`编译完成! ${stats.documents_processed || 0} 文档, ${stats.documents_skipped || 0} 跳过, ${stats.chunks_generated || 0} chunks, ${stats.l1_summaries || 0} L1 摘要`)
          onCompileDone?.()
          ws.close()
        } else if (data.type === 'error') {
          receivedResult = true
          setCompiling(false); setIsPaused(false)
          setCompileResult(`编译失败: ${data.message}`)
          ws.close()
        } else if (data.type === 'paused') {
          receivedResult = true
          setCompiling(false); setIsPaused(true)
          setCompileResult(`编译已暂停: ${data.message}`)
          ws.close()
        }
      } catch (e) { console.error('Failed to parse compile WS message:', e) }
    }

    ws.onclose = () => { if (!receivedResult) { setCompiling(false); setCompileResult('编译连接已断开，请重试') } }
    ws.onerror = () => { if (!receivedResult) { setCompiling(false); setCompileResult('编译连接失败，请重试') } }
  }

  const handlePause = () => {
    wsRef.current?.send(JSON.stringify({ type: 'cancel' }))
    addLog('cancel', '发送暂停请求...', 0)
  }

  const phaseIconMap: Record<string, React.ComponentType<{className?: string}>> = {
    parsing: FileTextIcon, connecting: RefreshIcon, reconnecting: RefreshIcon,
    compiling_l2: DocumentIcon, compiling_l1: FileTextIcon, compiling_l0: GraphIcon,
    skipping_existing: ChevronRightIcon, acceleration_mode: PlayIcon, done: CheckCircleIcon, status: InfoIcon,
  }

  const phaseLabels: Record<string, string> = {
    parsing: '加载文档', connecting: '连接', reconnecting: '重连',
    compiling_l2: 'L2 索引', compiling_l1: 'L1 摘要', compiling_l0: 'L0 图谱',
    wiki_generation: 'Wiki 生成', skipping_existing: '跳过', acceleration_mode: '加速模式', done: '完成', status: '状态',
  }

  // Stage progress indicators
  const stages = [
    { key: 'compiling_l2', label: 'L2 索引', range: [10, 30] },
    { key: 'compiling_l1', label: 'L1 摘要', range: [30, 65] },
    { key: 'compiling_l0', label: 'L0 图谱', range: [65, 80] },
    { key: 'wiki_generation', label: 'Wiki', range: [80, 95] },
  ]

  const currentStageIndex = stages.findIndex(s => {
    if (!compileProgress) return -1
    const p = compileProgress.progress
    return p >= s.range[0] && p < s.range[1]
  })

  return (
    <div className="compile-tab">
      <div className="compile-tab__inner">
        {isPaused ? (
          <button onClick={handleCompile} className="compile-tab__main-btn compile-tab__main-btn--resume">
            {'继续编译 (从断点恢复)'}
          </button>
        ) : (
          <button
            onClick={compiling ? handlePause : handleCompile}
            disabled={!compiling && false}
            className={`compile-tab__main-btn ${compiling ? 'compile-tab__main-btn--pause' : 'compile-tab__main-btn--start'}`}
          >
            {compiling ? <><PauseIcon className="icon-sm" />{'暂停编译'}</> : '一键编译全部 (L0/L1/L2)'}
          </button>
        )}

        {compiling && compileProgress && (
          <div className="compile-tab__progress-card">
            {/* Stage indicators */}
            <div className="compile-tab__stages">
              {stages.map((stage, idx) => (
                <div key={stage.key} className="compile-tab__stage">
                  <div className={`compile-tab__stage-dot ${idx < currentStageIndex ? 'compile-tab__stage-dot--done' : idx === currentStageIndex ? 'compile-tab__stage-dot--active' : 'compile-tab__stage-dot--pending'}`}>
                    {idx < currentStageIndex ? '✓' : idx + 1}
                  </div>
                  <span className={`compile-tab__stage-label ${idx <= currentStageIndex ? 'compile-tab__stage-label--active' : ''}`}>{stage.label}</span>
                </div>
              ))}
            </div>

            {/* Current phase message */}
            <div className="compile-tab__phase-row">
              {(() => { const IconComp = phaseIconMap[compileProgress.phase] || InfoIcon; return <IconComp className="icon-sm" /> })()}
              <span className="compile-tab__phase-message">{compileProgress.message}</span>
              <span className="compile-tab__phase-percent">{compileProgress.progress}%</span>
            </div>

            {/* Progress bar */}
            <div className="compile-tab__progress-bar-track">
              <div className="compile-tab__progress-bar-fill" style={{ width: `${compileProgress.progress}%` }} />
            </div>
          </div>
        )}

        {compileLog.length > 0 && (
          <div className="compile-tab__log-card">
            <div className="compile-tab__log-header">
              <span className="compile-tab__log-title">{'编译日志'}</span>
              <span className="compile-tab__log-count">{compileLog.length} {'条'}</span>
            </div>
            <div className="compile-tab__log-list">
              {compileLog.map((log, i) => (
                <div key={i} className="compile-tab__log-item">
                  <span className="compile-tab__log-time">{log.time}</span>
                  {(() => { const IconComp = phaseIconMap[log.phase] || InfoIcon; return <IconComp className="compile-tab__log-icon" /> })()}
                  <span className={`compile-tab__log-phase-badge ${log.phase.includes('l0') ? 'compile-tab__log-phase-badge--l0' : log.phase.includes('l1') ? 'compile-tab__log-phase-badge--l1' : log.phase.includes('l2') ? 'compile-tab__log-phase-badge--l2' : log.phase === 'done' ? 'compile-tab__log-phase-badge--done' : 'compile-tab__log-phase-badge--default'}`}>{phaseLabels[log.phase] || log.phase}</span>
                  <span className="compile-tab__log-msg">{log.message}</span>
                  <span className="compile-tab__log-percent">{log.progress}%</span>
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>
        )}

        {compileResult && (
          <div className={`compile-tab__result ${compileResult.includes('完成') ? 'compile-tab__result--success' : 'compile-tab__result--error'}`}>
            {compileResult}
          </div>
        )}

        {!compiling && !compileResult && (
          <div className="compile-tab__idle">
            <CompileIcon className="compile-tab__idle-icon" />
            <p className="compile-tab__idle-text">{'点击按钮开始编译'}</p>
            <p className="compile-tab__idle-hint">{'编译将执行 L2 分段索引 → L1 摘要生成 → L0 全局图谱构建'}</p>
          </div>
        )}
      </div>
    </div>
  )
}
