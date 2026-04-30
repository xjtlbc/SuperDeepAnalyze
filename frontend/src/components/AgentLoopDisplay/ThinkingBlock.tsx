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
    <div className="border-l-2 border-purple-400 pl-3 py-1.5">
      <button
        onClick={onToggle}
        className="flex items-center gap-2 text-xs text-purple-600 dark:text-purple-400 hover:text-purple-700 dark:hover:text-purple-300 transition-colors w-full text-left"
      >
        <InfoIcon className="w-4 h-4" />
        <span className="font-medium">思考过程</span>
        <span className={`text-purple-400 ml-auto transition-transform ${expanded ? 'rotate-90' : ''}`}>▸</span>
      </button>

      {expanded && event.content && (
        <div className="mt-2 bg-purple-50 dark:bg-purple-900/20 rounded px-3 py-2 border border-purple-200 dark:border-purple-800">
          <p className="text-xs text-purple-700 dark:text-purple-300 whitespace-pre-wrap leading-relaxed">
            {event.content}
          </p>
        </div>
      )}
    </div>
  )
}