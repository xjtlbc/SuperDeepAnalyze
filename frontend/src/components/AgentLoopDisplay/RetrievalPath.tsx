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

  const nodeLevelClass = (level: string | null) => {
    if (level === 'L0') return 'retrieval-path__node--l0'
    if (level === 'L1') return 'retrieval-path__node--l1'
    if (level === 'L2') return 'retrieval-path__node--l2'
    return 'retrieval-path__node--default'
  }

  const confidenceClass = event.confidence === 'EXTRACTED'
    ? 'retrieval-path__conf--extracted'
    : event.confidence === 'INFERRED'
    ? 'retrieval-path__conf--inferred'
    : 'retrieval-path__conf--default'

  return (
    <div className="retrieval-path">
      {/* 头部 */}
      <div className="retrieval-path__header">
        <SearchIcon className="retrieval-path__icon" />
        <span className="retrieval-path__title">检索路径</span>
        {event.relevance_score !== undefined && (
          <span className="retrieval-path__score">
            得分: {event.relevance_score.toFixed(3)}
          </span>
        )}
      </div>

      {/* 路径节点 */}
      <div className="retrieval-path__nodes">
        {event.drill_path.map((node, i) => {
          const parsed = parsePathNode(node)
          return (
            <div key={i} className="retrieval-path__node-wrap">
              {/* 节点卡片 */}
              <div className={`retrieval-path__node ${nodeLevelClass(parsed.level)}`}>
                {parsed.level && (
                  <span className="retrieval-path__node-level">{parsed.level}</span>
                )}
                <span className="retrieval-path__node-content">{parsed.content}</span>
              </div>

              {/* 连接箭头 */}
              {i < event.drill_path!.length - 1 && (
                <svg className="retrieval-path__arrow" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              )}
            </div>
          )
        })}
      </div>

      {/* Confidence */}
      {event.confidence && (
        <div className="retrieval-path__conf-row">
          <span className="retrieval-path__conf-label">置信度：</span>
          <span className={`retrieval-path__conf-badge ${confidenceClass}`}>
            {event.confidence}
          </span>
        </div>
      )}
    </div>
  )
}
