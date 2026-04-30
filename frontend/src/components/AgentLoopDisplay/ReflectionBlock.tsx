interface ReflectionEvent {
  confidence: number
  answered_aspects: string[]
  missing_aspects: string[]
  next_query: string
  evidence_strength: string
  iteration: number
}

const STRENGTH_LABELS: Record<string, { label: string; color: string }> = {
  strong: { label: '强', color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' },
  partial: { label: '部分', color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' },
  weak: { label: '弱', color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' },
  none: { label: '无', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
}

export function ReflectionBlock({ event }: { event: ReflectionEvent }) {
  const strength = STRENGTH_LABELS[event.evidence_strength] || STRENGTH_LABELS.none
  const pct = Math.round(event.confidence * 100)

  return (
    <div className="px-3 py-2 my-1 bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-200 dark:border-slate-700 text-xs">
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-medium text-slate-600 dark:text-slate-300">自我评估 (第{event.iteration}轮)</span>
        <div className="flex items-center gap-2">
          <span className={`px-1.5 py-0.5 rounded ${strength.color}`}>证据: {strength.label}</span>
          <span className={`font-mono font-bold ${pct >= 80 ? 'text-green-600 dark:text-green-400' : pct >= 50 ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400'}`}>
            {pct}%
          </span>
        </div>
      </div>
      <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-1.5 mb-1.5">
        <div
          className={`h-full rounded-full transition-all ${pct >= 80 ? 'bg-green-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {event.answered_aspects.length > 0 && (
        <div className="text-slate-500 dark:text-slate-400 mb-1">
          已解答: {event.answered_aspects.join(', ')}
        </div>
      )}
      {event.missing_aspects.length > 0 && (
        <div className="text-amber-600 dark:text-amber-400">
          缺失: {event.missing_aspects.join(', ')}
        </div>
      )}
    </div>
  )
}
