import { useState } from 'react'
import type { AgentEvent } from '../../types/agent'
import { EventBlock } from './EventBlock'
import { ThinkingBlock } from './ThinkingBlock'
import { DetailModal } from './DetailModal'
import WorkflowBlock from './WorkflowBlock'

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

  // Separate workflow events from regular action events
  const workflowEvents = actionEvents.filter(e => e.type === 'workflow_result')
  const regularActions = actionEvents.filter(e => e.type !== 'workflow_result')

  const totalEvents = thinkingEvents.length + actionEvents.length
  if (totalEvents === 0) return null

  return (
    <div className="agent-loop-display">
      {/* CoT 思维链面板 */}
      {thinkingEvents.length > 0 && (
        <div className="agent-loop__section">
          <div className="agent-loop__section-header">
            <span className="agent-loop__label agent-loop__label--purple">
              推理过程 ({thinkingEvents.length})
            </span>
          </div>
          <div className="agent-loop__event-list agent-loop__event-list--tight">
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

      {/* 工作流事件 */}
      {workflowEvents.length > 0 && (
        <div className="agent-loop__section">
          <div className="agent-loop__section-header">
            <span className="agent-loop__label agent-loop__label--cyan">
              工作流 ({workflowEvents.length})
            </span>
          </div>
          <div className="agent-loop__event-list agent-loop__event-list--tight">
            {workflowEvents.map(event => (
              <WorkflowBlock
                key={event.id}
                event={event}
                expanded={expandedActions.has(event.id)}
                onToggle={() => toggleAction(event.id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* 工具调用 / 动作事件列表 */}
      {regularActions.length > 0 && (
        <div className="agent-loop__section">
          <div className="agent-loop__section-header">
            <span className="agent-loop__label agent-loop__label--amber">
              工具调用 ({regularActions.length})
            </span>
          </div>
          <div className="agent-loop__event-list">
            {regularActions.map(event => (
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
          className="agent-loop__clear-btn"
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
