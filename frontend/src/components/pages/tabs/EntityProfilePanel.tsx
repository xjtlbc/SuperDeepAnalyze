import { useState, useMemo } from 'react'
import { TYPE_LABELS } from './shared'
import { EntityTypeIcon } from './EntityIcon'

const TYPE_COLORS: Record<string, string> = {
  person: '#6366f1', organization: '#f59e0b', location: '#10b981',
  event: '#ef4444', object: '#8b5cf6', concept: '#06b6d4',
}

interface Relation {
  target: string
  target_id?: string
  target_type?: string
  relation: string
  type: string
  weight: number
}

interface Statistics {
  relation_count: number
  event_count: number
  mention_count: number
  doc_count: number
}

interface EntityDetail {
  id: string
  name: string
  type: string
  aliases: string[]
  attributes: Record<string, unknown>
  relations: Relation[]
  events: Array<{ title?: string; time?: string; date?: string; description?: string }>
  mentions: Array<{ doc_id: string; chunk_ids: string[]; summary: string }>
  statistics?: Statistics
  mention_count?: number
}

type TabId = 'info' | 'graph' | 'timeline' | 'evidence'

const TAB_CONFIG: { id: TabId; label: string }[] = [
  { id: 'info', label: '档案' },
  { id: 'graph', label: '关系图' },
  { id: 'timeline', label: '时间线' },
  { id: 'evidence', label: '证据' },
]

export default function EntityProfilePanel({
  entity,
  onEntityClick,
}: {
  entity: EntityDetail
  onEntityClick?: (entityId: string) => void
}) {
  const [activeTab, setActiveTab] = useState<TabId>('info')

  const stats = entity.statistics || { relation_count: 0, event_count: 0, mention_count: entity.mention_count || 0, doc_count: 0 }
  const typeColor = TYPE_COLORS[entity.type] || 'var(--text-muted)'

  return (
    <div className="ep-inline">
      {/* Header */}
      <div className="ep-header">
        <div className="ep-avatar" style={{ background: typeColor }}>
          <EntityTypeIcon type={entity.type} className="icon-lg" />
        </div>
        <div className="ep-header-info">
          <h2 className="ep-name">{entity.name}</h2>
          <div className="ep-header-meta">
            <span className="ep-type-badge" style={{ background: typeColor }}>
              {TYPE_LABELS[entity.type] || entity.type}
            </span>
            <span className="ep-id">{entity.id}</span>
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <div className="ep-tabs">
        {TAB_CONFIG.map(t => (
          <button
            key={t.id}
            className={`ep-tab ${activeTab === t.id ? 'ep-tab--active' : ''}`}
            onClick={() => setActiveTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="ep-body">
        {activeTab === 'info' && <InfoTab entity={entity} stats={stats} typeColor={typeColor} />}
        {activeTab === 'graph' && (
          <GraphTab entity={entity} onEntityClick={onEntityClick} typeColor={typeColor} />
        )}
        {activeTab === 'timeline' && <TimelineTab events={entity.events || []} />}
        {activeTab === 'evidence' && <EvidenceTab mentions={entity.mentions || []} />}
      </div>
    </div>
  )
}

/* ============================================================
   Info Tab: Wikipedia-style infobox + statistics cards
   ============================================================ */

function InfoTab({ entity, stats }: { entity: EntityDetail; stats: Statistics; typeColor: string }) {
  return (
    <div className="ep-info">
      {/* Statistics cards */}
      <div className="ep-stat-cards">
        <div className="ep-stat-card">
          <span className="ep-stat-num">{stats.relation_count}</span>
          <span className="ep-stat-label">关联实体</span>
        </div>
        <div className="ep-stat-card">
          <span className="ep-stat-num">{stats.event_count}</span>
          <span className="ep-stat-label">相关事件</span>
        </div>
        <div className="ep-stat-card">
          <span className="ep-stat-num">{stats.mention_count || stats.doc_count}</span>
          <span className="ep-stat-label">文档引用</span>
        </div>
      </div>

      {/* Aliases */}
      {entity.aliases && entity.aliases.length > 0 && (
        <div className="ep-section">
          <h3 className="ep-section-title">别名</h3>
          <div className="ep-tags">
            {entity.aliases.map((a, i) => (
              <span key={i} className="ep-tag">{a}</span>
            ))}
          </div>
        </div>
      )}

      {/* Attributes table */}
      {entity.attributes && Object.keys(entity.attributes).length > 0 && (
        <div className="ep-section">
          <h3 className="ep-section-title">属性</h3>
          <table className="ep-attr-table">
            <tbody>
              {Object.entries(entity.attributes).map(([k, v]) => (
                <tr key={k}>
                  <td className="ep-attr-key">{k}</td>
                  <td className="ep-attr-val">{typeof v === 'string' || typeof v === 'number' ? String(v) : JSON.stringify(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Relations quick list */}
      {entity.relations && entity.relations.length > 0 && (
        <div className="ep-section">
          <h3 className="ep-section-title">关系网络 ({entity.relations.length})</h3>
          <div className="ep-rel-list">
            {entity.relations.slice(0, 15).map((rel, i) => (
              <div key={i} className="ep-rel-item">
                <span className="ep-rel-subject">{entity.name}</span>
                <span className="ep-rel-arrow">→</span>
                <span className="ep-rel-label" title={`${rel.type} (权重: ${rel.weight})`}>
                  {rel.relation}
                </span>
                <span className="ep-rel-arrow">→</span>
                <span
                  className="ep-rel-target"
                  style={{ color: TYPE_COLORS[rel.target_type || ''] || 'var(--text)' }}
                >
                  {rel.target}
                </span>
              </div>
            ))}
            {entity.relations.length > 15 && (
              <p className="ep-more">... 还有 {entity.relations.length - 15} 条关系</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/* ============================================================
   Graph Tab: SVG hub-and-spoke relationship network
   ============================================================ */

function GraphTab({
  entity,
  onEntityClick,
  typeColor,
}: {
  entity: EntityDetail
  onEntityClick?: (entityId: string) => void
  typeColor: string
}) {
  const relations = entity.relations || []
  const MAX_DISPLAY = 20
  const displayRels = relations.slice(0, MAX_DISPLAY)

  const nodes = useMemo(() => {
    if (displayRels.length === 0) return { center: { x: 0, y: 0 }, ring: [] as { x: number; y: number; rel: Relation }[] }

    const cx = 220, cy = 200, radius = 155
    const n = displayRels.length
    return {
      center: { x: cx, y: cy },
      ring: displayRels.map((rel, i) => {
        const angle = (2 * Math.PI * i) / n - Math.PI / 2
        return {
          x: cx + radius * Math.cos(angle),
          y: cy + radius * Math.sin(angle),
          rel,
        }
      }),
    }
  }, [displayRels])

  if (displayRels.length === 0) {
    return <div className="ep-empty">暂无关系数据</div>
  }

  return (
    <div className="ep-graph">
      <svg viewBox="0 0 440 400" className="ep-graph-svg">
        {/* Edges */}
        {nodes.ring.map((n, i) => (
          <line
            key={`edge-${i}`}
            x1={nodes.center.x} y1={nodes.center.y}
            x2={n.x} y2={n.y}
            stroke="var(--border)"
            strokeWidth={1.5}
            strokeDasharray={n.rel.weight > 0.7 ? 'none' : '4 3'}
          />
        ))}
        {/* Relation labels on edges */}
        {nodes.ring.map((n, i) => {
          const mx = (nodes.center.x + n.x) / 2
          const my = (nodes.center.y + n.y) / 2
          return (
            <text key={`elbl-${i}`} x={mx} y={my - 6} textAnchor="middle"
              fontSize={10} fill="var(--text-muted)" className="ep-graph-edge-label">
              {n.rel.relation.length > 6 ? n.rel.relation.slice(0, 6) + '…' : n.rel.relation}
            </text>
          )
        })}
        {/* Center node */}
        <circle cx={nodes.center.x} cy={nodes.center.y} r={32} fill={typeColor} stroke="#fff" strokeWidth={3} />
        <text x={nodes.center.x} y={nodes.center.y + 4} textAnchor="middle"
          fontSize={11} fill="#fff" fontWeight={700} className="ep-graph-ctr-text">
          {entity.name.length > 4 ? entity.name.slice(0, 4) + '…' : entity.name}
        </text>
        {/* Ring nodes */}
        {nodes.ring.map((n, i) => {
          const tColor = TYPE_COLORS[n.rel.target_type || ''] || 'var(--bg-tertiary)'
          const name = n.rel.target.length > 5 ? n.rel.target.slice(0, 5) + '…' : n.rel.target
          const clickable = !!(n.rel.target_id && onEntityClick)
          return (
            <g key={`rnode-${i}`}
              className={clickable ? 'ep-graph-node--clickable' : ''}
              onClick={() => clickable && onEntityClick?.(n.rel.target_id!)}
            >
              <circle cx={n.x} cy={n.y} r={18} fill={tColor} stroke="#fff" strokeWidth={2} />
              <text x={n.x} y={n.y + 4} textAnchor="middle"
                fontSize={9} fill="#fff" fontWeight={600}>
                {name}
              </text>
            </g>
          )
        })}
      </svg>
      {relations.length > MAX_DISPLAY && (
        <p className="ep-more" style={{ textAlign: 'center' }}>
          显示前 {MAX_DISPLAY} 条，共 {relations.length} 条关系
        </p>
      )}
      <p className="ep-graph-hint">点击关联实体可切换查看</p>
    </div>
  )
}

/* ============================================================
   Timeline Tab: entity-focused events sorted by date
   ============================================================ */

function TimelineTab({ events }: { events: EntityDetail['events'] }) {
  if (events.length === 0) {
    return <div className="ep-empty">暂无相关事件</div>
  }

  return (
    <div className="ep-timeline">
      {events.map((ev, i) => {
        const evDate = ev.date || ev.time || ''
        const evTitle = ev.title || (ev.description || '').slice(0, 60) || '未命名事件'
        const formattedDate = evDate ? _formatDate(evDate) : ''
        return (
          <div key={i} className="ep-timeline-item">
            <div className="ep-timeline-dot" />
            {i < events.length - 1 && <div className="ep-timeline-line" />}
            <div className="ep-timeline-card">
              <p className="ep-timeline-title">{evTitle}</p>
              {formattedDate && <p className="ep-timeline-date">{formattedDate}</p>}
              {ev.description && (
                <p className="ep-timeline-desc">{ev.description.slice(0, 200)}</p>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function _formatDate(raw: string): string {
  const m = raw.match(/^(\d{4})-(\d{2})(?:-(\d{2}))?/)
  if (m) {
    const y = parseInt(m[1]), mo = parseInt(m[2])
    let s = `${y}年${mo}月`
    if (m[3]) s += `${parseInt(m[3])}日`
    return s
  }
  return raw
}

/* ============================================================
   Evidence Tab: L1 mentions with expandable summaries
   ============================================================ */

function EvidenceTab({ mentions }: { mentions: EntityDetail['mentions'] }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)

  if (mentions.length === 0) {
    return <div className="ep-empty">暂无文档引用</div>
  }

  return (
    <div className="ep-evidence">
      <p className="ep-evidence-count">共 {mentions.length} 处文档提及</p>
      {mentions.map((m, i) => (
        <div key={i} className={`ep-evidence-item ${expandedIdx === i ? 'ep-evidence-item--expanded' : ''}`}>
          <div className="ep-evidence-header" onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}>
            <span className="ep-evidence-doc">{m.doc_id}</span>
            <span className="ep-evidence-chunks">{m.chunk_ids?.length || 0} chunks</span>
            <span className="ep-evidence-chevron">{expandedIdx === i ? '▾' : '▸'}</span>
          </div>
          {expandedIdx === i && (
            <div className="ep-evidence-body">
              <p className="ep-evidence-summary">{m.summary || '(无摘要)'}</p>
              {m.chunk_ids && m.chunk_ids.length > 0 && (
                <div className="ep-evidence-chunk-list">
                  {m.chunk_ids.map((cid, ci) => (
                    <span key={ci} className="ep-evidence-chunk">{cid}</span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
