interface ReflectionEvent {
  confidence: number
  answered_aspects: string[]
  missing_aspects: string[]
  next_query: string
  evidence_strength: string
  iteration: number
}

const STRENGTH_CONFIG: Record<string, { label: string; cls: string }> = {
  strong: { label: '强', cls: 'reflection-block__strength--strong' },
  partial: { label: '部分', cls: 'reflection-block__strength--partial' },
  weak:   { label: '弱', cls: 'reflection-block__strength--weak' },
  none:   { label: '无', cls: 'reflection-block__strength--none' },
}

export function ReflectionBlock({ event }: { event: ReflectionEvent }) {
  const strength = STRENGTH_CONFIG[event.evidence_strength] || STRENGTH_CONFIG.none
  const pct = Math.round(event.confidence * 100)
  const pctClass = pct >= 80
    ? 'reflection-block__pct--high'
    : pct >= 50
    ? 'reflection-block__pct--mid'
    : 'reflection-block__pct--low'

  const barClass = pct >= 80
    ? 'reflection-block__bar-fill--high'
    : pct >= 50
    ? 'reflection-block__bar-fill--mid'
    : 'reflection-block__bar-fill--low'

  return (
    <div className="reflection-block">
      <div className="reflection-block__header">
        <span className="reflection-block__title">自我评估 (第{event.iteration}轮)</span>
        <div className="reflection-block__badges">
          <span className={`reflection-block__strength-badge ${strength.cls}`}>证据: {strength.label}</span>
          <span className={`reflection-block__pct ${pctClass}`}>{pct}%</span>
        </div>
      </div>
      <div className="reflection-block__bar">
        <div className={`reflection-block__bar-fill ${barClass}`} style={{ width: `${pct}%` }} />
      </div>
      {event.answered_aspects.length > 0 && (
        <div className="reflection-block__answered">
          已解答: {event.answered_aspects.join(', ')}
        </div>
      )}
      {event.missing_aspects.length > 0 && (
        <div className="reflection-block__missing">
          缺失: {event.missing_aspects.join(', ')}
        </div>
      )}
    </div>
  )
}
