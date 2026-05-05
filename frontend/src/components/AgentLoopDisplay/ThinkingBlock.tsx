import { InfoIcon } from '../Icons'
import type { AgentEvent } from '../../types/agent'

interface ThinkingBlockProps {
  event: AgentEvent
  expanded: boolean
  onToggle: () => void
}

export function ThinkingBlock({ event, expanded, onToggle }: ThinkingBlockProps) {
  if (event.type !== 'thinking') return null

  return (
    <div className="thinking-block">
      <button onClick={onToggle} className="thinking-block__toggle">
        <InfoIcon className="thinking-block__icon" />
        <span className="thinking-block__label">思考过程</span>
        <span className={`thinking-block__chevron ${expanded ? 'thinking-block__chevron--expanded' : ''}`}>&#9656;</span>
      </button>

      {expanded && event.content && (
        <div className="thinking-block__content">
          <p className="thinking-block__text">
            {event.content}
          </p>
        </div>
      )}
    </div>
  )
}
