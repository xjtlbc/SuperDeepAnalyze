import { useState } from 'react'
import type { AgentEvent } from '../../types/agent'
import { EventBlock } from './EventBlock'
import { ThinkingBlock } from './ThinkingBlock'
import { DetailModal } from './DetailModal'

interface AgentLoopDisplayProps {
  thinkingEvents: AgentEvent[]
  actionEvents: AgentEvent[]
  onClear?: () => void
}

export function AgentLoopDisplay({ thinkingEvents, actionEvents, onClear }: AgentLoopDisplayProps) {
  const [expandedThinkings, setExpandedThinkings] = useState<Set<string>>(new Set())
  const [expandedActions, setExpandedActions] = useState<Set<string>>(new Set())
  const [selectedEvent, setSelectedEvent] = useState<AgentEvent | null>(null)

  const toggleThinking = (id: string) => {
    setExpandedThinkings(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAction = (id: string) => {
    setExpandedActions(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const totalEvents = thinkingEvents.length + actionEvents.length
  if (totalEvents === 0) return null

  return (
    <div className="agent-loop-display space-y-3">
      {/* CoT 思维链面板 */}
      {thinkingEvents.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-medium text-purple-600 dark:text-purple-400">
              推理过程 ({thinkingEvents.length})
            </span>
          </div>
          <div className="space-y-1">
            {thinkingEvents.map((event) => (
              <ThinkingBlock
                key={event.id}
                event={event}
                expanded={expandedThinkings.has(event.id)}
                onToggle={() => toggleThinking(event.id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* 工具调用 / 动作事件列表 */}
      {actionEvents.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-medium text-amber-600 dark:text-amber-400">
              工具调用 ({actionEvents.length})
            </span>
          </div>
          <div className="space-y-1.5">
            {actionEvents.map(event => (
              <EventBlock
                key={event.id}
                event={event}
                expanded={expandedActions.has(event.id)}
                onToggle={() => toggleAction(event.id)}
                onShowDetail={() => setSelectedEvent(event)}
              />
            ))}
          </div>
        </div>
      )}

      {/* 清除按钮 */}
      {onClear && (
        <button
          onClick={onClear}
          className="text-xs text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 transition-colors"
        >
          清除事件流
        </button>
      )}

      {/* 详情模态框 */}
      {selectedEvent && (
        <DetailModal
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      )}
    </div>
  )
}
