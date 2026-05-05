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

  const borderVariant = isCall ? 'tool-card--call' : 'tool-card--result'

  const levelClass = event.level === 'L0'
    ? 'tool-card__level--l0'
    : event.level === 'L1'
    ? 'tool-card__level--l1'
    : 'tool-card__level--l2'

  return (
    <div className={`tool-card ${borderVariant}`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className={`tool-card__header-btn ${isCall ? 'tool-card__header-btn--call' : 'tool-card__header-btn--result'}`}
      >
        <IconComp className="tool-card__icon" />
        <span className="tool-card__label">{label}</span>

        {/* Level 标签 */}
        {event.level && (
          <span className={`tool-card__level-badge ${levelClass}`}>
            {event.level}
          </span>
        )}

        {event.duration_ms && (
          <span className="tool-card__duration">
            {formatDuration(event.duration_ms)}
          </span>
        )}

        <span className={`tool-card__chevron ${expanded ? 'tool-card__chevron--expanded' : ''}`}>&#9656;</span>
      </button>

      {expanded && (
        <div className="tool-card__expanded">
          {inputPreview && (
            <div className="tool-card__field-cell">
              <span className="tool-card__field-label">输入：</span>
              <code className="tool-card__field-code">{inputPreview}</code>
            </div>
          )}
          {outputPreview && (
            <div className="tool-card__field-cell">
              <span className="tool-card__field-label">输出：</span>
              <p className="tool-card__field-output">
                {outputPreview}
                {(typeof event.tool_result === 'string' ? event.tool_result.length : JSON.stringify(event.tool_result || '').length) > 100 ? '...' : ''}
              </p>
            </div>
          )}

          {/* Drill Path */}
          {event.drill_path && event.drill_path.length > 0 && (
            <div className="tool-card__field-cell">
              <span className="tool-card__field-label">检索路径：</span>
              <div className="tool-card__drill-list">
                {event.drill_path.map((step, i) => (
                  <span key={i} className="tool-card__drill-step">
                    <span className="tool-card__drill-badge">{step}</span>
                    {i < event.drill_path!.length - 1 && <span className="tool-card__drill-arrow">&rarr;</span>}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Relevance Score */}
          {event.relevance_score !== undefined && (
            <div className="tool-card__field-cell">
              <span className="tool-card__field-label">相关度：</span>
              <span className="tool-card__relevance-score">
                {event.relevance_score.toFixed(3)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
