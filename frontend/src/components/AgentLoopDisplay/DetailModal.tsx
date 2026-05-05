import type { AgentEvent } from '../../types/agent'

interface DetailModalProps {
  event: AgentEvent
  onClose: () => void
}

// 事件类型标签配置
const EVENT_LABELS: Record<AgentEvent['type'], string> = {
  thinking: '思考过程',
  tool_call: '工具调用',
  tool_result: '工具结果',
  retrieval_hit: '检索命中',
  decision: '决策',
  ask_user: '询问用户',
  final_answer: '最终答案',
  error: '错误',
  intent_analysis: '意图分析',
  reflection: '反思评估',
  turn_summary: '轮次总结',
  phase: '阶段切换',
  progress: '进度更新',
  context_update: '上下文更新',
  workflow_result: '工作流结果'
}

export function DetailModal({ event, onClose }: DetailModalProps) {
  // 格式化时间戳
  const formatTime = (ts: number) => {
    const date = new Date(ts)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  }

  // 格式化持续时间
  const formatDuration = (ms?: number) => {
    if (!ms) return 'N/A'
    if (ms < 1000) return `${ms}ms`
    if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`
    return `${(ms / 60000).toFixed(1)}m ${((ms % 60000) / 1000).toFixed(0)}s`
  }

  // 获取完整 JSON
  const getFullJson = () => {
    return JSON.stringify(event, null, 2)
  }

  const levelClass = event.level === 'L0'
    ? 'detail-modal__level--l0'
    : event.level === 'L1'
    ? 'detail-modal__level--l1'
    : 'detail-modal__level--l2'

  const confidenceClass = event.confidence === 'EXTRACTED'
    ? 'detail-modal__confidence--extracted'
    : event.confidence === 'INFERRED'
    ? 'detail-modal__confidence--inferred'
    : 'detail-modal__confidence--default'

  return (
    <div className="detail-modal__overlay">
      {/* 背景遮罩 */}
      <div className="detail-modal__backdrop" onClick={onClose} />

      {/* 模态框 */}
      <div className="detail-modal__dialog">
        {/* 头部 */}
        <div className="detail-modal__header">
          <div className="detail-modal__header-left">
            <h3 className="detail-modal__title">事件详情</h3>
            <span className="detail-modal__type-badge">{EVENT_LABELS[event.type]}</span>
          </div>
          <button onClick={onClose} className="detail-modal__close-btn">
            <svg className="detail-modal__close-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 内容 */}
        <div className="detail-modal__body">
          {/* 基本信息 */}
          <div className="detail-modal__grid-2col">
            <div className="detail-modal__info-cell">
              <p className="detail-modal__info-label">ID</p>
              <p className="detail-modal__info-value detail-modal__info-value--mono">{event.id}</p>
            </div>
            <div className="detail-modal__info-cell">
              <p className="detail-modal__info-label">时间戳</p>
              <p className="detail-modal__info-value detail-modal__info-value--mono">{formatTime(event.timestamp)}</p>
            </div>
            <div className="detail-modal__info-cell">
              <p className="detail-modal__info-label">类型</p>
              <p className="detail-modal__info-value">{event.type}</p>
            </div>
            <div className="detail-modal__info-cell">
              <p className="detail-modal__info-label">持续时间</p>
              <p className="detail-modal__info-value detail-modal__info-value--mono">{formatDuration(event.duration_ms)}</p>
            </div>
          </div>

          {/* Content */}
          {event.content && (
            <div className="detail-modal__info-cell">
              <p className="detail-modal__info-label">内容</p>
              <p className="detail-modal__info-value detail-modal__info-value--prewrap">{event.content}</p>
            </div>
          )}

          {/* 工具名称 */}
          {event.tool_name && (
            <div className="detail-modal__tool-name-cell">
              <p className="detail-modal__tool-name-label">工具名称</p>
              <p className="detail-modal__tool-name-value">{event.tool_name}</p>
            </div>
          )}

          {/* 工具参数 */}
          {event.tool_args && (
            <div className="detail-modal__info-cell">
              <p className="detail-modal__info-label">工具参数</p>
              <pre className="detail-modal__pre-block">
                {JSON.stringify(event.tool_args, null, 2)}
              </pre>
            </div>
          )}

          {/* 工具结果 */}
          {event.tool_result !== undefined && (
            <div className="detail-modal__result-cell">
              <p className="detail-modal__result-label">工具结果</p>
              <pre className="detail-modal__result-pre">
                {typeof event.tool_result === 'string'
                  ? event.tool_result
                  : JSON.stringify(event.tool_result, null, 2)}
              </pre>
            </div>
          )}

          {/* Level */}
          {event.level && (
            <div className="detail-modal__inline-field">
              <span className="detail-modal__info-label">层级：</span>
              <span className={`detail-modal__level-badge ${levelClass}`}>
                {event.level}
              </span>
            </div>
          )}

          {/* Confidence */}
          {event.confidence && (
            <div className="detail-modal__inline-field">
              <span className="detail-modal__info-label">置信度：</span>
              <span className={`detail-modal__confidence-badge ${confidenceClass}`}>
                {event.confidence}
              </span>
            </div>
          )}

          {/* Relevance Score */}
          {event.relevance_score !== undefined && (
            <div className="detail-modal__relevance-cell">
              <p className="detail-modal__relevance-label">相关度得分</p>
              <p className="detail-modal__relevance-value">
                {event.relevance_score.toFixed(4)}
              </p>
            </div>
          )}

          {/* Drill Path */}
          {event.drill_path && event.drill_path.length > 0 && (
            <div className="detail-modal__info-cell">
              <p className="detail-modal__info-label detail-modal__info-label--mb2">检索路径</p>
              <div className="detail-modal__drill-path-list">
                {event.drill_path.map((step, i) => (
                  <span key={i} className="detail-modal__drill-step">
                    <span className="detail-modal__drill-step-badge">{step}</span>
                    {i < event.drill_path!.length - 1 && (
                      <span className="detail-modal__drill-arrow">&rarr;</span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 完整 JSON */}
          <div className="detail-modal__json-cell">
            <p className="detail-modal__info-label">完整 JSON</p>
            <pre className="detail-modal__json-pre">
              {getFullJson()}
            </pre>
          </div>
        </div>

        {/* 底部 */}
        <div className="detail-modal__footer">
          <button onClick={onClose} className="detail-modal__close-btn-main">
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}
