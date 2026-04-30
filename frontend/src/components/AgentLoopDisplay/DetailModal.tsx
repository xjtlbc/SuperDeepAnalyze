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
  context_update: '上下文更新'
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* 背景遮罩 */}
      <div
        className="absolute inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* 模态框 */}
      <div className="relative bg-white dark:bg-slate-800 rounded-xl border border-stone-200 dark:border-slate-700 shadow-xl max-w-2xl w-full max-h-[80vh] overflow-hidden flex flex-col">
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-stone-200 dark:border-slate-700">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-stone-800 dark:text-stone-100">
              事件详情
            </h3>
            <span className="px-2 py-0.5 bg-amber-100 dark:bg-amber-900/30 rounded text-xs text-amber-600 dark:text-amber-400 font-medium">
              {EVENT_LABELS[event.type]}
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 rounded-lg hover:bg-stone-100 dark:hover:bg-slate-700 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* 基本信息 */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-3">
              <p className="text-xs text-stone-500 dark:text-stone-400">ID</p>
              <p className="text-sm font-mono text-stone-700 dark:text-stone-300">{event.id}</p>
            </div>
            <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-3">
              <p className="text-xs text-stone-500 dark:text-stone-400">时间戳</p>
              <p className="text-sm font-mono text-stone-700 dark:text-stone-300">{formatTime(event.timestamp)}</p>
            </div>
            <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-3">
              <p className="text-xs text-stone-500 dark:text-stone-400">类型</p>
              <p className="text-sm text-stone-700 dark:text-stone-300">{event.type}</p>
            </div>
            <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-3">
              <p className="text-xs text-stone-500 dark:text-stone-400">持续时间</p>
              <p className="text-sm font-mono text-stone-700 dark:text-stone-300">{formatDuration(event.duration_ms)}</p>
            </div>
          </div>

          {/* Content */}
          {event.content && (
            <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-3">
              <p className="text-xs text-stone-500 dark:text-stone-400 mb-1">内容</p>
              <p className="text-sm text-stone-700 dark:text-stone-300 whitespace-pre-wrap">{event.content}</p>
            </div>
          )}

          {/* 工具名称 */}
          {event.tool_name && (
            <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-3 border border-amber-200 dark:border-amber-800">
              <p className="text-xs text-amber-600 dark:text-amber-400 mb-1">工具名称</p>
              <p className="text-sm font-medium text-amber-700 dark:text-amber-300">{event.tool_name}</p>
            </div>
          )}

          {/* 工具参数 */}
          {event.tool_args && (
            <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-3">
              <p className="text-xs text-stone-500 dark:text-stone-400 mb-1">工具参数</p>
              <pre className="text-sm text-stone-700 dark:text-stone-300 overflow-x-auto whitespace-pre-wrap bg-white dark:bg-slate-800 rounded p-2 border border-stone-200 dark:border-slate-600">
                {JSON.stringify(event.tool_args, null, 2)}
              </pre>
            </div>
          )}

          {/* 工具结果 */}
          {event.tool_result !== undefined && (
            <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3 border border-green-200 dark:border-green-800">
              <p className="text-xs text-green-600 dark:text-green-400 mb-1">工具结果</p>
              <pre className="text-sm text-green-700 dark:text-green-300 overflow-x-auto whitespace-pre-wrap max-h-60">
                {typeof event.tool_result === 'string'
                  ? event.tool_result
                  : JSON.stringify(event.tool_result, null, 2)}
              </pre>
            </div>
          )}

          {/* Level */}
          {event.level && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-stone-500 dark:text-stone-400">层级：</span>
              <span className={`px-2 py-1 rounded text-sm font-mono ${
                event.level === 'L0' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' :
                event.level === 'L1' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400'
              }`}>
                {event.level}
              </span>
            </div>
          )}

          {/* Confidence */}
          {event.confidence && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-stone-500 dark:text-stone-400">置信度：</span>
              <span className={`px-2 py-1 rounded text-sm ${
                event.confidence === 'EXTRACTED' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' :
                event.confidence === 'INFERRED' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' :
                'bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400'
              }`}>
                {event.confidence}
              </span>
            </div>
          )}

          {/* Relevance Score */}
          {event.relevance_score !== undefined && (
            <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 border border-blue-200 dark:border-blue-800">
              <p className="text-xs text-blue-600 dark:text-blue-400 mb-1">相关度得分</p>
              <p className="text-lg font-mono font-bold text-blue-700 dark:text-blue-300">
                {event.relevance_score.toFixed(4)}
              </p>
            </div>
          )}

          {/* Drill Path */}
          {event.drill_path && event.drill_path.length > 0 && (
            <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-3">
              <p className="text-xs text-stone-500 dark:text-stone-400 mb-2">检索路径</p>
              <div className="flex items-center gap-2 flex-wrap">
                {event.drill_path.map((step, i) => (
                  <span key={i} className="flex items-center gap-1">
                    <span className="px-2 py-1 bg-amber-100 dark:bg-amber-900/30 rounded text-sm text-amber-700 dark:text-amber-400 font-mono">
                      {step}
                    </span>
                    {i < event.drill_path!.length - 1 && (
                      <span className="text-stone-400 dark:text-stone-500">→</span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 完整 JSON */}
          <div className="bg-stone-100 dark:bg-slate-700 rounded-lg p-3">
            <p className="text-xs text-stone-500 dark:text-stone-400 mb-1">完整 JSON</p>
            <pre className="text-xs text-stone-700 dark:text-stone-300 overflow-x-auto whitespace-pre-wrap max-h-40">
              {getFullJson()}
            </pre>
          </div>
        </div>

        {/* 底部 */}
        <div className="px-4 py-3 border-t border-stone-200 dark:border-slate-700 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-stone-200 hover:bg-stone-300 dark:bg-slate-700 dark:hover:bg-slate-600 text-stone-700 dark:text-stone-300 rounded-lg text-sm font-medium transition-colors"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}