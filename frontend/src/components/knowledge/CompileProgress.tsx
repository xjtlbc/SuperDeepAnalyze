import { useEffect, useState, useRef } from 'react'

interface ProgressData {
  type: string
  phase: string
  progress: number
  message: string
}

const PHASES = [
  { key: 'parsing', label: '解析', color: '#4c6ef5' },
  { key: 'compiling_l2', label: 'L2索引', color: '#2f9e44' },
  { key: 'compiling_l1', label: 'L1摘要', color: '#7950f2' },
  { key: 'merging_entities', label: '实体合并', color: '#e8590c' },
  { key: 'done', label: '完成', color: '#10b981' },
]

export function CompileProgress({ kbId, onComplete }: { kbId: string; onComplete?: () => void }) {
  const [progress, setProgress] = useState(0)
  const [phase, setPhase] = useState('')
  const [message, setMessage] = useState('')
  const [done, setDone] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const ws = new WebSocket(`${proto}//${host}/api/compile/ws/${kbId}`)
    wsRef.current = ws

    ws.onmessage = (e) => {
      try {
        const data: ProgressData = JSON.parse(e.data)
        if (data.type === 'done' || data.type === 'error') {
          setDone(true)
          setProgress(100)
          onComplete?.()
          ws.close()
        } else {
          setProgress(data.progress || 0)
          setPhase(data.phase || '')
          setMessage(data.message || '')
        }
      } catch {}
    }

    ws.onerror = () => { setDone(true) }
    ws.onclose = () => { wsRef.current = null }

    return () => { ws.close() }
  }, [kbId, onComplete])

  const activeIdx = PHASES.findIndex(p => phase.startsWith(p.key))
  const activePhase = activeIdx >= 0 ? PHASES[activeIdx].key : ''

  if (done && progress >= 100) {
    return (
      <div style={{ padding: '16px 0', textAlign: 'center' }}>
        <div style={{ width: 40, height: 40, borderRadius: '50%', background: '#10b981', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', marginBottom: 8 }}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="#fff" strokeWidth="2">
            <path d="M5 10l3 3 7-7" />
          </svg>
        </div>
        <p style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)', margin: 0 }}>编译已完成</p>
      </div>
    )
  }

  return (
    <div style={{ padding: '16px 0' }}>
      {/* Phase bar */}
      <div style={{ display: 'flex', marginBottom: 12 }}>
        {PHASES.map((p, i) => (
          <div key={p.key} style={{ flex: 1, display: 'flex', alignItems: 'center' }}>
            <div style={{
              width: 24, height: 24, borderRadius: '50%',
              background: activeIdx >= i ? p.color : 'var(--bg-tertiary)',
              color: activeIdx >= i ? '#fff' : 'var(--text-muted)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, fontWeight: 600, margin: '0 auto',
              transition: 'background 0.3s ease',
            }}>
              {activeIdx > i ? '✓' : i + 1}
            </div>
            {i < PHASES.length - 1 && (
              <div style={{
                flex: 1, height: 2,
                background: activeIdx > i ? p.color : 'var(--bg-tertiary)',
                transition: 'background 0.3s ease',
              }} />
            )}
          </div>
        ))}
      </div>

      {/* Phase labels */}
      <div style={{ display: 'flex', marginBottom: 12 }}>
        {PHASES.map(p => (
          <div key={p.key} style={{
            flex: 1, textAlign: 'center', fontSize: 11,
            color: activePhase === p.key || activeIdx > PHASES.findIndex(x => x.key === p.key)
              ? p.color : 'var(--text-muted)',
            fontWeight: activePhase === p.key ? 600 : 400,
          }}>
            {p.label}
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div style={{ height: 6, background: 'var(--bg-tertiary)', borderRadius: 3, overflow: 'hidden', marginBottom: 8 }}>
        <div style={{
          height: '100%', width: `${Math.min(progress, 100)}%`,
          background: `linear-gradient(90deg, #4c6ef5, #10b981)`,
          borderRadius: 3, transition: 'width 0.5s ease',
        }} />
      </div>

      {/* Message */}
      <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: 0, textAlign: 'center' }}>
        {message || '准备中...'}
      </p>
    </div>
  )
}
