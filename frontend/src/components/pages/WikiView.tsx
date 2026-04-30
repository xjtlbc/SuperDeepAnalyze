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
    <svg className={className || 'w-5 h-5'} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  )
}

function EntityTypeIcon({ type, className = 'w-4 h-4' }: { type: string; className?: string }) {
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
      <div className="flex flex-col items-center justify-center h-full">
        <WikiIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
        <p className="text-stone-600 dark:text-stone-300 font-medium">暂无知识库，请先创建</p>
      </div>
    )
  }

  if (!currentKbId) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <WikiIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
        <p className="text-stone-600 dark:text-stone-300 font-medium mb-4">选择知识库查看 Wiki</p>
        <select
          value=""
          onChange={(e) => setCurrentKbId(e.target.value)}
          className="px-4 py-2 rounded-lg border border-stone-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-stone-800 dark:text-stone-100 text-sm"
        >
          <option value="">请选择...</option>
          {kbs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
        </select>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-stone-800 dark:text-stone-100">知识 Wiki</h1>
          {overview && (
            <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">
              {overview.entity_count} 实体 · {overview.timeline_count} 时间线事件
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <select
            value={currentKbId}
            onChange={(e) => { setCurrentKbId(e.target.value); setSelectedEntity(null) }}
            className="px-3 py-1.5 rounded-lg border border-stone-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-stone-800 dark:text-stone-100 text-xs"
          >
            {kbs.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
          </select>
          <button
            onClick={fetchWiki}
            disabled={loading}
            className="px-3 py-1.5 bg-stone-100 hover:bg-stone-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-stone-600 dark:text-stone-300 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
          >
            {loading ? '加载中...' : '刷新'}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* Sidebar */}
        <div className="w-72 bg-white dark:bg-slate-800 rounded-xl border border-stone-200 dark:border-slate-700 flex flex-col overflow-hidden">
          {/* Tabs */}
          <div className="flex border-b border-stone-200 dark:border-slate-700">
            <button
              onClick={() => { setActiveTab('overview'); setSelectedEntity(null); setSelectedPageContent(null) }}
              className={`flex-1 px-4 py-2.5 text-xs font-medium transition-colors ${
                activeTab === 'overview'
                  ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-b-2 border-amber-500'
                  : 'text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'
              }`}
            >
              概览
            </button>
            {catalog ? (
              <button
                onClick={() => { setActiveTab('wiki-pages'); setSelectedEntity(null); setSelectedPageContent(null) }}
                className={`flex-1 px-4 py-2.5 text-xs font-medium transition-colors ${
                  activeTab === 'wiki-pages'
                    ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-b-2 border-amber-500'
                    : 'text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'
                }`}
              >
                页面
              </button>
            ) : (
              <button
                onClick={() => { setActiveTab('entities'); setSelectedEntity(null) }}
                className={`flex-1 px-4 py-2.5 text-xs font-medium transition-colors ${
                  activeTab === 'entities'
                    ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-b-2 border-amber-500'
                    : 'text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'
                }`}
              >
                实体
              </button>
            )}
            <button
              onClick={() => { setActiveTab('timeline'); setSelectedEntity(null); fetchTimeline() }}
              className={`flex-1 px-4 py-2.5 text-xs font-medium transition-colors ${
                activeTab === 'timeline'
                  ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-b-2 border-amber-500'
                  : 'text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'
              }`}
            >
              时间线
            </button>
          </div>

          {/* Entity tree */}
          <div className="flex-1 overflow-y-auto p-2">
            {/* Wiki pages catalog tree */}
            {activeTab === 'wiki-pages' && catalog && (
              <div className="space-y-1">
                <div className="px-3 py-2 text-xs font-semibold text-stone-500 dark:text-stone-400 uppercase tracking-wide">
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
                          className={`w-full text-left px-3 py-1.5 rounded-lg text-xs transition-colors ${
                            selectedPagePath === page.path
                              ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400'
                              : 'text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'
                          }`}
                          style={{ paddingLeft: `${12 + depth * 12}px` }}
                        >
                          {page.title || page.path}
                        </button>
                      )
                    }
                    for (const child of children) {
                      const childItems = renderCatalogNode(child, depth + 1)
                      items.push(
                        <div key={child.path || child.title} className="mt-1">
                          <div
                            className="px-3 py-1 text-xs font-medium text-stone-400 dark:text-stone-500"
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
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-5 w-5 border-2 border-amber-500 border-t-transparent"></div>
              </div>
            )}

            {activeTab === 'entities' && !loading && !overview && (
              <p className="text-xs text-stone-400 dark:text-stone-500 text-center py-8">暂无 Wiki 数据</p>
            )}

            {activeTab === 'entities' && !loading && overview && overview.entity_count === 0 && (
              <p className="text-xs text-stone-400 dark:text-stone-500 text-center py-8">暂无实体数据</p>
            )}

            {activeTab === 'entities' && overview && overview.entity_count > 0 && (
              <div className="space-y-1">
                {/* All entities */}
                <button
                  onClick={() => { setFilterType('all'); setSelectedEntity(null) }}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs transition-colors ${
                    filterType === 'all'
                      ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400'
                      : 'text-stone-600 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'
                  }`}
                >
                  <span className="font-medium">全部实体</span>
                  <span className="text-stone-400 dark:text-stone-500">{overview.entity_count}</span>
                </button>

                {/* Type groups */}
                {Object.entries(overview.type_counts).map(([type, count]) => (
                  <div key={type}>
                    <button
                      onClick={() => toggleType(type)}
                      className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-stone-600 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700 transition-colors"
                    >
                      <span className={`transition-transform ${expandedTypes.has(type) ? 'rotate-90' : ''}`}>▸</span>
                      <EntityTypeIcon type={type} className="w-4 h-4" />
                      <span className="flex-1 text-left">{TYPE_LABELS[type] || type}</span>
                      <span className="text-stone-400 dark:text-stone-500">{count}</span>
                    </button>
                    {expandedTypes.has(type) && (
                      <div className="ml-4 space-y-0.5 mt-0.5">
                        {overview.entities
                          .filter(e => e.type === type)
                          .map(e => (
                            <button
                              key={e.id}
                              onClick={() => fetchEntity(e.id)}
                              className={`w-full text-left px-3 py-1.5 rounded-lg text-xs transition-colors truncate ${
                                selectedEntity?.id === e.id
                                  ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400'
                                  : 'text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'
                              }`}
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
              <div className="space-y-2">
                {loading && (
                  <div className="flex items-center justify-center py-8">
                    <div className="animate-spin rounded-full h-5 w-5 border-2 border-amber-500 border-t-transparent"></div>
                  </div>
                )}
                {!loading && timeline.length === 0 && (
                  <p className="text-xs text-stone-400 dark:text-stone-500 text-center py-8">暂无时间线事件</p>
                )}
                {timeline.map((ev, i) => (
                  <div key={i} className="relative pl-4 border-l-2 border-amber-300 dark:border-amber-700">
                    <div className="absolute -left-1.5 top-0 w-3 h-3 rounded-full bg-amber-400 dark:bg-amber-600 border-2 border-white dark:border-slate-800"></div>
                    <p className="text-xs font-medium text-stone-700 dark:text-stone-300">{ev.title}</p>
                    {ev.time && (
                      <p className="text-xs text-stone-400 dark:text-stone-500 mt-0.5 font-mono">{ev.time}</p>
                    )}
                    {ev.participants && ev.participants.length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {ev.participants.map((p, j) => (
                          <span key={j} className="px-1.5 py-0.5 bg-stone-100 dark:bg-slate-700 rounded text-xs text-stone-500 dark:text-stone-400">
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
        <div className="flex-1 bg-white dark:bg-slate-800 rounded-xl border border-stone-200 dark:border-slate-700 overflow-y-auto">
          {/* Overview tab */}
          {activeTab === 'overview' && overview && (
            <div className="p-6">
              {/* Health score */}
              {healthScore !== null && (
                <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full mb-6 text-sm font-semibold ${
                  healthScore >= 0.8 ? 'bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400' :
                  healthScore >= 0.5 ? 'bg-amber-100 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400' :
                  'bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-400'
                }`}>
                  <span>Wiki 健康度: {(healthScore * 100).toFixed(0)}%</span>
                  {healthIssueCount > 0 && <span className="text-xs opacity-70">({healthIssueCount} 个问题)</span>}
                </div>
              )}

              {/* Stats cards */}
              <div className="grid grid-cols-4 gap-4 mb-6">
                <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-amber-600 dark:text-amber-400">{overview.entity_count}</p>
                  <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">实体</p>
                </div>
                <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">{overview.relation_count || 0}</p>
                  <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">关系</p>
                </div>
                <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-green-600 dark:text-green-400">{overview.timeline_count}</p>
                  <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">时间线事件</p>
                </div>
                <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-red-600 dark:text-red-400">{overview.contradiction_count || 0}</p>
                  <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">矛盾点</p>
                </div>
              </div>

              {/* Type distribution */}
              {overview.type_counts && Object.keys(overview.type_counts).length > 0 && (
                <div className="mb-6">
                  <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-3">实体类型分布</h3>
                  <div className="space-y-2">
                    {Object.entries(overview.type_counts)
                      .sort(([, a], [, b]) => b - a)
                      .map(([type, count]) => {
                        const pct = overview.entity_count > 0 ? (count / overview.entity_count * 100) : 0
                        return (
                          <div key={type} className="flex items-center gap-3">
                            <span className="w-16 text-xs text-stone-500 dark:text-stone-400">{TYPE_LABELS[type] || type}</span>
                            <div className="flex-1 bg-stone-100 dark:bg-slate-700 rounded-full h-3 overflow-hidden">
                              <div className="h-full bg-amber-400 dark:bg-amber-600 rounded-full transition-all" style={{ width: `${pct}%` }} />
                            </div>
                            <span className="text-xs text-stone-400 w-8 text-right">{count}</span>
                          </div>
                        )
                      })}
                  </div>
                </div>
              )}

              {/* Confidence distribution */}
              {overview.confidence_distribution && (
                <div className="mb-6">
                  <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-3">置信度分布</h3>
                  <div className="flex gap-4">
                    <div className="flex-1 bg-green-50 dark:bg-green-900/10 rounded-lg p-3 text-center">
                      <p className="text-lg font-bold text-green-600 dark:text-green-400">{overview.confidence_distribution.EXTRACTED || 0}</p>
                      <p className="text-xs text-stone-500 dark:text-stone-400">已确认 (EXTRACTED)</p>
                    </div>
                    <div className="flex-1 bg-amber-50 dark:bg-amber-900/10 rounded-lg p-3 text-center">
                      <p className="text-lg font-bold text-amber-600 dark:text-amber-400">{overview.confidence_distribution.INFERRED || 0}</p>
                      <p className="text-xs text-stone-500 dark:text-stone-400">推断 (INFERRED)</p>
                    </div>
                    <div className="flex-1 bg-red-50 dark:bg-red-900/10 rounded-lg p-3 text-center">
                      <p className="text-lg font-bold text-red-600 dark:text-red-400">{overview.confidence_distribution.AMBIGUOUS || 0}</p>
                      <p className="text-xs text-stone-500 dark:text-stone-400">存疑 (AMBIGUOUS)</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Top entities */}
              {overview.top_entities && overview.top_entities.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-3">重要实体</h3>
                  <div className="grid grid-cols-2 gap-2">
                    {overview.top_entities.map(e => (
                      <div key={e.id} className="flex items-center gap-2 px-3 py-2 bg-stone-50 dark:bg-slate-700/50 rounded-lg">
                        <EntityTypeIcon type={e.type} className="w-4 h-4" />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium text-stone-700 dark:text-stone-300 truncate">{e.name}</p>
                          <p className="text-xs text-stone-400">{TYPE_LABELS[e.type] || e.type} · 置信度: {e.confidence}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Empty overview */}
              {overview.entity_count === 0 && (
                <div className="flex flex-col items-center justify-center py-12">
                  <GraphIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
                  <p className="text-stone-500 dark:text-stone-400">暂无数据，请先编译知识库</p>
                </div>
              )}
            </div>
          )}

          {/* Overview loading */}
          {activeTab === 'overview' && !overview && (
            <div className="flex items-center justify-center h-full">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent"></div>
            </div>
          )}

          {/* Wiki page content */}
          {selectedPageContent && activeTab === 'wiki-pages' && (
            <div className="p-6">
              <WikiPageRenderer
                content={selectedPageContent.content}
                frontmatter={selectedPageContent.frontmatter}
                onWikilinkClick={(target) => loadWikiPage(target)}
              />
            </div>
          )}

          {!selectedPageContent && activeTab === 'wiki-pages' && (
            <div className="flex flex-col items-center justify-center h-full">
              <DocumentIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
              <p className="text-stone-500 dark:text-stone-400">选择一个页面查看内容</p>
            </div>
          )}

          {entityLoading && (
            <div className="flex items-center justify-center h-full">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent"></div>
            </div>
          )}

          {!entityLoading && !selectedEntity && activeTab === 'entities' && (
            <div className="flex flex-col items-center justify-center h-full">
              <WikiIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
              <p className="text-stone-500 dark:text-stone-400">选择一个实体查看详情</p>
            </div>
          )}

          {!entityLoading && selectedEntity && (
            <div className="p-6">
              {/* Entity header */}
              <div className="flex items-center gap-3 mb-6 pb-4 border-b border-stone-200 dark:border-slate-700">
                <EntityTypeIcon type={selectedEntity.type} className="w-6 h-6" />
                <div>
                  <h2 className="text-xl font-bold text-stone-800 dark:text-stone-100">{selectedEntity.name}</h2>
                  <span className="text-xs text-stone-400 dark:text-stone-500">
                    {TYPE_LABELS[selectedEntity.type] || selectedEntity.type} · {selectedEntity.id}
                  </span>
                </div>
              </div>

              {/* Aliases */}
              {selectedEntity.aliases && selectedEntity.aliases.length > 0 && (
                <div className="mb-6">
                  <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-2">别名</h3>
                  <div className="flex gap-2 flex-wrap">
                    {selectedEntity.aliases.map((a, i) => (
                      <span key={i} className="px-2 py-1 bg-stone-100 dark:bg-slate-700 rounded text-xs text-stone-600 dark:text-stone-300">
                        {a}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Attributes */}
              {selectedEntity.attributes && Object.keys(selectedEntity.attributes).length > 0 && (
                <div className="mb-6">
                  <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-2">属性</h3>
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(selectedEntity.attributes).map(([k, v]) => (
                      <div key={k} className="flex justify-between px-3 py-2 bg-stone-50 dark:bg-slate-700/50 rounded-lg">
                        <span className="text-xs text-stone-500 dark:text-stone-400">{k}</span>
                        <span className="text-xs text-stone-700 dark:text-stone-300">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Relations */}
              {selectedEntity.relations && selectedEntity.relations.length > 0 && (
                <div className="mb-6">
                  <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-2">关系</h3>
                  <div className="space-y-1">
                    {selectedEntity.relations.map((rel, i) => (
                      <div key={i} className="flex items-center gap-2 px-3 py-2 bg-stone-50 dark:bg-slate-700/50 rounded-lg">
                        <span className="text-xs text-stone-700 dark:text-stone-300">{selectedEntity.name}</span>
                        <span className="text-xs text-amber-500">→</span>
                        <span className="text-xs text-stone-500 dark:text-stone-400 italic">{rel.relation}</span>
                        <span className="text-xs text-amber-500">→</span>
                        <span className="text-xs text-stone-700 dark:text-stone-300">{rel.target}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Events */}
              {selectedEntity.events && selectedEntity.events.length > 0 && (
                <div className="mb-6">
                  <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-2">相关事件</h3>
                  <div className="space-y-2">
                    {selectedEntity.events.map((ev, i) => (
                      <div key={i} className="relative pl-4 border-l-2 border-amber-300 dark:border-amber-700">
                        <p className="text-sm font-medium text-stone-700 dark:text-stone-300">{ev.title}</p>
                        {ev.time && <p className="text-xs text-stone-400 dark:text-stone-500 font-mono">{ev.time}</p>}
                        {ev.description && <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">{ev.description}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Mentions */}
              {selectedEntity.mentions && selectedEntity.mentions.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-2">文档引用</h3>
                  <div className="space-y-2">
                    {selectedEntity.mentions.map((m, i) => (
                      <div key={i} className="px-3 py-2 bg-stone-50 dark:bg-slate-700/50 rounded-lg">
                        <p className="text-xs font-mono text-amber-600 dark:text-amber-400 mb-1">{m.doc_id}</p>
                        <p className="text-xs text-stone-600 dark:text-stone-300 line-clamp-2">{m.summary}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {!entityLoading && activeTab === 'timeline' && timeline.length > 0 && (
            <div className="p-6">
              <h2 className="text-lg font-bold text-stone-800 dark:text-stone-100 mb-4">时间线总览</h2>
              <div className="relative pl-8">
                <div className="absolute left-3 top-0 bottom-0 w-0.5 bg-amber-300 dark:bg-amber-700"></div>
                {timeline.map((ev, i) => (
                  <div key={i} className="relative mb-6">
                    <div className="absolute -left-8 top-1 w-6 h-6 rounded-full bg-amber-400 dark:bg-amber-600 border-4 border-white dark:border-slate-800 flex items-center justify-center">
                      <span className="text-xs text-white font-bold">{i + 1}</span>
                    </div>
                    <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-3">
                      <h3 className="text-sm font-semibold text-stone-700 dark:text-stone-300">{ev.title}</h3>
                      {ev.time && <p className="text-xs font-mono text-amber-600 dark:text-amber-400 mt-1">{ev.time}</p>}
                      {ev.description && <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">{ev.description}</p>}
                      {ev.participants && ev.participants.length > 0 && (
                        <div className="flex gap-1 mt-2 flex-wrap">
                          {ev.participants.map((p, j) => (
                            <span key={j} className="px-2 py-0.5 bg-amber-100 dark:bg-amber-900/30 rounded text-xs text-amber-700 dark:text-amber-400">
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
            <div className="flex flex-col items-center justify-center h-full">
              <ClockIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
              <p className="text-stone-500 dark:text-stone-400">点击左侧"时间线"按钮查看事件</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
