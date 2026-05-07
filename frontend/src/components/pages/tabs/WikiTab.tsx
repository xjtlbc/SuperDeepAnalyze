import { useState, useEffect, Component } from 'react'
import type { ReactNode } from 'react'
import { API_BASE, TYPE_LABELS } from './shared'
import { EntityTypeIcon, GapIconRenderer } from './EntityIcon'
import { ConceptTags } from '../../knowledge/ConceptTags'
import { WikiIcon, ClockIcon, SearchIcon, WarningIcon, ExternalLinkIcon, InfoIcon } from '../../Icons'
import EntityProfilePanel from './EntityProfilePanel'

class WikiErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean; errMsg: string }> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { hasError: false, errMsg: '' }
  }
  static getDerivedStateFromError(err: Error) {
    return { hasError: true, errMsg: err.message || String(err) }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 40, textAlign: 'center' }}>
          <p style={{ fontSize: 16, fontWeight: 600, color: 'var(--text)', marginBottom: 8 }}>Wiki 页面渲染出错</p>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16, maxWidth: 500, margin: '0 auto' }}>
            {this.state.errMsg.substring(0, 200)}
          </p>
          <button onClick={() => { this.setState({ hasError: false, errMsg: '' }); window.location.reload() }}
            style={{ padding: '8px 20px', borderRadius: 8, background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer', marginTop: 16 }}>
            刷新页面
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

interface WikiEntity {
  id: string
  name: string
  type: string
  aliases: string[]
}

interface WikiOverview {
  entities: WikiEntity[]
  entity_count: number
  timeline_count: number
  relation_count: number
  type_counts: Record<string, number>
  top_entities?: Array<{ id: string; name: string; type: string; confidence: string; importance: number }>
  wiki_status?: string
}

interface EntityDetail {
  id: string
  name: string
  type: string
  aliases: string[]
  attributes: Record<string, unknown>
  relations: Array<{ target: string; target_id?: string; target_type?: string; relation: string; type: string; weight: number }>
  events: Array<{ title?: string; date?: string; time?: string; description?: string }>
  mentions: Array<{ doc_id: string; chunk_ids: string[]; summary: string }>
  statistics?: { relation_count: number; event_count: number; mention_count: number; doc_count: number }
  mention_count?: number
}

interface TimelineParticipant {
  id: string
  name: string
  type: string
}

interface TimelineEvent {
  title?: string
  time?: string
  date?: string
  participants?: (string | TimelineParticipant)[]
  description?: string
  source_docs?: string[]
  source?: string
  confidence?: number
}


function formatDate(dateStr: string): string {
  const m = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (m) return `${m[1]}年${parseInt(m[2])}月${parseInt(m[3])}日`
  return dateStr
}

function safeStr(v: unknown): string {
  if (v === null || v === undefined) return ''
  if (typeof v === 'string') return v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  return ''
}

function getParticipantName(p: string | TimelineParticipant | unknown): string {
  if (!p) return ''
  if (typeof p === 'string') return p
  if (typeof p === 'object' && p !== null) {
    const d = p as Record<string, unknown>
    return safeStr(d.name || d.id)
  }
  return ''
}

export function WikiTab({ kbId, refreshKey = 0 }: { kbId: string; refreshKey?: number }) {
  return <EmbeddedWikiView kbId={kbId} refreshKey={refreshKey} />
}

type TabKey = 'overview' | 'entities' | 'timeline' | 'analysis'
const TABS: { key: TabKey; label: string }[] = [
  { key: 'overview', label: '总览' },
  { key: 'entities', label: '实体' },
  { key: 'timeline', label: '时间线' },
  { key: 'analysis', label: '分析' },
]

function EmbeddedWikiView({ kbId, refreshKey = 0 }: { kbId: string; refreshKey?: number }) {
  const [overview, setOverview] = useState<WikiOverview | null>(null)
  const [selectedEntity, setSelectedEntity] = useState<EntityDetail | null>(null)
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [selectedTimelineIdx, setSelectedTimelineIdx] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<TabKey>('overview')
  const [filterType, setFilterType] = useState<string>('all')
  const [loading, setLoading] = useState(false)
  const [entityLoading, setEntityLoading] = useState(false)
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set())
  const [analysis, setAnalysis] = useState<any>(null)
  const [crossRefs, setCrossRefs] = useState<any[]>([])
  const [surprises, setSurprises] = useState<any>(null)
  const [wikiGenerating, setWikiGenerating] = useState(false)

  useEffect(() => { fetchWiki(); fetchTimeline() }, [kbId, refreshKey])

  useEffect(() => {
    fetch(`${API_BASE}/api/wiki/${kbId}/analysis`)
      .then(r => r.json()).then(setAnalysis).catch(() => setAnalysis(null))
  }, [kbId])

  useEffect(() => {
    fetch(`${API_BASE}/api/wiki/${kbId}/cross_refs`)
      .then(r => r.json()).then(d => setCrossRefs(d.cross_refs || [])).catch(() => setCrossRefs([]))
  }, [kbId])

  useEffect(() => {
    fetch(`${API_BASE}/api/wiki/${kbId}/surprises`)
      .then(r => r.json()).then(setSurprises).catch(() => setSurprises(null))
  }, [kbId])

  useEffect(() => {
    if (overview?.wiki_status !== 'generating') { setWikiGenerating(false); return }
    setWikiGenerating(true)
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/wiki/${kbId}/status`)
        if (res.ok) {
          const data = await res.json()
          if (data.wiki_status !== 'generating') { setWikiGenerating(false); fetchWiki(); fetchTimeline(); clearInterval(timer) }
        }
      } catch { /* ignore */ }
    }, 3000)
    return () => clearInterval(timer)
  }, [overview?.wiki_status, kbId])

  const fetchWiki = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/wiki/${kbId}`)
      if (res.ok) setOverview(await res.json()); else setOverview(null)
    } catch { setOverview(null) }
    setLoading(false)
  }

  const fetchEntity = async (entityId: string) => {
    setEntityLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/wiki/${kbId}/entity/${entityId}`)
      if (res.ok) setSelectedEntity(await res.json())
    } catch { /* ignore */ }
    setEntityLoading(false)
  }

  const fetchTimeline = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/wiki/${kbId}/timeline`)
      if (res.ok) { const d = await res.json(); setTimeline(d.events || []) }
    } catch { /* ignore */ }
  }

  const toggleType = (type: string) => {
    setExpandedTypes(prev => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type); else next.add(type)
      return next
    })
  }

  const triggerWikiGen = async () => {
    setWikiGenerating(true)
    try {
      const res = await fetch(`${API_BASE}/api/compile/${kbId}/wiki`, { method: 'POST' })
      if (res.ok) setTimeout(() => { fetchWiki(); fetchTimeline() }, 2000)
      else setWikiGenerating(false)
    } catch { setWikiGenerating(false) }
  }

  const entitiesByType: Record<string, WikiEntity[]> = {}
  if (overview?.entities) {
    for (const e of overview.entities) {
      const t = e.type || 'unknown'
      if (!entitiesByType[t]) entitiesByType[t] = []
      entitiesByType[t].push(e)
    }
  }
  const sortedTypes = Object.keys(entitiesByType).sort((a, b) => entitiesByType[b].length - entitiesByType[a].length)

  return (
    <WikiErrorBoundary>
    <div className="wiki-tab">
      {/* Sidebar */}
      <div className="wiki-tab__sidebar">
        <div className="wiki-tab__sidebar-tabs">
          {TABS.map(tab => (
            <button key={tab.key}
              onClick={() => { setActiveTab(tab.key); setSelectedEntity(null); setSelectedTimelineIdx(null) }}
              className={`wiki-tab__sidebar-tab ${activeTab === tab.key ? 'wiki-tab__sidebar-tab--active' : ''}`}>
              {tab.label}
            </button>
          ))}
        </div>
        <div className="wiki-tab__sidebar-body">

          {/* ======== OVERVIEW SIDEBAR ======== */}
          {activeTab === 'overview' && loading && (
            <div className="wiki-tab__loading"><div className="chat-spinner chat-spinner--accent"></div></div>
          )}
          {activeTab === 'overview' && !loading && !overview && (
            <div className="wiki-tab__empty-state">
              <p className="wiki-tab__empty-hint">暂无 Wiki 数据</p>
              <button onClick={triggerWikiGen} disabled={wikiGenerating}
                style={{ padding: '8px 20px', borderRadius: 8, background: 'var(--accent)', color: '#fff', fontSize: 13, fontWeight: 500, border: 'none', cursor: 'pointer', opacity: wikiGenerating ? 0.6 : 1 }}>
                {wikiGenerating ? '正在生成...' : '生成 Wiki'}
              </button>
            </div>
          )}
          {activeTab === 'overview' && overview && overview.entity_count > 0 && (
            <div className="wiki-tab__overview-sidebar">
              <div className="wiki-tab__overview-stats">
                共 {overview.entity_count} 实体 · {overview.timeline_count} 事件 · {overview.relation_count || 0} 关系
              </div>
              {sortedTypes.map(type => (
                <button key={type} onClick={() => { setActiveTab('entities'); setFilterType(type); setExpandedTypes(prev => { const next = new Set(prev); next.add(type); return next }) }}
                  className="wiki-tab__entity-group-btn">
                  <EntityTypeIcon type={type} className="icon-sm" />
                  <span className="wiki-tab__entity-group-label">{TYPE_LABELS[type] || type}</span>
                  <span className="wiki-tab__entity-count">{entitiesByType[type]?.length || 0}</span>
                </button>
              ))}
            </div>
          )}

          {/* ======== ENTITIES SIDEBAR ======== */}
          {activeTab === 'entities' && loading && (
            <div className="wiki-tab__loading"><div className="chat-spinner chat-spinner--accent"></div></div>
          )}
          {activeTab === 'entities' && !loading && overview && overview.entity_count > 0 && (
            <div className="wiki-tab__entity-list">
              <button onClick={() => { setFilterType('all'); setSelectedEntity(null) }}
                className={`wiki-tab__entity-group-btn ${filterType === 'all' ? 'wiki-tab__entity-group-btn--active' : ''}`}>
                <span style={{ fontWeight: 600 }}>全部实体</span>
                <span className="wiki-tab__entity-count">{overview.entity_count}</span>
              </button>
              {sortedTypes.map(type => (
                <div key={type}>
                  <button onClick={() => toggleType(type)} className="wiki-tab__entity-group-btn">
                    <span className={`wiki-tab__chevron ${expandedTypes.has(type) ? 'wiki-tab__chevron--expanded' : ''}`}>▸</span>
                    <EntityTypeIcon type={type} className="icon-sm" />
                    <span className="wiki-tab__entity-group-label">{TYPE_LABELS[type] || type}</span>
                    <span className="wiki-tab__entity-count">{entitiesByType[type]?.length || 0}</span>
                  </button>
                  {expandedTypes.has(type) && (
                    <div className="wiki-tab__entity-sub-list">
                      {entitiesByType[type]?.map(e => (
                        <button key={e.id} onClick={() => fetchEntity(e.id)}
                          className={`wiki-tab__entity-item ${selectedEntity?.id === e.id ? 'wiki-tab__entity-item--active' : ''}`}>
                          {e.name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          {activeTab === 'entities' && !loading && (!overview || overview.entity_count === 0) && (
            <p className="wiki-tab__empty-hint">暂无实体数据</p>
          )}

          {/* ======== TIMELINE SIDEBAR ======== */}
          {activeTab === 'timeline' && (
            <div className="wiki-tab__timeline-sidebar">
              {loading && <div className="wiki-tab__loading"><div className="chat-spinner chat-spinner--accent"></div></div>}
              {!loading && timeline.length === 0 && <p className="wiki-tab__empty-hint">暂无时间线事件</p>}
              {timeline.map((ev, i) => {
                const evDate = ev.date || ev.time || ''
                const evTitle = safeStr(ev.title) || safeStr(ev.description).slice(0, 40)
                return (
                  <div key={i} className="wiki-tab__timeline-item"
                    onClick={() => setSelectedTimelineIdx(selectedTimelineIdx === i ? null : i)}
                    style={{ background: selectedTimelineIdx === i ? 'var(--bg-tertiary)' : undefined }}>
                    <div className="wiki-tab__timeline-dot"></div>
                    {evDate && <p className="wiki-tab__timeline-item-time">{formatDate(evDate)}</p>}
                    <p className="wiki-tab__timeline-item-title">{evTitle}</p>
                    {ev.participants && ev.participants.length > 0 && (
                      <div className="wiki-tab__timeline-item-participants">
                        {ev.participants.slice(0, 4).map((p, j) => (
                          <span key={j} className="wiki-tab__timeline-item-participant">{getParticipantName(p)}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* ======== ANALYSIS SIDEBAR ======== */}
          {activeTab === 'analysis' && (
            <div className="wiki-tab__analysis-sidebar">
              {analysis?.contradictions?.length > 0 && (
                <div className="wiki-tab__analysis-item wiki-tab__analysis-item--danger">
                  <WarningIcon className="icon-sm" /> {analysis.contradictions.length} 个矛盾
                </div>
              )}
              {crossRefs.length > 0 && (
                <div className="wiki-tab__analysis-item wiki-tab__analysis-item--neutral">
                  <ExternalLinkIcon className="wiki-tab__analysis-icon-sm" /> {crossRefs.length} 个跨文档引用
                </div>
              )}
              {analysis?.knowledge_gaps?.length > 0 && (
                <div className="wiki-tab__analysis-item wiki-tab__analysis-item--amber">
                  <GapIconRenderer type="isolated_entity" className="wiki-tab__analysis-icon-sm" /> {analysis.knowledge_gaps.length} 个知识缺口
                </div>
              )}
              {analysis?.narrative_threads?.length > 0 && (
                <div className="wiki-tab__analysis-item wiki-tab__analysis-item--blue">
                  <WikiIcon className="wiki-tab__analysis-icon-sm" /> {analysis.narrative_threads.length} 条叙事线索
                </div>
              )}
              {surprises?.stats?.total_surprises > 0 && (
                <div className="wiki-tab__analysis-item wiki-tab__analysis-item--purple">
                  <InfoIcon className="wiki-tab__analysis-icon-sm" /> {surprises.stats.total_surprises} 个发现
                </div>
              )}
              {!analysis && !crossRefs.length && !surprises?.stats?.total_surprises && (
                <p className="wiki-tab__empty-hint">暂无分析数据</p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ======== DETAIL PANEL ======== */}
      <div className="wiki-tab__detail">

        {/* ======== OVERVIEW DETAIL ======== */}
        {activeTab === 'overview' && overview && overview.entity_count > 0 && (
          <div className="wiki-tab__overview-detail">
            <div className="wiki-tab__stats-grid">
              <div className="wiki-tab__stat-card"><p className="wiki-tab__stat-label">实体总数</p><p className="wiki-tab__stat-value">{overview.entity_count}</p></div>
              <div className="wiki-tab__stat-card"><p className="wiki-tab__stat-label">时间线事件</p><p className="wiki-tab__stat-value">{overview.timeline_count}</p></div>
              <div className="wiki-tab__stat-card"><p className="wiki-tab__stat-label">关系网络</p><p className="wiki-tab__stat-value">{overview.relation_count || 0}</p></div>
              <div className="wiki-tab__stat-card"><p className="wiki-tab__stat-label">实体类型</p><p className="wiki-tab__stat-value">{sortedTypes.length}</p></div>
            </div>

            {overview.top_entities && overview.top_entities.length > 0 && (
              <div className="wiki-tab__section-card">
                <h3 className="wiki-tab__section-title">核心概念标签</h3>
                <ConceptTags entities={overview.top_entities.map((e, i) => ({ ...e, frequency: 0, connections: 0, score: 0, rank: i + 1 }))}
                  onTagClick={(name) => {
                    const ent = overview.entities.find(e => e.name === name)
                    if (ent) { setActiveTab('entities'); fetchEntity(ent.id) }
                  }} />
              </div>
            )}

            <div className="wiki-tab__section-card">
              <h3 className="wiki-tab__section-title">实体类型分布</h3>
              <div className="wiki-tab__distribution">
                {sortedTypes.map(type => {
                  const count = entitiesByType[type]?.length || 0
                  const pct = Math.round((count / overview.entity_count) * 100)
                  return (
                    <div key={type} className="wiki-tab__distribution-row">
                      <span className="wiki-tab__distribution-label"><EntityTypeIcon type={type} className="wiki-tab__distribution-icon" /> {TYPE_LABELS[type] || type}</span>
                      <div className="wiki-tab__distribution-bar-track"><div className="wiki-tab__distribution-bar-fill" style={{ width: `${pct}%` }} /></div>
                      <span className="wiki-tab__distribution-count">{count} ({pct}%)</span>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="wiki-tab__section-card">
              <h3 className="wiki-tab__section-title">主要实体</h3>
              <div className="wiki-tab__main-entities-grid">
                {(overview.top_entities || overview.entities).slice(0, 8).map(entity => (
                  <button key={entity.id} onClick={() => { setActiveTab('entities'); fetchEntity(entity.id) }}
                    className="wiki-tab__main-entity-card">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <EntityTypeIcon type={entity.type} className="icon-sm" />
                      <span style={{ fontWeight: 600, fontSize: 13 }}>{entity.name}</span>
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{TYPE_LABELS[entity.type] || entity.type}</span>
                  </button>
                ))}
              </div>
            </div>

            {timeline.length > 0 && (
              <div className="wiki-tab__section-card">
                <h3 className="wiki-tab__section-title">最近事件</h3>
                {timeline.slice(0, 5).map((ev, i) => {
                  const evDate = ev.date || ev.time || ''
                  const evTitle = safeStr(ev.title) || safeStr(ev.description).slice(0, 50)
                  return (
                    <div key={i} style={{ display: 'flex', gap: 12, padding: '8px 0', borderBottom: i < Math.min(timeline.length, 5) - 1 ? '1px solid var(--border)' : 'none' }}>
                      <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', marginTop: 6, flexShrink: 0 }}></div>
                      <div>
                        {evDate && <p style={{ fontSize: 12, color: 'var(--accent)', fontWeight: 500 }}>{formatDate(evDate)}</p>}
                        <p style={{ fontSize: 13, fontWeight: 500 }}>{evTitle}</p>
                        {ev.description && <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>{safeStr(ev.description).slice(0, 150)}</p>}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}
        {activeTab === 'overview' && (!overview || overview.entity_count === 0) && !wikiGenerating && (
          <div className="wiki-tab__empty-state">
            <WikiIcon className="wiki-tab__empty-icon" />
            <p className="wiki-tab__empty-text">暂无 Wiki 数据</p>
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>编译完成后系统将自动生成 Wiki</p>
          </div>
        )}
        {activeTab === 'overview' && (!overview || overview.entity_count === 0) && wikiGenerating && (
          <div className="wiki-tab__empty-state">
            <div className="chat-spinner chat-spinner--accent" style={{ width: 32, height: 32, marginBottom: 12 }}></div>
            <p className="wiki-tab__empty-text">正在生成 Wiki...</p>
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>正在提取实体关系、构建时间线</p>
          </div>
        )}

        {/* ======== ENTITY DETAIL ======== */}
        {entityLoading && activeTab === 'entities' && (
          <div className="wiki-tab__loading-full"><div className="chat-spinner chat-spinner--accent"></div></div>
        )}
        {!entityLoading && activeTab === 'entities' && !selectedEntity && (
          <div className="wiki-tab__empty-state"><WikiIcon className="wiki-tab__empty-icon" /><p className="wiki-tab__empty-text">选择一个实体查看详情</p></div>
        )}
        {!entityLoading && selectedEntity && activeTab === 'entities' && (
          <EntityProfilePanel
            entity={selectedEntity}
            onEntityClick={(entityId) => fetchEntity(entityId)}
          />
        )}

        {/* ======== TIMELINE DETAIL ======== */}
        {activeTab === 'timeline' && timeline.length > 0 && (
          <div className="wiki-tab__timeline-detail">
            <h2 className="wiki-tab__timeline-detail-title">时间线总览 ({timeline.length} 事件)</h2>
            <div className="wiki-tab__timeline-detail-body">
              <div className="wiki-tab__timeline-line"></div>
              {timeline.map((ev, i) => {
                const evDate = ev.date || ev.time || ''
                const evTitle = safeStr(ev.title) || safeStr(ev.description).slice(0, 50)
                return (
                  <div key={i} className="wiki-tab__timeline-detail-item" id={`tl-${i}`}>
                    <div className="wiki-tab__timeline-detail-dot"></div>
                    <div className="wiki-tab__timeline-detail-card">
                      {evDate && <div className="wiki-tab__timeline-detail-item-date">{formatDate(evDate)}</div>}
                      <h3 className="wiki-tab__timeline-detail-item-title">{evTitle}</h3>
                      {ev.description && <p className="wiki-tab__timeline-detail-item-desc">{safeStr(ev.description)}</p>}
                      {ev.participants && ev.participants.length > 0 && (
                        <div className="wiki-tab__timeline-detail-item-participants">
                          {ev.participants.map((p, j) => (
                            <span key={j} className="wiki-tab__timeline-detail-item-participant"
                              onClick={() => {
                                const name = getParticipantName(p)
                                const ent = overview?.entities?.find(e => e.name === name)
                                if (ent) { setActiveTab('entities'); fetchEntity(ent.id) }
                              }}
                              style={{ cursor: 'pointer' }}>
                              {getParticipantName(p)}
                            </span>
                          ))}
                        </div>
                      )}
                      {ev.source_docs && ev.source_docs.length > 0 && (
                        <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
                          来源: {ev.source_docs.join(', ')}
                          {ev.confidence && <> · 置信度: {Math.round(ev.confidence * 100)}%</>}
                        </p>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
        {activeTab === 'timeline' && timeline.length === 0 && (
          <div className="wiki-tab__empty-state">
            <ClockIcon className="wiki-tab__empty-icon" />
            <p className="wiki-tab__empty-text">暂无时间线事件</p>
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>请重新编译知识库以生成时间线</p>
          </div>
        )}

        {/* ======== ANALYSIS DETAIL ======== */}
        {activeTab === 'analysis' && (analysis || crossRefs.length > 0 || surprises?.surprises?.length > 0) && (
          <div className="wiki-tab__analysis-detail">
            <div className="wiki-tab__analysis-section">
              <h3 className="wiki-tab__analysis-section-title">矛盾与疑点</h3>
              {analysis?.contradictions?.length > 0 ? analysis.contradictions.map((c: any) => (
                <div key={c.id} className={`wiki-tab__analysis-card ${c.severity === 'high' ? 'wiki-tab__analysis-card--danger' : c.severity === 'medium' ? 'wiki-tab__analysis-card--warning' : 'wiki-tab__analysis-card--neutral'}`}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 10, fontWeight: 600, background: c.severity === 'high' ? '#fef2f2' : '#fffbeb', color: c.severity === 'high' ? '#dc2626' : '#d97706' }}>{c.severity || '?'}</span>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{c.type}</span>
                  </div>
                  <p className="wiki-tab__analysis-card-desc">{c.description}</p>
                </div>
              )) : <p className="wiki-tab__analysis-empty">未发现明显矛盾</p>}

              {crossRefs.length > 0 && (
                <>
                  <h4 style={{ fontSize: 13, fontWeight: 600, margin: '16px 0 8px' }}>跨文档实体引用</h4>
                  {crossRefs.slice(0, 10).map((ref: any, i: number) => (
                    <div key={i} className="wiki-tab__analysis-card wiki-tab__analysis-card--neutral">
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: 12, fontWeight: 600 }}>{safeStr(ref.entity)}</span>
                        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>出现在 {ref.document_count} 篇文档中</span>
                      </div>
                      {ref.documents && <p style={{ fontSize: 11, color: 'var(--text-muted)' }}>{ref.documents.join(', ')}</p>}
                    </div>
                  ))}
                </>
              )}
            </div>

            <div className="wiki-tab__analysis-section">
              <h3 className="wiki-tab__analysis-section-title">知识缺口</h3>
              {analysis?.knowledge_gaps?.length > 0 ? analysis.knowledge_gaps.map((gap: any) => (
                <div key={gap.id} className="wiki-tab__analysis-card wiki-tab__analysis-card--neutral">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <GapIconRenderer type={gap.type} className="icon-sm" />
                    <span style={{ fontSize: 12, fontWeight: 500 }}>{gap.type?.replace(/_/g, ' ')}</span>
                  </div>
                  <p className="wiki-tab__analysis-card-desc">{gap.description}</p>
                  {gap.suggestion && <p className="wiki-tab__analysis-card-hint">建议: {gap.suggestion}</p>}
                </div>
              )) : <p className="wiki-tab__analysis-empty">未发现明显知识缺口</p>}
            </div>

            {analysis?.narrative_threads?.length > 0 && (
              <div className="wiki-tab__analysis-section">
                <h3 className="wiki-tab__analysis-section-title">叙事线索</h3>
                {analysis.narrative_threads.map((thread: any) => (
                  <div key={thread.id} className="wiki-tab__analysis-card wiki-tab__analysis-card--neutral">
                    <h4 style={{ fontSize: 13, fontWeight: 600, margin: '0 0 4px' }}><WikiIcon className="icon-sm" /> {thread.title}</h4>
                    <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>{thread.description}</p>
                  </div>
                ))}
              </div>
            )}

            {surprises && surprises.surprises && surprises.surprises.length > 0 && (
              <div className="wiki-tab__analysis-section">
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                  <h3 className="wiki-tab__analysis-section-title" style={{ margin: 0 }}>意外发现</h3>
                  {surprises.stats && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{surprises.stats.high_surprise} 高 · {surprises.stats.medium_surprise} 中 · {surprises.stats.low_surprise} 低</span>}
                </div>
                {surprises.surprises.map((s: any, i: number) => {
                  const scoreColor = s.score >= 0.8 ? '#dc2626' : s.score >= 0.5 ? '#d97706' : '#6b7280'
                  return (
                    <div key={i} className="wiki-tab__analysis-card wiki-tab__analysis-card--neutral">
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: 11, fontWeight: 600, padding: '1px 8px', borderRadius: 10, background: scoreColor + '15', color: scoreColor }}>{Math.round(s.score * 100)}%</span>
                        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{s.type.replace(/_/g, ' ')}</span>
                      </div>
                      <p className="wiki-tab__analysis-card-desc">{s.description}</p>
                      <p className="wiki-tab__analysis-card-hint">{s.reason}</p>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}
        {activeTab === 'analysis' && !analysis && crossRefs.length === 0 && !(surprises && surprises.surprises?.length > 0) && (
          <div className="wiki-tab__empty-state">
            <SearchIcon className="wiki-tab__empty-icon" />
            <p className="wiki-tab__empty-text">暂无分析数据</p>
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>请确保已完成编译和 Wiki 生成</p>
          </div>
        )}
      </div>
    </div>
    </WikiErrorBoundary>
  )
}
