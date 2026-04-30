import { useState } from 'react'
import type { AgentEvent } from '../../types/agent'
import { SearchIcon, DatabaseIcon, FileTextIcon, DocumentIcon, ExternalLinkIcon, ClockIcon, PlayIcon } from '../Icons'

interface ToolCallCardProps {
  event: AgentEvent
}

const TOOL_ICON_MAP: Record<string, React.ComponentType<{className?: string}>> = {
  search_vector: SearchIcon,
  search_keyword: SearchIcon,
  read_l0: DatabaseIcon,
  read_l1: FileTextIcon,
  read_l2: DocumentIcon,
  expand_entity: ExternalLinkIcon,
  get_timeline: ClockIcon,
}

const TOOL_LABELS: Record<string, string> = {
  search_vector: '向量搜索',
  search_keyword: '关键词搜索',
  read_l0: '读取 L0 全局',
  read_l1: '读取 L1 摘要',
  read_l2: '读取 L2 原文',
  expand_entity: '展开实体链',
  get_timeline: '查询时间线'
}

export function ToolCallCard({ event }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false)

  if (event.type !== 'tool_call' && event.type !== 'tool_result') return null

  const isCall = event.type === 'tool_call'
  const IconComp = isCall
    ? (TOOL_ICON_MAP[event.tool_name || ''] || PlayIcon)
    : FileTextIcon
  const label = isCall
    ? (TOOL_LABELS[event.tool_name || ''] || event.tool_name || '未知工具')
    : '工具结果'

  const formatDuration = (ms?: number) => {
    if (!ms) return null
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  const inputPreview = event.tool_args
    ? JSON.stringify(event.tool_args).slice(0, 80)
    : ''

  const outputPreview = event.tool_result
    ? (typeof event.tool_result === 'string'
        ? event.tool_result
        : JSON.stringify(event.tool_result)).slice(0, 100)
    : ''

  const borderColor = isCall ? 'border-amber-400' : 'border-green-400'

  return (
    <div className={`border-l-2 ${borderColor} pl-3 py-1.5`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className={`flex items-center gap-2 text-xs ${
          isCall
            ? 'text-amber-600 dark:text-amber-400'
            : 'text-green-600 dark:text-green-400'
        } hover:text-amber-700 dark:hover:text-amber-300 transition-colors w-full text-left`}
      >
        <IconComp className="w-4 h-4" />
        <span className="font-medium">{label}</span>

        {/* Level 标签 */}
        {event.level && (
          <span className={`px-1.5 py-0.5 rounded text-xs font-mono ${
            event.level === 'L0' ? 'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400' :
            event.level === 'L1' ? 'bg-green-50 text-green-600 dark:bg-green-900/20 dark:text-green-400' :
            'bg-purple-50 text-purple-600 dark:bg-purple-900/20 dark:text-purple-400'
          }`}>
            {event.level}
          </span>
        )}

        {event.duration_ms && (
          <span className="text-stone-400 dark:text-stone-500 ml-auto">
            {formatDuration(event.duration_ms)}
          </span>
        )}

        <span className={`text-stone-400 ml-auto transition-transform ${expanded ? 'rotate-90' : ''}`}>▸</span>
      </button>

      {expanded && (
        <div className="mt-2 space-y-1 text-xs">
          {inputPreview && (
            <div className="bg-stone-100 dark:bg-slate-700 rounded px-2 py-1.5">
              <span className="text-stone-500 dark:text-stone-400">输入：</span>
              <code className="text-stone-700 dark:text-stone-300">{inputPreview}</code>
            </div>
          )}
          {outputPreview && (
            <div className="bg-stone-100 dark:bg-slate-700 rounded px-2 py-1.5">
              <span className="text-stone-500 dark:text-stone-400">输出：</span>
              <p className="text-stone-700 dark:text-stone-300 mt-1 whitespace-pre-wrap">
                {outputPreview}
                {(typeof event.tool_result === 'string' ? event.tool_result.length : JSON.stringify(event.tool_result || '').length) > 100 ? '...' : ''}
              </p>
            </div>
          )}

          {/* Drill Path */}
          {event.drill_path && event.drill_path.length > 0 && (
            <div className="bg-stone-100 dark:bg-slate-700 rounded px-2 py-1.5">
              <span className="text-stone-500 dark:text-stone-400">检索路径：</span>
              <div className="flex items-center gap-1 mt-1 flex-wrap">
                {event.drill_path.map((step, i) => (
                  <span key={i} className="flex items-center gap-1">
                    <span className="px-1.5 py-0.5 bg-amber-100 dark:bg-amber-900/30 rounded text-amber-600 dark:text-amber-400 font-mono">
                      {step}
                    </span>
                    {i < event.drill_path!.length - 1 && <span className="text-stone-400">→</span>}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Relevance Score */}
          {event.relevance_score !== undefined && (
            <div className="bg-stone-100 dark:bg-slate-700 rounded px-2 py-1.5">
              <span className="text-stone-500 dark:text-stone-400">相关度：</span>
              <span className="ml-2 font-mono text-amber-600 dark:text-amber-400">
                {event.relevance_score.toFixed(3)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}