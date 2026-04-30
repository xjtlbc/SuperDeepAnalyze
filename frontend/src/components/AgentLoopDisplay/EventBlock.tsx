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
}

// 事件类型配置
const EVENT_CONFIG: Record<string, { label: string; color: string; bgColor: string }> = {
  thinking: {
    label: '思考',
    color: 'text-purple-600 dark:text-purple-400',
    bgColor: 'bg-purple-100 dark:bg-purple-900/30'
  },
  tool_call: {
    label: '工具调用',
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-100 dark:bg-amber-900/30'
  },
  tool_result: {
    label: '工具结果',
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-100 dark:bg-green-900/30'
  },
  retrieval_hit: {
    label: '检索命中',
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-100 dark:bg-blue-900/30'
  },
  decision: {
    label: '决策',
    color: 'text-indigo-600 dark:text-indigo-400',
    bgColor: 'bg-indigo-100 dark:bg-indigo-900/30'
  },
  ask_user: {
    label: '询问用户',
    color: 'text-orange-600 dark:text-orange-400',
    bgColor: 'bg-orange-100 dark:bg-orange-900/30'
  },
  final_answer: {
    label: '最终答案',
    color: 'text-emerald-600 dark:text-emerald-400',
    bgColor: 'bg-emerald-100 dark:bg-emerald-900/30'
  },
  error: {
    label: '错误',
    color: 'text-red-600 dark:text-red-400',
    bgColor: 'bg-red-100 dark:bg-red-900/30'
  },
  intent_analysis: {
    label: '意图分析',
    color: 'text-cyan-600 dark:text-cyan-400',
    bgColor: 'bg-cyan-100 dark:bg-cyan-900/30'
  },
  reflection: {
    label: '自我评估',
    color: 'text-teal-600 dark:text-teal-400',
    bgColor: 'bg-teal-100 dark:bg-teal-900/30'
  },
  turn_summary: {
    label: '轮次总结',
    color: 'text-slate-600 dark:text-slate-400',
    bgColor: 'bg-slate-100 dark:bg-slate-700/30'
  },
  phase: {
    label: '阶段切换',
    color: 'text-purple-600 dark:text-purple-400',
    bgColor: 'bg-purple-100 dark:bg-purple-900/30'
  },
  progress: {
    label: '进度',
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-100 dark:bg-blue-900/30'
  },
  context_update: {
    label: '上下文管理',
    color: 'text-gray-600 dark:text-gray-400',
    bgColor: 'bg-gray-100 dark:bg-gray-700/30'
  }
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
      return <IconComp className="w-4 h-4" />
    }
    const IconComp = EVENT_ICON_MAP[event.type] || InfoIcon
    return <IconComp className="w-4 h-4" />
  }

  return (
    <div className={`border-l-2 pl-3 py-1.5 ${config.color.replace('text-', 'border-')}`}>
      {/* 主行 */}
      <div className="flex items-center gap-2 text-xs">
        {getToolIcon()}
        <span className={`font-medium ${config.color}`}>
          {event.type === 'tool_call' && event.tool_name
            ? TOOL_LABELS[event.tool_name] || event.tool_name
            : config.label}
        </span>

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

        {/* Confidence 标签 */}
        {event.confidence && (
          <span className={`px-1.5 py-0.5 rounded text-xs ${
            event.confidence === 'EXTRACTED' ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400' :
            event.confidence === 'INFERRED' ? 'bg-yellow-50 text-yellow-600 dark:bg-yellow-900/20 dark:text-yellow-400' :
            'bg-gray-50 text-gray-600 dark:bg-gray-900/20 dark:text-gray-400'
          }`}>
            {event.confidence}
          </span>
        )}

        {/* 时间 */}
        <span className="text-stone-400 dark:text-stone-500 ml-auto font-mono">
          {formatTime(event.timestamp)}
        </span>

        {/* 持续时间 */}
        {event.duration_ms && (
          <span className="text-stone-400 dark:text-stone-500">
            {formatDuration(event.duration_ms)}
          </span>
        )}

        {/* 展开按钮 */}
        <button
          onClick={onToggle}
          className="text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 transition-colors"
        >
          <span className={`transition-transform ${expanded ? 'rotate-90' : ''}`}>▸</span>
        </button>

        {/* 详情按钮 */}
        <button
          onClick={onShowDetail}
          className="text-stone-400 hover:text-amber-500 dark:hover:text-amber-400 transition-colors"
          title="查看详情"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </button>
      </div>

      {/* 展开内容 */}
      {expanded && (
        <div className="mt-2 space-y-2 text-xs">
          {/* 预览 */}
          <div className={`${config.bgColor} rounded px-2 py-1.5`}>
            <p className={`${config.color} whitespace-pre-wrap`}>{getPreview()}</p>
          </div>

          {/* 检索路径 */}
          {event.drill_path && event.drill_path.length > 0 && (
            <div className="bg-stone-100 dark:bg-slate-700 rounded px-2 py-1.5">
              <span className="text-stone-500 dark:text-stone-400">检索路径：</span>
              <div className="flex items-center gap-1 mt-1 flex-wrap">
                {event.drill_path.map((step, i) => (
                  <span key={i} className="flex items-center gap-1">
                    <span className="px-1.5 py-0.5 bg-amber-100 dark:bg-amber-900/30 rounded text-amber-600 dark:text-amber-400 font-mono text-xs">{step}</span>
                    {i < event.drill_path!.length - 1 && <span className="text-stone-400">→</span>}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 相关度得分 */}
          {event.relevance_score !== undefined && (
            <div className="bg-stone-100 dark:bg-slate-700 rounded px-2 py-1.5">
              <span className="text-stone-500 dark:text-stone-400">相关度得分：</span>
              <span className="ml-2 font-mono text-amber-600 dark:text-amber-400">
                {event.relevance_score.toFixed(3)}
              </span>
            </div>
          )}

          {/* 工具参数详情 */}
          {event.type === 'tool_call' && event.tool_args && (
            <div className="bg-stone-100 dark:bg-slate-700 rounded px-2 py-1.5">
              <span className="text-stone-500 dark:text-stone-400">参数：</span>
              <pre className="mt-1 text-stone-700 dark:text-stone-300 overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(event.tool_args, null, 2)}
              </pre>
            </div>
          )}

          {/* 工具结果详情 */}
          {event.type === 'tool_result' && event.tool_result && (
            <div className="bg-stone-100 dark:bg-slate-700 rounded px-2 py-1.5">
              <span className="text-stone-500 dark:text-stone-400">结果：</span>
              <pre className="mt-1 text-stone-700 dark:text-stone-300 overflow-x-auto whitespace-pre-wrap max-h-40">
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