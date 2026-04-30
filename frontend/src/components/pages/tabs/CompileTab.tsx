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
    <div className="h-full overflow-y-auto">
      <div className="max-w-2xl mx-auto">
        {isPaused ? (
          <button onClick={handleCompile} className="w-full px-6 py-4 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-lg font-medium transition-colors">
            继续编译 (从断点恢复)
          </button>
        ) : (
          <button
            onClick={compiling ? handlePause : handleCompile}
            disabled={!compiling && false}
            className={`w-full px-6 py-4 rounded-xl text-lg font-medium transition-colors ${
              compiling ? 'bg-orange-600 hover:bg-orange-700 text-white' : 'bg-amber-600 hover:bg-amber-700 text-white'
            }`}
          >
            {compiling ? <><PauseIcon className="w-4 h-4 inline-block mr-1" />暂停编译</> : '一键编译全部 (L0/L1/L2)'}
          </button>
        )}

        {compiling && compileProgress && (
          <div className="mt-4 p-4 bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700">
            {/* Stage indicators */}
            <div className="flex items-center justify-between mb-3">
              {stages.map((stage, idx) => (
                <div key={stage.key} className="flex flex-col items-center flex-1">
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                    idx < currentStageIndex ? 'bg-green-500 text-white' :
                    idx === currentStageIndex ? 'bg-amber-500 text-white animate-pulse' :
                    'bg-stone-200 dark:bg-slate-600 text-stone-400'
                  }`}>
                    {idx < currentStageIndex ? '✓' : idx + 1}
                  </div>
                  <span className={`text-xs mt-1 ${
                    idx <= currentStageIndex ? 'text-stone-700 dark:text-stone-200' : 'text-stone-400'
                  }`}>{stage.label}</span>
                </div>
              ))}
            </div>

            {/* Current phase message */}
            <div className="flex items-center gap-2 text-sm mb-2">
              {(() => { const IconComp = phaseIconMap[compileProgress.phase] || InfoIcon; return <IconComp className="w-5 h-5" /> })()}
              <span className="text-stone-600 dark:text-stone-300 font-medium">{compileProgress.message}</span>
              <span className="ml-auto text-amber-600 dark:text-amber-400 font-mono text-sm">{compileProgress.progress}%</span>
            </div>

            {/* Progress bar */}
            <div className="w-full bg-stone-200 dark:bg-slate-700 rounded-full h-2.5 overflow-hidden">
              <div className="h-full bg-gradient-to-r from-amber-400 to-amber-600 rounded-full transition-all duration-500 ease-out" style={{ width: `${compileProgress.progress}%` }} />
            </div>
          </div>
        )}

        {compileLog.length > 0 && (
          <div className="mt-4 bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700 overflow-hidden">
            <div className="px-3 py-2 bg-stone-50 dark:bg-slate-700/50 border-b border-stone-200 dark:border-slate-700 flex items-center justify-between">
              <span className="text-xs font-medium text-stone-500 dark:text-stone-400">编译日志</span>
              <span className="text-xs text-stone-400 dark:text-stone-500">{compileLog.length} 条</span>
            </div>
            <div className="max-h-64 overflow-y-auto p-2 space-y-1 text-xs">
              {compileLog.map((log, i) => (
                <div key={i} className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-stone-50 dark:hover:bg-slate-700/30">
                  <span className="text-stone-400 dark:text-stone-500 font-mono w-16 flex-shrink-0">{log.time}</span>
                  {(() => { const IconComp = phaseIconMap[log.phase] || InfoIcon; return <IconComp className="w-3.5 h-3.5" /> })()}
                  <span className={`px-1.5 py-0.5 rounded text-xs font-medium flex-shrink-0 ${
                    log.phase.includes('l0') ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400' :
                    log.phase.includes('l1') ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                    log.phase.includes('l2') ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' :
                    log.phase === 'done' ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' :
                    'bg-stone-100 text-stone-600 dark:bg-slate-700 dark:text-stone-400'
                  }`}>{phaseLabels[log.phase] || log.phase}</span>
                  <span className="text-stone-600 dark:text-stone-300 flex-1 truncate">{log.message}</span>
                  <span className="text-stone-400 dark:text-stone-500 font-mono w-10 text-right">{log.progress}%</span>
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>
        )}

        {compileResult && (
          <div className={`mt-4 p-4 rounded-lg text-sm ${compileResult.includes('完成') ? 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400 border border-green-200 dark:border-green-800' : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400 border border-red-200 dark:border-red-800'}`}>
            {compileResult}
          </div>
        )}

        {!compiling && !compileResult && (
          <div className="mt-8 text-center">
            <CompileIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
            <p className="text-stone-500 dark:text-stone-400">点击按钮开始编译</p>
            <p className="text-xs text-stone-400 dark:text-stone-500 mt-1">编译将执行 L2 分段索引 → L1 摘要生成 → L0 全局图谱构建</p>
          </div>
        )}
      </div>
    </div>
  )
}
