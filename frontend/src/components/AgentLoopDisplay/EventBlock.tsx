import type { AgentEvent } from '../../types/agent'
import { SearchIcon, DatabaseIcon, FileTextIcon, DocumentIcon, ExternalLinkIcon, ClockIcon, InfoIcon, PlayIcon, CheckCircleIcon, ChatIcon, CheckIcon, AlertCircleIcon, ArrowRightIcon, SettingsIcon } from '../Icons'

interface EventBlockProps {
  event: AgentEvent
  expanded: boolean
  onToggle: () => void
  onShowDetail: () => void
}

// 事件图标映射
const EVENT_ICON_MAP: Record<string, React.ComponentType<{className?: string}>> = {
  thinking: InfoIcon,
  tool_call: PlayIcon,
  tool_result: CheckCircleIcon,
  retrieval_hit: SearchIcon,
  decision: ArrowRightIcon,
  ask_user: ChatIcon,
  final_answer: CheckIcon,
  error: AlertCircleIcon,
  intent_analysis: SearchIcon,
  reflection: CheckCircleIcon,
  turn_summary: InfoIcon,
  phase: InfoIcon,
  progress: InfoIcon,
  context_update: SettingsIcon,
  workflow_result: ArrowRightIcon,
}

// 事件类型配置 — maps to BEM modifier classes
const EVENT_CONFIG: Record<string, { label: string; cls: string }> = {
  thinking:        { label: '思考',     cls: 'event-block--purple' },
  tool_call:       { label: '工具调用',  cls: 'event-block--amber' },
  tool_result:     { label: '工具结果',  cls: 'event-block--green' },
  retrieval_hit:   { label: '检索命中',  cls: 'event-block--blue' },
  decision:        { label: '决策',     cls: 'event-block--indigo' },
  ask_user:        { label: '询问用户',  cls: 'event-block--orange' },
  final_answer:    { label: '最终答案',  cls: 'event-block--emerald' },
  error:           { label: '错误',     cls: 'event-block--red' },
  intent_analysis: { label: '意图分析',  cls: 'event-block--cyan' },
  reflection:      { label: '自我评估',  cls: 'event-block--teal' },
  turn_summary:    { label: '轮次总结',  cls: 'event-block--slate' },
  phase:           { label: '阶段切换',  cls: 'event-block--purple' },
  progress:        { label: '进度',     cls: 'event-block--blue' },
  context_update:  { label: '上下文管理', cls: 'event-block--gray' },
  workflow_result: { label: '工作流',   cls: 'event-block--cyan' },
}

// 工具图标映射
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

export function EventBlock({ event, expanded, onToggle, onShowDetail }: EventBlockProps) {
  const config = EVENT_CONFIG[event.type]

  // 格式化时间戳
  const formatTime = (ts: number) => {
    const date = new Date(ts)
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  // 格式化持续时间
  const formatDuration = (ms?: number) => {
    if (!ms) return null
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  // 获取预览内容
  const getPreview = () => {
    switch (event.type) {
      case 'thinking':
        return event.content?.slice(0, 100) || '正在思考...'
      case 'tool_call':
        const toolLabel = TOOL_LABELS[event.tool_name || ''] || event.tool_name || '未知工具'
        const argsPreview = event.tool_args ? JSON.stringify(event.tool_args).slice(0, 60) : ''
        return `${toolLabel}${argsPreview ? `: ${argsPreview}` : ''}`
      case 'tool_result':
        const resultStr = typeof event.tool_result === 'string'
          ? event.tool_result
          : JSON.stringify(event.tool_result)
        return resultStr.slice(0, 100)
      case 'retrieval_hit':
        return event.content?.slice(0, 80) || `得分: ${event.relevance_score?.toFixed(2) || 'N/A'}`
      case 'decision':
        return event.content?.slice(0, 100) || '做出决策'
      case 'ask_user':
        return event.content?.slice(0, 100) || '需要用户输入'
      case 'final_answer':
        return event.content?.slice(0, 150) || '完成'
      case 'error':
        return event.content?.slice(0, 100) || '发生错误'
      case 'intent_analysis': {
        const parts = []
        if (event.question_type) parts.push(`类型: ${event.question_type}`)
        if (event.complexity) parts.push(`复杂度: ${event.complexity}`)
        if (event.sub_queries && event.sub_queries.length > 0) parts.push(`${event.sub_queries.length}个子查询`)
        return parts.join(' | ') || '意图分析完成'
      }
      case 'reflection': {
        const parts = []
        if (event.evidence_strength) parts.push(`证据: ${event.evidence_strength}`)
        if (event.answered_aspects && event.answered_aspects.length > 0) parts.push(`${event.answered_aspects.length}个已解答`)
        if (event.missing_aspects && event.missing_aspects.length > 0) parts.push(`${event.missing_aspects.length}个待查`)
        return parts.join(' | ') || event.content?.slice(0, 100) || '自我评估'
      }
      case 'turn_summary':
        return event.content?.slice(0, 100) || '轮次总结'
      case 'phase':
        return event.phase ? `进入阶段: ${event.phase}` : (event.content?.slice(0, 100) || '阶段切换')
      case 'progress':
        return event.content?.slice(0, 100) || '处理中...'
      case 'context_update': {
        if (event.token_usage && event.token_limit) {
          const pct = Math.round((event.token_usage / event.token_limit) * 100)
          return `Token使用: ${pct}%${event.action ? ` (${event.action})` : ''}`
        }
        return event.content?.slice(0, 100) || '上下文更新'
      }
      default:
        return event.content?.slice(0, 100) || ''
    }
  }

  // 获取工具图标
  const getToolIcon = () => {
    if (event.type === 'tool_call' && event.tool_name) {
      const IconComp = TOOL_ICON_MAP[event.tool_name] || SettingsIcon
      return <IconComp className="event-block__icon" />
    }
    const IconComp = EVENT_ICON_MAP[event.type] || InfoIcon
    return <IconComp className="event-block__icon" />
  }

  const levelClass = event.level === 'L0'
    ? 'event-block__level-badge--l0'
    : event.level === 'L1'
    ? 'event-block__level-badge--l1'
    : 'event-block__level-badge--l2'

  const confidenceClass = event.confidence === 'EXTRACTED'
    ? 'event-block__conf-badge--extracted'
    : event.confidence === 'INFERRED'
    ? 'event-block__conf-badge--inferred'
    : 'event-block__conf-badge--default'

  return (
    <div className={`event-block ${config?.cls || ''}`}>
      {/* 主行 */}
      <div className="event-block__main-row">
        {getToolIcon()}
        <span className={`event-block__label ${config?.cls || ''}`}>
          {event.type === 'tool_call' && event.tool_name
            ? TOOL_LABELS[event.tool_name] || event.tool_name
            : config?.label || event.type}
        </span>

        {/* Level 标签 */}
        {event.level && (
          <span className={`event-block__level-badge ${levelClass}`}>
            {event.level}
          </span>
        )}

        {/* Confidence 标签 */}
        {event.confidence && (
          <span className={`event-block__conf-badge ${confidenceClass}`}>
            {event.confidence}
          </span>
        )}

        {/* 时间 */}
        <span className="event-block__time">
          {formatTime(event.timestamp)}
        </span>

        {/* 持续时间 */}
        {event.duration_ms && (
          <span className="event-block__duration">
            {formatDuration(event.duration_ms)}
          </span>
        )}

        {/* 展开按钮 */}
        <button onClick={onToggle} className="event-block__toggle-btn">
          <span className={`event-block__chevron ${expanded ? 'event-block__chevron--expanded' : ''}`}>&#9656;</span>
        </button>

        {/* 详情按钮 */}
        <button onClick={onShowDetail} className="event-block__detail-btn" title="查看详情">
          <svg className="event-block__detail-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </button>
      </div>

      {/* 展开内容 */}
      {expanded && (
        <div className="event-block__expanded">
          {/* 预览 */}
          <div className={`event-block__preview ${config?.cls || ''}`}>
            <p className={`event-block__preview-text ${config?.cls || ''}`}>{getPreview()}</p>
          </div>

          {/* 检索路径 */}
          {event.drill_path && event.drill_path.length > 0 && (
            <div className="event-block__field-cell">
              <span className="event-block__field-label">检索路径：</span>
              <div className="event-block__drill-list">
                {event.drill_path.map((step, i) => (
                  <span key={i} className="event-block__drill-step">
                    <span className="event-block__drill-badge">{step}</span>
                    {i < event.drill_path!.length - 1 && <span className="event-block__drill-arrow">&rarr;</span>}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 相关度得分 */}
          {event.relevance_score !== undefined && (
            <div className="event-block__field-cell">
              <span className="event-block__field-label">相关度得分：</span>
              <span className="event-block__relevance-score">
                {event.relevance_score.toFixed(3)}
              </span>
            </div>
          )}

          {/* 工具参数详情 */}
          {event.type === 'tool_call' && event.tool_args && (
            <div className="event-block__field-cell">
              <span className="event-block__field-label">参数：</span>
              <pre className="event-block__field-pre">
                {JSON.stringify(event.tool_args, null, 2)}
              </pre>
            </div>
          )}

          {/* 工具结果详情 */}
          {event.type === 'tool_result' && event.tool_result && (
            <div className="event-block__field-cell">
              <span className="event-block__field-label">结果：</span>
              <pre className="event-block__field-pre event-block__field-pre--clamped">
                {typeof event.tool_result === 'string'
                  ? event.tool_result.slice(0, 500)
                  : JSON.stringify(event.tool_result, null, 2).slice(0, 500)}
                {(typeof event.tool_result === 'string' ? event.tool_result.length : JSON.stringify(event.tool_result).length) > 500 && '...'}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
