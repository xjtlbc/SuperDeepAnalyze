import { useState, useEffect, useCallback } from 'react'
import { useAppStore } from '../../store/app'
import { WikiPageRenderer } from './WikiPageRenderer'
import { PersonIcon, FolderIcon, ClockIcon, DatabaseIcon, InfoIcon, GraphIcon, DocumentIcon, WikiIcon, FileTextIcon } from '../Icons'

const API_BASE = import.meta.env.VITE_API_BASE || ''

interface KB {
  id: string
  name: string
}

interface EntityOverview {
  id: string
  name: string
  type: string
  aliases: string[]
}

interface WikiOverview {
  entities: EntityOverview[]
  entity_count: number
  timeline_count: number
  type_counts: Record<string, number>
  relation_count: number
  contradiction_count: number
  confidence_distribution: Record<string, number>
  top_entities: Array<{ id: string; name: string; type: string; confidence: string; importance: number }>
}

interface EntityDetail {
  id: string
  name: string
  type: string
  aliases: string[]
  attributes: Record<string, unknown>
  relations: Array<{ target: string; relation: string }>
  events: Array<{ title: string; time?: string; description?: string }>
  mentions: Array<{ doc_id: string; chunk_ids: string[]; summary: string }>
}

interface TimelineEvent {
  title: string
  time?: string
  participants: string[]
  description?: string
}

function MapPinIcon({ className }: { className?: string }) {
  return (
    <svg className={className || 'icon-sm'} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  )
}

function EntityTypeIcon({ type, className = 'icon-sm' }: { type: string; className?: string }) {
  switch (type) {
    case 'person': return <PersonIcon className={className} />
    case 'location': return <MapPinIcon className={className} />
    case 'organization': return <FolderIcon className={className} />
    case 'event': return <ClockIcon className={className} />
    case 'object': return <DatabaseIcon className={className} />
    case 'concept': return <InfoIcon className={className} />
    default: return <FileTextIcon className={className} />
  }
}

const TYPE_LABELS: Record<string, string> = {
  person: '人物',
  location: '地点',
  organization: '组织',
  event: '事件',
  object: '物品',
  concept: '概念',
}

export function WikiView() {
  const { currentKbId, setCurrentKbId } = useAppStore()
  const [kbs, setKbs] = useState<KB[]>([])
  const [overview, setOverview] = useState<WikiOverview | null>(null)
  const [selectedEntity, setSelectedEntity] = useState<EntityDetail | null>(null)
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [activeTab, setActiveTab] = useState<'overview' | 'entities' | 'timeline' | 'wiki-pages'>('overview')
  const [filterType, setFilterType] = useState<string>('all')
  const [loading, setLoading] = useState(false)
  const [entityLoading, setEntityLoading] = useState(false)
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set())
  const [catalog, setCatalog] = useState<any>(null)
  const [selectedPagePath, setSelectedPagePath] = useState<string>('')
  const [selectedPageContent, setSelectedPageContent] = useState<{frontmatter: any, content: string} | null>(null)
  const [healthScore, setHealthScore] = useState<number | null>(null)
  const [healthIssueCount, setHealthIssueCount] = useState(0)

  useEffect(() => {
    fetch(`${API_BASE}/api/knowledge-bases`)
      .then(r => r.json())
      .then(data => {
        setKbs(Array.isArray(data) ? data : [])
        if (!currentKbId && data.length > 0) setCurrentKbId(data[0].id)
      })
      .catch(console.error)
  }, [])

  useEffect(() => {
    if (currentKbId) fetchWiki()
  }, [currentKbId])

  // Fetch health check
  useEffect(() => {
    if (!currentKbId) return
    fetch(`${API_BASE}/api/wiki/${currentKbId}/health`)
      .then(r => r.json())
      .then(data => {
        setHealthScore(data.score ?? null)
        setHealthIssueCount(data.issue_count ?? 0)
      })
      .catch(() => { setHealthScore(null); setHealthIssueCount(0) })
  }, [currentKbId])

  // Try to fetch wiki catalog (new system)
  useEffect(() => {
    if (!currentKbId) return
    fetch(`${API_BASE}/api/wiki/${currentKbId}/catalog`)
      .then(r => r.json())
      .then(data => {
        if (data.title) {
          setCatalog(data)
          setActiveTab('wiki-pages')
        }
      })
      .catch(() => {
        // Catalog doesn't exist, fall back to old system
        setCatalog(null)
      })
  }, [currentKbId])

  const fetchWiki = useCallback(async () => {
    if (!currentKbId) return
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/wiki/${currentKbId}`)
      if (res.ok) {
        const data = await res.json()
        setOverview(data)
      } else {
        setOverview(null)
      }
    } catch (e) {
      console.error('Failed to fetch wiki:', e)
      setOverview(null)
    }
    setLoading(false)
  }, [currentKbId])

  const fetchEntity = useCallback(async (entityId: string) => {
    if (!currentKbId) return
    setEntityLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/wiki/${currentKbId}/entity/${entityId}`)
      if (res.ok) {
        const data = await res.json()
        setSelectedEntity(data)
      }
    } catch (e) {
      console.error('Failed to fetch entity:', e)
    }
    setEntityLoading(false)
  }, [currentKbId])

  const fetchTimeline = useCallback(async () => {
    if (!currentKbId) return
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/wiki/${currentKbId}/timeline`)
      if (res.ok) {
        const data = await res.json()
        setTimeline(data.events || [])
      }
    } catch (e) {
      console.error('Failed to fetch timeline:', e)
    }
    setLoading(false)
  }, [currentKbId])

  const toggleType = (type: string) => {
    setExpandedTypes(prev => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }

  const loadWikiPage = async (path: string) => {
    if (!currentKbId) return
    try {
      const res = await fetch(`${API_BASE}/api/wiki/${currentKbId}/page?path=${encodeURIComponent(path)}`)
      const data = await res.json()
      setSelectedPagePath(path)
      setSelectedPageContent(data)
    } catch (e) {
      console.error('Failed to load wiki page:', e)
    }
  }

  if (kbs.length === 0) {
    return (
      <div className="wiki-view__empty-state">
        <WikiIcon className="wiki-view__empty-icon" />
        <p className="wiki-view__empty-text">{'暂无知识库，请先创建'}</p>
      </div>
    )
  }

  if (!currentKbId) {
    return (
      <div className="wiki-view__empty-state">
        <WikiIcon className="wiki-view__empty-icon" />
        <p className="wiki-view__empty-text wiki-view__empty-text--mb">{'选择知识库查看 Wiki'}</p>
        <select
          value=""
          onChange={(e) => setCurrentKbId(e.target.value)}
          className="wiki-view__select"
        >
          <option value="">{'请选择...'}</option>
          {kbs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
        </select>
      </div>
    )
  }

  return (
    <div className="wiki-view">
      {/* Header */}
      <div className="wiki-view__header">
        <div>
          <h1 className="wiki-view__title">{'知识 Wiki'}</h1>
          {overview && (
            <p className="wiki-view__subtitle">
              {overview.entity_count} {'实体 ·'} {overview.timeline_count} {'时间线事件'}
            </p>
          )}
        </div>
        <div className="wiki-view__header-actions">
          <select
            value={currentKbId}
            onChange={(e) => { setCurrentKbId(e.target.value); setSelectedEntity(null) }}
            className="wiki-view__select wiki-view__select--xs"
          >
            {kbs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
          </select>
          <button
            onClick={fetchWiki}
            disabled={loading}
            className="wiki-view__refresh-btn"
          >
            {loading ? '加载中...' : '刷新'}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="wiki-view__content">
        {/* Sidebar */}
        <div className="wiki-view__sidebar">
          {/* Tabs */}
          <div className="wiki-view__sidebar-tabs">
            <button
              onClick={() => { setActiveTab('overview'); setSelectedEntity(null); setSelectedPageContent(null) }}
              className={`wiki-view__sidebar-tab ${activeTab === 'overview' ? 'wiki-view__sidebar-tab--active' : ''}`}
            >
              {'概览'}
            </button>
            {catalog ? (
              <button
                onClick={() => { setActiveTab('wiki-pages'); setSelectedEntity(null); setSelectedPageContent(null) }}
                className={`wiki-view__sidebar-tab ${activeTab === 'wiki-pages' ? 'wiki-view__sidebar-tab--active' : ''}`}
              >
                {'页面'}
              </button>
            ) : (
              <button
                onClick={() => { setActiveTab('entities'); setSelectedEntity(null) }}
                className={`wiki-view__sidebar-tab ${activeTab === 'entities' ? 'wiki-view__sidebar-tab--active' : ''}`}
              >
                {'实体'}
              </button>
            )}
            <button
              onClick={() => { setActiveTab('timeline'); setSelectedEntity(null); fetchTimeline() }}
              className={`wiki-view__sidebar-tab ${activeTab === 'timeline' ? 'wiki-view__sidebar-tab--active' : ''}`}
            >
              {'时间线'}
            </button>
          </div>

          {/* Entity tree */}
          <div className="wiki-view__sidebar-body">
            {/* Wiki pages catalog tree */}
            {activeTab === 'wiki-pages' && catalog && (
              <div className="wiki-view__catalog">
                <div className="wiki-view__catalog-title">
                  {catalog.title}
                </div>
                {/* Render catalog pages recursively */}
                {(() => {
                  const renderCatalogNode = (node: any, depth: number = 0) => {
                    const items: React.ReactNode[] = []
                    const pages = node.pages || []
                    const children = node.children || []
                    for (const page of pages) {
                      items.push(
                        <button
                          key={page.path}
                          onClick={() => loadWikiPage(page.path)}
                          className={`wiki-view__catalog-page ${selectedPagePath === page.path ? 'wiki-view__catalog-page--active' : ''}`}
                          style={{ paddingLeft: `${12 + depth * 12}px` }}
                        >
                          {page.title || page.path}
                        </button>
                      )
                    }
                    for (const child of children) {
                      const childItems = renderCatalogNode(child, depth + 1)
                      items.push(
                        <div key={child.path || child.title} className="wiki-view__catalog-section">
                          <div
                            className="wiki-view__catalog-section-title"
                            style={{ paddingLeft: `${12 + depth * 12}px` }}
                          >
                            {child.title}
                          </div>
                          {childItems}
                        </div>
                      )
                    }
                    return items
                  }
                  return renderCatalogNode(catalog)
                })()}
              </div>
            )}

            {activeTab === 'entities' && loading && (
              <div className="wiki-view__loading">
                <div className="chat-spinner chat-spinner--accent"></div>
              </div>
            )}

            {activeTab === 'entities' && !loading && !overview && (
              <p className="wiki-view__empty-hint">{'暂无 Wiki 数据'}</p>
            )}

            {activeTab === 'entities' && !loading && overview && overview.entity_count === 0 && (
              <p className="wiki-view__empty-hint">{'暂无实体数据'}</p>
            )}

            {activeTab === 'entities' && overview && overview.entity_count > 0 && (
              <div className="wiki-view__entity-list">
                {/* All entities */}
                <button
                  onClick={() => { setFilterType('all'); setSelectedEntity(null) }}
                  className={`wiki-view__entity-group-btn ${filterType === 'all' ? 'wiki-view__entity-group-btn--active' : ''}`}
                >
                  <span className="font-medium">{'全部实体'}</span>
                  <span className="wiki-view__entity-count">{overview.entity_count}</span>
                </button>

                {/* Type groups */}
                {Object.entries(overview.type_counts).map(([type, count]) => (
                  <div key={type}>
                    <button
                      onClick={() => toggleType(type)}
                      className="wiki-view__entity-group-btn"
                    >
                      <span className={`wiki-view__chevron ${expandedTypes.has(type) ? 'wiki-view__chevron--expanded' : ''}`}>{'▸'}</span>
                      <EntityTypeIcon type={type} className="icon-sm" />
                      <span className="wiki-view__entity-group-label">{TYPE_LABELS[type] || type}</span>
                      <span className="wiki-view__entity-count">{count}</span>
                    </button>
                    {expandedTypes.has(type) && (
                      <div className="wiki-view__entity-sub-list">
                        {overview.entities
                          .filter(e => e.type === type)
                          .map(e => (
                            <button
                              key={e.id}
                              onClick={() => fetchEntity(e.id)}
                              className={`wiki-view__entity-item ${selectedEntity?.id === e.id ? 'wiki-view__entity-item--active' : ''}`}
                            >
                              {e.name}
                            </button>
                          ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'timeline' && (
              <div className="wiki-view__timeline-sidebar">
                {loading && (
                  <div className="wiki-view__loading">
                    <div className="chat-spinner chat-spinner--accent"></div>
                  </div>
                )}
                {!loading && timeline.length === 0 && (
                  <p className="wiki-view__empty-hint">{'暂无时间线事件'}</p>
                )}
                {timeline.map((ev, i) => (
                  <div key={i} className="wiki-view__timeline-item">
                    <div className="wiki-view__timeline-dot"></div>
                    <p className="wiki-view__timeline-item-title">{ev.title}</p>
                    {ev.time && (
                      <p className="wiki-view__timeline-item-time">{ev.time}</p>
                    )}
                    {ev.participants && ev.participants.length > 0 && (
                      <div className="wiki-view__timeline-item-participants">
                        {ev.participants.map((p, j) => (
                          <span key={j} className="wiki-view__timeline-item-participant">
                            {p}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Detail panel */}
        <div className="wiki-view__detail">
          {/* Overview tab */}
          {activeTab === 'overview' && overview && (
            <div className="wiki-view__overview">
              {/* Health score */}
              {healthScore !== null && (
                <div className={`wiki-view__health-badge ${healthScore >= 0.8 ? 'wiki-view__health-badge--good' : healthScore >= 0.5 ? 'wiki-view__health-badge--warn' : 'wiki-view__health-badge--bad'}`}>
                  <span>{'Wiki 健康度: '}{(healthScore * 100).toFixed(0)}{'%'}</span>
                  {healthIssueCount > 0 && <span className="wiki-view__health-badge-count">{'('}{healthIssueCount}{' 个问题)'}</span>}
                </div>
              )}

              {/* Stats cards */}
              <div className="wiki-view__stats-grid">
                <div className="wiki-view__stat-card">
                  <p className="wiki-view__stat-value wiki-view__stat-value--amber">{overview.entity_count}</p>
                  <p className="wiki-view__stat-label">{'实体'}</p>
                </div>
                <div className="wiki-view__stat-card">
                  <p className="wiki-view__stat-value wiki-view__stat-value--blue">{overview.relation_count || 0}</p>
                  <p className="wiki-view__stat-label">{'关系'}</p>
                </div>
                <div className="wiki-view__stat-card">
                  <p className="wiki-view__stat-value wiki-view__stat-value--green">{overview.timeline_count}</p>
                  <p className="wiki-view__stat-label">{'时间线事件'}</p>
                </div>
                <div className="wiki-view__stat-card">
                  <p className="wiki-view__stat-value wiki-view__stat-value--red">{overview.contradiction_count || 0}</p>
                  <p className="wiki-view__stat-label">{'矛盾点'}</p>
                </div>
              </div>

              {/* Type distribution */}
              {overview.type_counts && Object.keys(overview.type_counts).length > 0 && (
                <div className="wiki-view__section">
                  <h3 className="wiki-view__section-title">{'实体类型分布'}</h3>
                  <div className="wiki-view__distribution">
                    {Object.entries(overview.type_counts)
                      .sort(([, a], [, b]) => b - a)
                      .map(([type, count]) => {
                        const pct = overview.entity_count > 0 ? (count / overview.entity_count * 100) : 0
                        return (
                          <div key={type} className="wiki-view__distribution-row">
                            <span className="wiki-view__distribution-label">{TYPE_LABELS[type] || type}</span>
                            <div className="wiki-view__distribution-bar-track">
                              <div className="wiki-view__distribution-bar-fill" style={{ width: `${pct}%` }} />
                            </div>
                            <span className="wiki-view__distribution-count">{count}</span>
                          </div>
                        )
                      })}
                  </div>
                </div>
              )}

              {/* Confidence distribution */}
              {overview.confidence_distribution && (
                <div className="wiki-view__section">
                  <h3 className="wiki-view__section-title">{'置信度分布'}</h3>
                  <div className="wiki-view__confidence-grid">
                    <div className="wiki-view__confidence-card wiki-view__confidence-card--green">
                      <p className="wiki-view__confidence-value">{overview.confidence_distribution.EXTRACTED || 0}</p>
                      <p className="wiki-view__confidence-label">{'已确认 (EXTRACTED)'}</p>
                    </div>
                    <div className="wiki-view__confidence-card wiki-view__confidence-card--amber">
                      <p className="wiki-view__confidence-value">{overview.confidence_distribution.INFERRED || 0}</p>
                      <p className="wiki-view__confidence-label">{'推断 (INFERRED)'}</p>
                    </div>
                    <div className="wiki-view__confidence-card wiki-view__confidence-card--red">
                      <p className="wiki-view__confidence-value">{overview.confidence_distribution.AMBIGUOUS || 0}</p>
                      <p className="wiki-view__confidence-label">{'存疑 (AMBIGUOUS)'}</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Top entities */}
              {overview.top_entities && overview.top_entities.length > 0 && (
                <div className="wiki-view__section">
                  <h3 className="wiki-view__section-title">{'重要实体'}</h3>
                  <div className="wiki-view__top-entities-grid">
                    {overview.top_entities.map(e => (
                      <div key={e.id} className="wiki-view__top-entity-card">
                        <EntityTypeIcon type={e.type} className="icon-sm" />
                        <div className="wiki-view__top-entity-info">
                          <p className="wiki-view__top-entity-name">{e.name}</p>
                          <p className="wiki-view__top-entity-meta">{TYPE_LABELS[e.type] || e.type}{' · 置信度: '}{e.confidence}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Empty overview */}
              {overview.entity_count === 0 && (
                <div className="wiki-view__empty-state">
                  <GraphIcon className="wiki-view__empty-icon" />
                  <p className="wiki-view__empty-text">{'暂无数据，请先编译知识库'}</p>
                </div>
              )}
            </div>
          )}

          {/* Overview loading */}
          {activeTab === 'overview' && !overview && (
            <div className="wiki-view__loading-full">
              <div className="chat-spinner chat-spinner--accent"></div>
            </div>
          )}

          {/* Wiki page content */}
          {selectedPageContent && activeTab === 'wiki-pages' && (
            <div className="wiki-view__page-content">
              <WikiPageRenderer
                content={selectedPageContent.content}
                frontmatter={selectedPageContent.frontmatter}
                onWikilinkClick={(target) => loadWikiPage(target)}
              />
            </div>
          )}

          {!selectedPageContent && activeTab === 'wiki-pages' && (
            <div className="wiki-view__empty-state">
              <DocumentIcon className="wiki-view__empty-icon" />
              <p className="wiki-view__empty-text">{'选择一个页面查看内容'}</p>
            </div>
          )}

          {entityLoading && (
            <div className="wiki-view__loading-full">
              <div className="chat-spinner chat-spinner--accent"></div>
            </div>
          )}

          {!entityLoading && !selectedEntity && activeTab === 'entities' && (
            <div className="wiki-view__empty-state">
              <WikiIcon className="wiki-view__empty-icon" />
              <p className="wiki-view__empty-text">{'选择一个实体查看详情'}</p>
            </div>
          )}

          {!entityLoading && selectedEntity && (
            <div className="wiki-view__entity-detail">
              {/* Entity header */}
              <div className="wiki-view__entity-detail-header">
                <EntityTypeIcon type={selectedEntity.type} className="wiki-view__entity-detail-icon" />
                <div>
                  <h2 className="wiki-view__entity-detail-name">{selectedEntity.name}</h2>
                  <span className="wiki-view__entity-detail-meta">
                    {TYPE_LABELS[selectedEntity.type] || selectedEntity.type}{' · '}{selectedEntity.id}
                  </span>
                </div>
              </div>

              {/* Aliases */}
              {selectedEntity.aliases && selectedEntity.aliases.length > 0 && (
                <div className="wiki-view__section">
                  <h3 className="wiki-view__section-title">{'别名'}</h3>
                  <div className="wiki-view__aliases">
                    {selectedEntity.aliases.map((a, i) => (
                      <span key={i} className="wiki-view__alias-tag">
                        {a}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Attributes */}
              {selectedEntity.attributes && Object.keys(selectedEntity.attributes).length > 0 && (
                <div className="wiki-view__section">
                  <h3 className="wiki-view__section-title">{'属性'}</h3>
                  <div className="wiki-view__attrs-grid">
                    {Object.entries(selectedEntity.attributes).map(([k, v]) => (
                      <div key={k} className="wiki-view__attr-row">
                        <span className="wiki-view__attr-key">{k}</span>
                        <span className="wiki-view__attr-value">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Relations */}
              {selectedEntity.relations && selectedEntity.relations.length > 0 && (
                <div className="wiki-view__section">
                  <h3 className="wiki-view__section-title">{'关系'}</h3>
                  <div className="wiki-view__relations">
                    {selectedEntity.relations.map((rel, i) => (
                      <div key={i} className="wiki-view__relation-row">
                        <span className="wiki-view__relation-name">{selectedEntity.name}</span>
                        <span className="wiki-view__relation-arrow">{'→'}</span>
                        <span className="wiki-view__relation-label">{rel.relation}</span>
                        <span className="wiki-view__relation-arrow">{'→'}</span>
                        <span className="wiki-view__relation-name">{rel.target}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Events */}
              {selectedEntity.events && selectedEntity.events.length > 0 && (
                <div className="wiki-view__section">
                  <h3 className="wiki-view__section-title">{'相关事件'}</h3>
                  <div className="wiki-view__events">
                    {selectedEntity.events.map((ev, i) => (
                      <div key={i} className="wiki-view__event-item">
                        <p className="wiki-view__event-title">{ev.title}</p>
                        {ev.time && <p className="wiki-view__event-time">{ev.time}</p>}
                        {ev.description && <p className="wiki-view__event-desc">{ev.description}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Mentions */}
              {selectedEntity.mentions && selectedEntity.mentions.length > 0 && (
                <div className="wiki-view__section">
                  <h3 className="wiki-view__section-title">{'文档引用'}</h3>
                  <div className="wiki-view__mentions">
                    {selectedEntity.mentions.map((m, i) => (
                      <div key={i} className="wiki-view__mention-item">
                        <p className="wiki-view__mention-doc">{m.doc_id}</p>
                        <p className="wiki-view__mention-summary">{m.summary}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {!entityLoading && activeTab === 'timeline' && timeline.length > 0 && (
            <div className="wiki-view__timeline-detail">
              <h2 className="wiki-view__timeline-detail-title">{'时间线总览'}</h2>
              <div className="wiki-view__timeline-detail-body">
                <div className="wiki-view__timeline-line"></div>
                {timeline.map((ev, i) => (
                  <div key={i} className="wiki-view__timeline-detail-item">
                    <div className="wiki-view__timeline-detail-dot">
                      <span className="wiki-view__timeline-detail-num">{i + 1}</span>
                    </div>
                    <div className="wiki-view__timeline-detail-card">
                      <h3 className="wiki-view__timeline-detail-item-title">{ev.title}</h3>
                      {ev.time && <p className="wiki-view__timeline-detail-item-time">{ev.time}</p>}
                      {ev.description && <p className="wiki-view__timeline-detail-item-desc">{ev.description}</p>}
                      {ev.participants && ev.participants.length > 0 && (
                        <div className="wiki-view__timeline-detail-item-participants">
                          {ev.participants.map((p, j) => (
                            <span key={j} className="wiki-view__timeline-detail-item-participant">
                              {p}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!entityLoading && activeTab === 'timeline' && timeline.length === 0 && (
            <div className="wiki-view__empty-state">
              <ClockIcon className="wiki-view__empty-icon" />
              <p className="wiki-view__empty-text">{'点击左侧"时间线"按钮查看事件'}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
