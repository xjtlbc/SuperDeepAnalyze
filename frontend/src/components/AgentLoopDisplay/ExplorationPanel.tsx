import { useState } from 'react'
import type { AgentEvent } from '../../types/agent'

interface Props {
  thinkingEvents: AgentEvent[]
  agentEvents: AgentEvent[]
  onClear?: () => void
}

export default function ExplorationPanel({ thinkingEvents, agentEvents, onClear }: Props) {
  const [expanded, setExpanded] = useState(false)

  const totalEvents = thinkingEvents.length + agentEvents.length
  if (totalEvents === 0) return null

  // Count by category
  const toolCalls = agentEvents.filter(e => e.type === 'tool_call' || e.type === 'tool_result')
  const intentEvents = thinkingEvents.filter(e =>
    e.content?.includes('意图分析') || e.content?.includes('意图') || e.type === 'intent_analysis'
  )
  const phaseEvents = thinkingEvents.filter(e => e.type === 'phase')
  const thinkingOnly = thinkingEvents.filter(e =>
    e.type === 'thinking' && !intentEvents.includes(e) && !phaseEvents.includes(e)
  )
  const searchHits = agentEvents.filter(e => e.type === 'retrieval_hit' || e.type === 'decision')

  // Deduplicate tool calls
  const toolCallNames = [...new Set(toolCalls.map(e => e.tool_name || '').filter(Boolean))]

  // Build summary line
  const parts: string[] = []
  if (intentEvents.length > 0) parts.push('意图分析')
  if (toolCallNames.length > 0) parts.push(`${toolCallNames.length}个工具`)
  if (searchHits.length > 0) parts.push('检索命中')
  if (thinkingOnly.length > 0) parts.push('思考')

  return (
    <div className="exploration-panel">
      <button className="exploration-toggle" onClick={() => setExpanded(!expanded)}>
        <span className="exploration-toggle-icon">{expanded ? '▾' : '▸'}</span>
        <span className="exploration-toggle-text">
          探索过程 {parts.length > 0 && `(${parts.join(' → ')})`}
        </span>
        <span className="exploration-toggle-count">{totalEvents} 事件</span>
      </button>

      {expanded && (
        <div className="exploration-body">
          {/* Intent analysis */}
          {intentEvents.map((ev, i) => (
            <div key={`intent-${i}`} className="exploration-step exploration-step--intent">
              <span className="exploration-step-icon">📖</span>
              <span className="exploration-step-text">{ev.content || '意图分析'}</span>
            </div>
          ))}

          {/* Phase transitions */}
          {phaseEvents.map((ev, i) => (
            <div key={`phase-${i}`} className="exploration-step exploration-step--phase">
              <span className="exploration-step-icon">🔄</span>
              <span className="exploration-step-text">{ev.content || ev.phase || '阶段切换'}</span>
            </div>
          ))}

          {/* Tool calls */}
          {toolCallNames.length > 0 && (
            <div className="exploration-step-group">
              <div className="exploration-step-group-header">🔧 工具调用 ({toolCalls.length})</div>
              {toolCallNames.map((name, i) => (
                <div key={`tool-${i}`} className="exploration-step exploration-step--tool">
                  <span className="exploration-step-icon">•</span>
                  <span className="exploration-step-text">{name}</span>
                </div>
              ))}
            </div>
          )}

          {/* Search hits */}
          {searchHits.length > 0 && (
            <div className="exploration-step-group">
              <div className="exploration-step-group-header">📊 检索结果 ({searchHits.length})</div>
              {searchHits.slice(0, 8).map((ev, i) => (
                <div key={`hit-${i}`} className="exploration-step exploration-step--search">
                  <span className="exploration-step-icon">•</span>
                  <span className="exploration-step-text">{ev.content?.slice(0, 200) || '命中'}</span>
                </div>
              ))}
            </div>
          )}

          {/* Thinking segments */}
          {thinkingOnly.length > 0 && (
            <div className="exploration-step-group">
              <div className="exploration-step-group-header">💭 思考过程 ({thinkingOnly.length})</div>
              {thinkingOnly.slice(0, 10).map((ev, i) => (
                <div key={`think-${i}`} className="exploration-step exploration-step--thinking">
                  <span className="exploration-step-icon">•</span>
                  <span className="exploration-step-text">{ev.content?.slice(0, 200) || '思考中...'}</span>
                </div>
              ))}
              {thinkingOnly.length > 10 && (
                <div className="exploration-step exploration-step--more">
                  还有 {thinkingOnly.length - 10} 条思考记录...
                </div>
              )}
            </div>
          )}

          {onClear && (
            <button className="exploration-clear" onClick={onClear}>清除记录</button>
          )}
        </div>
      )}
    </div>
  )
}
