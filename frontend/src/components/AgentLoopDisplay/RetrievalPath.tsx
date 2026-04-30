import type { AgentEvent } from '../../types/agent'
import { SearchIcon } from '../Icons'

interface RetrievalPathProps {
  event: AgentEvent
}

export function RetrievalPath({ event }: RetrievalPathProps) {
  if (!event.drill_path || event.drill_path.length === 0) return null

  // 解析路径节点信息
  const parsePathNode = (node: string) => {
    // 尝试解析 L0/L1/L2 标记
    const levelMatch = node.match(/^(L[0-2])[:\s]/)
    if (levelMatch) {
      return {
        level: levelMatch[1],
        content: node.replace(levelMatch[0], '').trim()
      }
    }
    return { level: null, content: node }
  }

  return (
    <div className="retrieval-path bg-gradient-to-r from-amber-50 to-blue-50 dark:from-amber-900/10 dark:to-blue-900/10 rounded-lg p-3 border border-amber-200 dark:border-amber-800">
      {/* 头部 */}
      <div className="flex items-center gap-2 mb-2">
        <SearchIcon className="w-5 h-5" />
        <span className="text-xs font-medium text-amber-600 dark:text-amber-400">
          检索路径
        </span>
        {event.relevance_score !== undefined && (
          <span className="ml-auto text-xs font-mono text-blue-600 dark:text-blue-400">
            得分: {event.relevance_score.toFixed(3)}
          </span>
        )}
      </div>

      {/* 路径节点 */}
      <div className="flex items-start gap-1 overflow-x-auto pb-1">
        {event.drill_path.map((node, i) => {
          const parsed = parsePathNode(node)
          return (
            <div key={i} className="flex items-center gap-1 flex-shrink-0">
              {/* 节点卡片 */}
              <div className={`px-2 py-1 rounded-lg text-xs ${
                parsed.level === 'L0'
                  ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 border border-blue-200 dark:border-blue-800'
                  : parsed.level === 'L1'
                  ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800'
                  : parsed.level === 'L2'
                  ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400 border border-purple-200 dark:border-purple-800'
                  : 'bg-stone-100 dark:bg-slate-700 text-stone-700 dark:text-stone-400 border border-stone-200 dark:border-slate-600'
              }`}>
                {parsed.level && (
                  <span className="font-mono font-bold mr-1">{parsed.level}</span>
                )}
                <span className="truncate max-w-24">{parsed.content}</span>
              </div>

              {/* 连接箭头 */}
              {i < event.drill_path!.length - 1 && (
                <svg className="w-4 h-4 text-amber-400 dark:text-amber-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              )}
            </div>
          )
        })}
      </div>

      {/* Confidence */}
      {event.confidence && (
        <div className="mt-2 flex items-center gap-2">
          <span className="text-xs text-stone-500 dark:text-stone-400">置信度：</span>
          <span className={`px-2 py-0.5 rounded text-xs ${
            event.confidence === 'EXTRACTED'
              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
              : event.confidence === 'INFERRED'
              ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
              : 'bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400'
          }`}>
            {event.confidence}
          </span>
        </div>
      )}
    </div>
  )
}