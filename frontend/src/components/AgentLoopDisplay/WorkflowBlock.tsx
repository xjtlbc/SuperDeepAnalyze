import type { AgentEvent, WorkflowStepInfo } from '../../types/agent'

interface WorkflowBlockProps {
  event: AgentEvent
  expanded: boolean
  onToggle: () => void
}

const MODE_LABELS: Record<string, string> = {
  pipeline: '顺序管道',
  parallel: '并行研究',
  verify: '对抗验证',
}

const MODE_COLORS: Record<string, string> = {
  pipeline: '#3b82f6',
  parallel: '#8b5cf6',
  verify: '#f59e0b',
}

const STATUS_COLORS: Record<string, string> = {
  pending: '#9ca3af',
  running: '#3b82f6',
  completed: '#22c55e',
  failed: '#ef4444',
}

const STATUS_ICONS: Record<string, string> = {
  pending: '○',
  running: '◎',
  completed: '●',
  failed: '✕',
}

function StepRow({ step }: { step: WorkflowStepInfo }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      padding: '4px 0',
      fontSize: '12px',
    }}>
      <span style={{ color: STATUS_COLORS[step.status] || '#9ca3af', width: '16px', textAlign: 'center' }}>
        {STATUS_ICONS[step.status] || '○'}
      </span>
      <span style={{ flex: 1, color: '#d1d5db', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {step.description}
      </span>
      {step.duration != null && (
        <span style={{ color: '#6b7280', fontSize: '11px', flexShrink: 0 }}>
          {step.duration.toFixed(1)}s
        </span>
      )}
      {step.entity_count != null && step.entity_count > 0 && (
        <span style={{
          color: '#a78bfa',
          fontSize: '10px',
          background: 'rgba(167,139,250,0.15)',
          padding: '1px 5px',
          borderRadius: '8px',
          flexShrink: 0,
        }}>
          {step.entity_count}实体
        </span>
      )}
    </div>
  )
}

export default function WorkflowBlock({ event, expanded, onToggle }: WorkflowBlockProps) {
  const mode = event.workflow_mode || 'pipeline'
  const steps = event.workflow_steps || []
  const totalDuration = event.workflow_total_duration
  const totalEntities = event.workflow_total_entities
  const synthesis = event.workflow_synthesis
  const modeColor = MODE_COLORS[mode] || '#6b7280'

  return (
    <div style={{
      border: `1px solid ${modeColor}33`,
      borderRadius: '6px',
      margin: '4px 0',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div
        onClick={onToggle}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '6px 10px',
          cursor: 'pointer',
          background: `${modeColor}11`,
        }}
      >
        <span style={{ fontSize: '13px', fontWeight: 600, color: modeColor }}>
          {MODE_LABELS[mode] || mode}
        </span>
        <span style={{ color: '#6b7280', fontSize: '11px' }}>
          {steps.length}步
        </span>
        {totalDuration != null && (
          <span style={{ color: '#6b7280', fontSize: '11px' }}>
            {totalDuration.toFixed(1)}s
          </span>
        )}
        {totalEntities != null && totalEntities > 0 && (
          <span style={{ color: '#a78bfa', fontSize: '11px' }}>
            {totalEntities}个实体
          </span>
        )}
        <span style={{ marginLeft: 'auto', color: '#6b7280', fontSize: '11px' }}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div style={{ padding: '6px 10px', borderTop: `1px solid ${modeColor}22` }}>
          {steps.length > 0 ? (
            <div>
              {steps.map((step, i) => (
                <StepRow key={step.step_id || i} step={step} />
              ))}
            </div>
          ) : (
            <div style={{ color: '#6b7280', fontSize: '12px' }}>暂无步骤详情</div>
          )}

          {synthesis && (
            <div style={{
              marginTop: '6px',
              padding: '6px 8px',
              background: 'rgba(255,255,255,0.03)',
              borderRadius: '4px',
              fontSize: '12px',
              color: '#d1d5db',
              lineHeight: '1.5',
              maxHeight: '120px',
              overflow: 'auto',
            }}>
              {synthesis}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
