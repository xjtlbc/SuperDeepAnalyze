import { useState, useEffect } from 'react'
import { API_BASE, TYPE_LABELS } from './shared'
import { EntityTypeIcon, GapIconRenderer } from './EntityIcon'
import { WikiPageRenderer } from '../WikiPageRenderer'
import { WikiIcon, ClockIcon, DocumentIcon, SearchIcon, WarningIcon, ExternalLinkIcon, InfoIcon } from '../../Icons'

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
  type_counts: Record<string, number>
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

export function WikiTab({ kbId, refreshKey = 0 }: { kbId: string; refreshKey?: number }) {
  return <EmbeddedWikiView kbId={kbId} refreshKey={refreshKey} />
}

function EmbeddedWikiView({ kbId, refreshKey = 0 }: { kbId: string; refreshKey?: number }) {
  const [overview, setOverview] = useState<WikiOverview | null>(null)
  const [selectedEntity, setSelectedEntity] = useState<EntityDetail | null>(null)
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [activeTab, setActiveTab] = useState<'overview' | 'pages' | 'entities' | 'timeline' | 'analysis'>('overview')
  const [filterType, setFilterType] = useState<string>('all')
  const [loading, setLoading] = useState(false)
  const [entityLoading, setEntityLoading] = useState(false)
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set())
  const [catalog, setCatalog] = useState<any>(null)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [selectedPagePath, setSelectedPagePath] = useState<string>('')
  const [selectedPageContent, setSelectedPageContent] = useState<{ frontmatter: Record<string, any>; content: string } | null>(null)
  const [wikiPageLoading, setWikiPageLoading] = useState(false)
  const [analysis, setAnalysis] = useState<any>(null)
  const [crossRefs, setCrossRefs] = useState<any[]>([])
  const [surprises, setSurprises] = useState<any>(null)
  const [selectedDocPreview, setSelectedDocPreview] = useState<{ doc_id: string; content: string } | null>(null)

  useEffect(() => { fetchWiki(); fetchTimeline() }, [kbId, refreshKey])

  useEffect(() => {
    setCatalogLoading(true)
    fetch(`${API_BASE}/api/wiki/${kbId}/catalog`)
      .then(r => r.json())
      .then(data => { if (data && data.title) setCatalog(data) })
      .catch(() => setCatalog(null))
      .finally(() => setCatalogLoading(false))
  }, [kbId])

  useEffect(() => {
    fetch(`${API_BASE}/api/wiki/${kbId}/analysis`)
      .then(r => r.json())
      .then(data => setAnalysis(data))
      .catch(() => setAnalysis(null))
  }, [kbId])

  useEffect(() => {
    fetch(`${API_BASE}/api/wiki/${kbId}/cross_refs`)
      .then(r => r.json())
      .then(data => setCrossRefs(data.cross_refs || []))
      .catch(() => setCrossRefs([]))
  }, [kbId])

  useEffect(() => {
    fetch(`${API_BASE}/api/wiki/${kbId}/surprises`)
      .then(r => r.json())
      .then(data => setSurprises(data))
      .catch(() => setSurprises(null))
  }, [kbId])

  const fetchWiki = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/wiki/${kbId}`)
      if (res.ok) { const data = await res.json(); setOverview(data) } else { setOverview(null) }
    } catch (e) { console.error('Failed to fetch wiki:', e); setOverview(null) }
    setLoading(false)
  }

  const fetchEntity = async (entityId: string) => {
    setEntityLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/wiki/${kbId}/entity/${entityId}`)
      if (res.ok) { const data = await res.json(); setSelectedEntity(data) }
    } catch (e) { console.error('Failed to fetch entity:', e) }
    setEntityLoading(false)
  }

  const fetchTimeline = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/wiki/${kbId}/timeline`)
      if (res.ok) { const data = await res.json(); setTimeline(data.events || []) }
    } catch (e) { console.error('Failed to fetch timeline:', e) }
    setLoading(false)
  }

  const loadWikiPage = async (path: string) => {
    setWikiPageLoading(true)
    setSelectedPagePath(path)
    setSelectedPageContent(null)
    try {
      const res = await fetch(`${API_BASE}/api/wiki/${kbId}/page?path=${encodeURIComponent(path)}`)
      if (!res.ok) { setSelectedPageContent(null); return }
      const data = await res.json()
      setSelectedPageContent(data)
    } catch (e) { console.error('Failed to load wiki page:', e); setSelectedPageContent(null) }
    setWikiPageLoading(false)
  }

  const loadDocumentPreview = async (docId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/documents/${kbId}/${docId}/parsed`)
      if (res.ok) {
        const data = await res.json()
        setSelectedDocPreview({ doc_id: docId, content: data.content })
      }
    } catch (e) { console.error('Failed to load document preview:', e) }
  }

  const handleSourceClick = (docId: string) => { loadDocumentPreview(docId) }

  const toggleType = (type: string) => {
    setExpandedTypes(prev => { const next = new Set(prev); if (next.has(type)) next.delete(type); else next.add(type); return next })
  }

  const renderCatalogNode = (node: any, depth: number = 0, parentPath: string = ''): React.ReactNode => {
    const indent = depth * 12
    const fullPath = parentPath ? `${parentPath}/${node.path}` : node.path
    if (node.node_type === 'page') {
      return (
        <button
          key={node.path}
          onClick={() => loadWikiPage(fullPath)}
          className={`w-full text-left px-2 py-1.5 text-sm rounded-lg transition-colors truncate ${
            selectedPagePath === fullPath
              ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 font-medium'
              : 'text-stone-600 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'
          }`}
          style={{ paddingLeft: `${indent + 8}px` }}
          title={node.title}
        >
          {node.title}
        </button>
      )
    }
    return (
      <div key={node.path}>
        <div className="px-2 py-1 text-xs font-semibold text-stone-400 dark:text-stone-500 uppercase tracking-wide" style={{ paddingLeft: `${indent + 8}px` }}>
          {node.title}
        </div>
        {node.children?.map((child: any) => renderCatalogNode(child, depth + 1, fullPath))}
      </div>
    )
  }

  return (
    <div className="h-full flex gap-4 min-h-0">
      {/* Sidebar */}
      <div className="w-72 bg-white dark:bg-slate-800 rounded-xl border border-stone-200 dark:border-slate-700 flex flex-col overflow-hidden">
        <div className="flex border-b border-stone-200 dark:border-slate-700">
          <button onClick={() => { setActiveTab('overview'); setSelectedEntity(null); setSelectedPagePath(''); setSelectedPageContent(null) }} className={`flex-1 px-3 py-2 text-xs font-medium transition-colors ${activeTab === 'overview' ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-b-2 border-amber-500' : 'text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'}`}>总览</button>
          <button onClick={() => { setActiveTab('pages'); setSelectedEntity(null) }} className={`flex-1 px-3 py-2 text-xs font-medium transition-colors ${activeTab === 'pages' ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-b-2 border-amber-500' : 'text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'}`}>页面</button>
          <button onClick={() => { setActiveTab('entities'); setSelectedEntity(null) }} className={`flex-1 px-3 py-2 text-xs font-medium transition-colors ${activeTab === 'entities' ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-b-2 border-amber-500' : 'text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'}`}>实体</button>
          <button onClick={() => { setActiveTab('timeline'); setSelectedEntity(null) }} className={`flex-1 px-3 py-2 text-xs font-medium transition-colors ${activeTab === 'timeline' ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-b-2 border-amber-500' : 'text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'}`}>时间线</button>
          <button onClick={() => { setActiveTab('analysis'); setSelectedEntity(null) }} className={`flex-1 px-3 py-2 text-xs font-medium transition-colors ${activeTab === 'analysis' ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border-b-2 border-amber-500' : 'text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'}`}>分析</button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {/* Overview Tab */}
          {activeTab === 'overview' && loading && <div className="flex items-center justify-center py-8"><div className="animate-spin rounded-full h-5 w-5 border-2 border-amber-500 border-t-transparent"></div></div>}
          {activeTab === 'overview' && !loading && !overview && <p className="text-xs text-stone-400 dark:text-stone-500 text-center py-8">暂无 Wiki 数据，请先编译</p>}
          {activeTab === 'overview' && !loading && overview && overview.entity_count === 0 && <p className="text-xs text-stone-400 dark:text-stone-500 text-center py-8">暂无实体数据</p>}
          {activeTab === 'overview' && overview && overview.entity_count > 0 && (
            <div className="space-y-3">
              <div className="text-xs text-stone-500 dark:text-stone-400 text-center pb-2 border-b border-stone-200 dark:border-slate-700">
                {overview.entity_count} 实体 · {overview.timeline_count} 事件 · {Object.keys(overview.type_counts).length} 类型
              </div>
              {Object.entries(overview.type_counts).map(([type, count]) => (
                <button key={type} onClick={() => { setActiveTab('entities'); setFilterType(type); setExpandedTypes(prev => { const next = new Set(prev); next.add(type); return next }) }}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-stone-600 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700 transition-colors">
                  <EntityTypeIcon type={type} className="w-4 h-4" />
                  <span className="flex-1 text-left">{TYPE_LABELS[type] || type}</span>
                  <span className="text-stone-400 dark:text-stone-500">{count}</span>
                </button>
              ))}
              {timeline.length > 0 && (
                <div className="pt-2 border-t border-stone-200 dark:border-slate-700">
                  <p className="text-xs font-medium text-stone-500 dark:text-stone-400 mb-1">最近事件</p>
                  {timeline.slice(0, 3).map((ev, i) => (
                    <div key={i} className="px-3 py-1.5 text-xs text-stone-600 dark:text-stone-400">
                      <p className="truncate">{ev.title}</p>
                      {ev.time && <p className="text-stone-400 dark:text-stone-500 font-mono">{ev.time}</p>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Entities Tab */}
          {activeTab === 'entities' && loading && <div className="flex items-center justify-center py-8"><div className="animate-spin rounded-full h-5 w-5 border-2 border-amber-500 border-t-transparent"></div></div>}
          {activeTab === 'entities' && !loading && !overview && <p className="text-xs text-stone-400 dark:text-stone-500 text-center py-8">暂无 Wiki 数据，请先编译</p>}
          {activeTab === 'entities' && !loading && overview && overview.entity_count === 0 && <p className="text-xs text-stone-400 dark:text-stone-500 text-center py-8">暂无实体数据</p>}
          {activeTab === 'entities' && overview && overview.entity_count > 0 && (
            <div className="space-y-1">
              <button onClick={() => { setFilterType('all'); setSelectedEntity(null) }} className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs transition-colors ${filterType === 'all' ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400' : 'text-stone-600 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'}`}><span className="font-medium">全部实体</span><span className="text-stone-400 dark:text-stone-500">{overview.entity_count}</span></button>
              {Object.entries(overview.type_counts).map(([type, count]) => (
                <div key={type}>
                  <button onClick={() => toggleType(type)} className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-stone-600 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700 transition-colors"><span className={`transition-transform ${expandedTypes.has(type) ? 'rotate-90' : ''}`}>▸</span><EntityTypeIcon type={type} className="w-4 h-4" /><span className="flex-1 text-left">{TYPE_LABELS[type] || type}</span><span className="text-stone-400 dark:text-stone-500">{count}</span></button>
                  {expandedTypes.has(type) && (
                    <div className="ml-4 space-y-0.5 mt-0.5">
                      {overview.entities.filter(e => e.type === type).map(e => (
                        <button key={e.id} onClick={() => fetchEntity(e.id)} className={`w-full text-left px-3 py-1.5 rounded-lg text-xs transition-colors truncate ${selectedEntity?.id === e.id ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400' : 'text-stone-500 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'}`}>{e.name}</button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Timeline Tab */}
          {activeTab === 'timeline' && (
            <div className="space-y-2">
              {loading && <div className="flex items-center justify-center py-8"><div className="animate-spin rounded-full h-5 w-5 border-2 border-amber-500 border-t-transparent"></div></div>}
              {!loading && timeline.length === 0 && <p className="text-xs text-stone-400 dark:text-stone-500 text-center py-8">暂无时间线事件</p>}
              {timeline.map((ev, i) => (
                <div key={i} className="relative pl-4 border-l-2 border-amber-300 dark:border-amber-700"><div className="absolute -left-1.5 top-0 w-3 h-3 rounded-full bg-amber-400 dark:bg-amber-600 border-2 border-white dark:border-slate-800"></div><p className="text-xs font-medium text-stone-700 dark:text-stone-300">{ev.title}</p>{ev.time && <p className="text-xs text-stone-400 dark:text-stone-500 mt-0.5 font-mono">{ev.time}</p>}{ev.participants && ev.participants.length > 0 && (<div className="flex gap-1 mt-1 flex-wrap">{ev.participants.map((p, j) => (<span key={j} className="px-1.5 py-0.5 bg-stone-100 dark:bg-slate-700 rounded text-xs text-stone-500 dark:text-stone-400">{p}</span>))}</div>)}</div>
              ))}
            </div>
          )}

          {/* Pages Tab */}
          {activeTab === 'pages' && catalogLoading && (
            <div className="flex items-center justify-center py-8"><div className="animate-spin rounded-full h-5 w-5 border-2 border-amber-500 border-t-transparent"></div></div>
          )}
          {activeTab === 'pages' && !catalogLoading && catalog && (
            <div className="space-y-0">{renderCatalogNode(catalog, 0)}</div>
          )}
          {activeTab === 'pages' && !catalogLoading && !catalog && (
            <p className="text-xs text-stone-400 dark:text-stone-500 text-center py-8">暂无 Wiki 页面，请先编译知识库</p>
          )}

          {/* Analysis Tab sidebar */}
          {activeTab === 'analysis' && (
            <div className="space-y-1">
              {analysis && analysis.contradictions && analysis.contradictions.length > 0 && (
                <button onClick={() => setActiveTab('analysis')} className="w-full text-left px-3 py-2 rounded-lg text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">
                  <WarningIcon className="w-4 h-4 inline" /> {analysis.contradictions.length} 个矛盾
                </button>
              )}
              {crossRefs.length > 0 && <div className="px-3 py-1 text-xs text-stone-400 dark:text-stone-500"><ExternalLinkIcon className="w-3.5 h-3.5 inline" /> {crossRefs.length} 个跨文档矛盾</div>}
              {analysis && analysis.knowledge_gaps && analysis.knowledge_gaps.length > 0 && <div className="px-3 py-1 text-xs text-amber-600 dark:text-amber-400"><GapIconRenderer type="isolated_entity" className="w-3.5 h-3.5 inline" /> {analysis.knowledge_gaps.length} 个知识缺口</div>}
              {analysis && analysis.narrative_threads && analysis.narrative_threads.length > 0 && <div className="px-3 py-1 text-xs text-blue-600 dark:text-blue-400"><WikiIcon className="w-3.5 h-3.5 inline" /> {analysis.narrative_threads.length} 条叙事线索</div>}
              {surprises && surprises.stats && surprises.stats.total_surprises > 0 && <div className="px-3 py-1 text-xs text-purple-600 dark:text-purple-400"><InfoIcon className="w-3.5 h-3.5 inline" /> {surprises.stats.total_surprises} 个发现 ({surprises.stats.high_surprise} 高惊喜)</div>}
              {!analysis && <p className="text-xs text-stone-400 dark:text-stone-500 text-center py-4">暂无分析数据</p>}
            </div>
          )}
        </div>
      </div>

      {/* Detail panel */}
      <div className="flex-1 bg-white dark:bg-slate-800 rounded-xl border border-stone-200 dark:border-slate-700 overflow-y-auto">
        {/* Overview detail */}
        {activeTab === 'overview' && overview && overview.entity_count > 0 && (
          <div className="p-6 space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4"><p className="text-xs text-stone-500 dark:text-stone-400">实体总数</p><p className="text-2xl font-bold text-stone-800 dark:text-stone-100">{overview.entity_count}</p></div>
              <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4"><p className="text-xs text-stone-500 dark:text-stone-400">时间线事件</p><p className="text-2xl font-bold text-stone-800 dark:text-stone-100">{overview.timeline_count}</p></div>
              <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4"><p className="text-xs text-stone-500 dark:text-stone-400">实体类型</p><p className="text-2xl font-bold text-stone-800 dark:text-stone-100">{Object.keys(overview.type_counts).length}</p></div>
              <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-4"><p className="text-xs text-stone-500 dark:text-stone-400">人物</p><p className="text-2xl font-bold text-stone-800 dark:text-stone-100">{overview.type_counts.person || 0}</p></div>
            </div>
            <div className="bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700 p-4">
              <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-3">实体类型分布</h3>
              <div className="space-y-2">
                {Object.entries(overview.type_counts).map(([type, count]) => {
                  const percentage = Math.round((count / overview.entity_count) * 100)
                  return (
                    <div key={type} className="flex items-center gap-3">
                      <span className="text-xs w-20 text-stone-500 dark:text-stone-400"><EntityTypeIcon type={type} className="w-3.5 h-3.5 inline" /> {TYPE_LABELS[type] || type}</span>
                      <div className="flex-1 bg-stone-200 dark:bg-slate-700 rounded-full h-4 overflow-hidden"><div className="h-full bg-amber-500 rounded-full transition-all" style={{ width: `${percentage}%` }} /></div>
                      <span className="text-xs text-stone-500 dark:text-stone-400 w-20 text-right">{count} ({percentage}%)</span>
                    </div>
                  )
                })}
              </div>
            </div>
            <div className="bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700 p-4">
              <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-3">主要实体</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {overview.entities.slice(0, 6).map(entity => (
                  <button key={entity.id} onClick={() => { setActiveTab('entities'); fetchEntity(entity.id) }}
                    className="flex items-center gap-2 p-3 bg-stone-50 dark:bg-slate-700/50 rounded-lg hover:bg-amber-50 dark:hover:bg-amber-900/20 transition-colors text-left">
                    <span className="text-lg"><EntityTypeIcon type={entity.type} className="w-5 h-5" /></span>
                    <div className="min-w-0"><p className="text-sm font-medium text-stone-700 dark:text-stone-300 truncate">{entity.name}</p><p className="text-xs text-stone-400 dark:text-stone-500">{TYPE_LABELS[entity.type] || entity.type}</p></div>
                  </button>
                ))}
              </div>
            </div>
            {timeline.length > 0 && (
              <div className="bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700 p-4">
                <h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-3">最近事件</h3>
                <div className="space-y-2">
                  {timeline.slice(0, 5).map((ev, i) => (
                    <div key={i} className="flex items-start gap-3 p-3 bg-stone-50 dark:bg-slate-700/50 rounded-lg">
                      <div className="w-2 h-2 rounded-full bg-amber-400 dark:bg-amber-600 mt-1.5 flex-shrink-0"></div>
                      <div className="min-w-0"><p className="text-sm text-stone-700 dark:text-stone-300">{ev.title}</p>{ev.time && <p className="text-xs text-stone-400 dark:text-stone-500 font-mono">{ev.time}</p>}{ev.description && <p className="text-xs text-stone-500 dark:text-stone-400 mt-0.5 line-clamp-2">{ev.description}</p>}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        {activeTab === 'overview' && (!overview || overview.entity_count === 0) && (
          <div className="flex flex-col items-center justify-center h-full"><WikiIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" /><p className="text-stone-500 dark:text-stone-400">暂无 Wiki 数据，请先编译知识库</p></div>
        )}

        {/* Entity detail */}
        {entityLoading && activeTab === 'entities' && <div className="flex items-center justify-center h-full"><div className="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent"></div></div>}
        {!entityLoading && activeTab === 'entities' && !selectedEntity && <div className="flex flex-col items-center justify-center h-full"><WikiIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" /><p className="text-stone-500 dark:text-stone-400">选择一个实体查看详情</p></div>}
        {!entityLoading && selectedEntity && activeTab === 'entities' && (
          <div className="p-6">
            <div className="flex items-center gap-3 mb-6 pb-4 border-b border-stone-200 dark:border-slate-700"><span className="text-2xl"><EntityTypeIcon type={selectedEntity.type} className="w-6 h-6" /></span><div><h2 className="text-xl font-bold text-stone-800 dark:text-stone-100">{selectedEntity.name}</h2><span className="text-xs text-stone-400 dark:text-stone-500">{TYPE_LABELS[selectedEntity.type] || selectedEntity.type} · {selectedEntity.id}</span></div></div>
            {selectedEntity.aliases && selectedEntity.aliases.length > 0 && (<div className="mb-6"><h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-2">别名</h3><div className="flex gap-2 flex-wrap">{selectedEntity.aliases.map((a, i) => (<span key={i} className="px-2 py-1 bg-stone-100 dark:bg-slate-700 rounded text-xs text-stone-600 dark:text-stone-300">{a}</span>))}</div></div>)}
            {selectedEntity.attributes && Object.keys(selectedEntity.attributes).length > 0 && (<div className="mb-6"><h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-2">属性</h3><div className="grid grid-cols-2 gap-2">{Object.entries(selectedEntity.attributes).map(([k, v]) => (<div key={k} className="flex justify-between px-3 py-2 bg-stone-50 dark:bg-slate-700/50 rounded-lg"><span className="text-xs text-stone-500 dark:text-stone-400">{k}</span><span className="text-xs text-stone-700 dark:text-stone-300">{String(v)}</span></div>))}</div></div>)}
            {selectedEntity.relations && selectedEntity.relations.length > 0 && (<div className="mb-6"><h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-2">关系</h3><div className="space-y-1">{selectedEntity.relations.map((rel, i) => (<div key={i} className="flex items-center gap-2 px-3 py-2 bg-stone-50 dark:bg-slate-700/50 rounded-lg"><span className="text-xs text-stone-700 dark:text-stone-300">{selectedEntity.name}</span><span className="text-xs text-amber-500">→</span><span className="text-xs text-stone-500 dark:text-stone-400 italic">{rel.relation}</span><span className="text-xs text-amber-500">→</span><span className="text-xs text-stone-700 dark:text-stone-300">{rel.target}</span></div>))}</div></div>)}
            {selectedEntity.events && selectedEntity.events.length > 0 && (<div className="mb-6"><h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-2">相关事件</h3><div className="space-y-2">{selectedEntity.events.map((ev, i) => (<div key={i} className="relative pl-4 border-l-2 border-amber-300 dark:border-amber-700"><p className="text-sm font-medium text-stone-700 dark:text-stone-300">{ev.title}</p>{ev.time && <p className="text-xs text-stone-400 dark:text-stone-500 font-mono">{ev.time}</p>}{ev.description && <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">{ev.description}</p>}</div>))}</div></div>)}
            {selectedEntity.mentions && selectedEntity.mentions.length > 0 && (<div><h3 className="text-sm font-semibold text-stone-600 dark:text-stone-400 mb-2">文档引用</h3><div className="space-y-2">{selectedEntity.mentions.map((m, i) => (<div key={i} className="px-3 py-2 bg-stone-50 dark:bg-slate-700/50 rounded-lg"><p className="text-xs font-mono text-amber-600 dark:text-amber-400 mb-1">{m.doc_id}</p><p className="text-xs text-stone-600 dark:text-stone-300 line-clamp-2">{m.summary}</p></div>))}</div></div>)}
          </div>
        )}

        {/* Timeline detail */}
        {activeTab === 'timeline' && timeline.length > 0 && (
          <div className="p-6">
            <h2 className="text-lg font-bold text-stone-800 dark:text-stone-100 mb-4">时间线总览</h2>
            <div className="relative pl-8">
              <div className="absolute left-3 top-0 bottom-0 w-0.5 bg-amber-300 dark:bg-amber-700"></div>
              {timeline.map((ev, i) => (
                <div key={i} className="relative mb-6">
                  <div className="absolute -left-8 top-1 w-6 h-6 rounded-full bg-amber-400 dark:bg-amber-600 border-4 border-white dark:border-slate-800 flex items-center justify-center"><span className="text-xs text-white font-bold">{i + 1}</span></div>
                  <div className="bg-stone-50 dark:bg-slate-700/50 rounded-lg p-3">
                    <h3 className="text-sm font-semibold text-stone-700 dark:text-stone-300">{ev.title}</h3>
                    {ev.time && <p className="text-xs font-mono text-amber-600 dark:text-amber-400 mt-1">{ev.time}</p>}
                    {ev.description && <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">{ev.description}</p>}
                    {ev.participants && ev.participants.length > 0 && (<div className="flex gap-1 mt-2 flex-wrap">{ev.participants.map((p, j) => (<span key={j} className="px-2 py-0.5 bg-amber-100 dark:bg-amber-900/30 rounded text-xs text-amber-700 dark:text-amber-400">{p}</span>))}</div>)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {activeTab === 'timeline' && timeline.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full"><ClockIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" /><p className="text-stone-500 dark:text-stone-400">时间线事件在左侧列表中查看</p></div>
        )}

        {/* Wiki page content */}
        {activeTab === 'pages' && wikiPageLoading && <div className="flex items-center justify-center h-full"><div className="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent"></div></div>}
        {activeTab === 'pages' && !wikiPageLoading && selectedPageContent && (
          <div className="p-4">
            <WikiPageRenderer content={selectedPageContent.content} frontmatter={selectedPageContent.frontmatter} onWikilinkClick={(target) => loadWikiPage(target)} onSourceClick={handleSourceClick} />
            {selectedDocPreview && (
              <div className="mt-4 border-t border-stone-200 dark:border-slate-700 pt-4">
                <div className="flex items-center justify-between mb-2"><h4 className="text-sm font-semibold text-stone-700 dark:text-stone-300">原始文档: {selectedDocPreview.doc_id}</h4><button onClick={() => setSelectedDocPreview(null)} className="text-stone-400 hover:text-stone-600 dark:hover:text-stone-200 text-lg">&times;</button></div>
                <pre className="text-xs text-stone-600 dark:text-stone-400 whitespace-pre-wrap max-h-96 overflow-y-auto bg-stone-50 dark:bg-slate-900 p-3 rounded-lg font-mono">{selectedDocPreview.content}</pre>
              </div>
            )}
          </div>
        )}
        {activeTab === 'pages' && !wikiPageLoading && !selectedPageContent && catalog && (
          <div className="flex flex-col items-center justify-center h-full"><DocumentIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" /><p className="text-stone-500 dark:text-stone-400">从左侧目录选择页面查看</p></div>
        )}

        {/* Analysis Tab */}
        {activeTab === 'analysis' && analysis && (
          <div className="p-4 space-y-6 overflow-y-auto">
            <div className="space-y-3">
              <h3 className="font-semibold text-stone-800 dark:text-stone-100 text-sm">矛盾与疑点</h3>
              {analysis.contradictions && analysis.contradictions.length > 0 && analysis.contradictions.map((c: any) => {
                const colors: Record<string, string> = { high: 'border-red-400 dark:border-red-700 bg-red-50 dark:bg-red-900/10', medium: 'border-amber-400 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/10', low: 'border-green-400 dark:border-green-700 bg-green-50 dark:bg-green-900/10' }
                return <div key={c.id} className={`p-3 rounded-lg border ${colors[c.severity] || colors.low}`}><div className="flex items-center gap-2 mb-1"><span className="text-xs font-bold uppercase">{c.severity}</span><span className="text-xs text-stone-400">{c.type}</span></div><p className="text-sm text-stone-700 dark:text-stone-300">{c.description}</p></div>
              })}
              {crossRefs.length > 0 && (<><h4 className="text-xs font-semibold text-stone-500 dark:text-stone-400 mt-4">跨文档矛盾</h4>{crossRefs.map((ref: any, i: number) => (<div key={i} className="p-3 rounded-lg border border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800"><div className="flex items-center gap-2 mb-1"><WarningIcon className="w-3.5 h-3.5 text-red-500" />{ref.source_doc && <span className="text-xs px-1.5 py-0.5 bg-stone-100 dark:bg-slate-700 rounded font-mono">{ref.source_doc}</span>}<span className="text-xs text-stone-400">↔</span>{ref.target_doc && <span className="text-xs px-1.5 py-0.5 bg-stone-100 dark:bg-slate-700 rounded font-mono">{ref.target_doc}</span>}</div><p className="text-sm text-stone-700 dark:text-stone-300">{ref.description}</p></div>))}</>)}
            </div>
            <div className="space-y-3">
              <h3 className="font-semibold text-stone-800 dark:text-stone-100 text-sm">知识缺口</h3>
              {analysis.knowledge_gaps && analysis.knowledge_gaps.length > 0 ? analysis.knowledge_gaps.map((gap: any) => {
                return <div key={gap.id} className="p-3 rounded-lg border border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800"><div className="flex items-center gap-2 mb-1"><GapIconRenderer type={gap.type} className="w-5 h-5" /><span className="text-sm font-medium text-stone-700 dark:text-stone-300">{gap.type?.replace(/_/g, ' ')}</span></div><p className="text-sm text-stone-600 dark:text-stone-400">{gap.description}</p>{gap.suggestion && <p className="text-xs text-stone-500 dark:text-stone-500 mt-1">建议: {gap.suggestion}</p>}</div>
              }) : <p className="text-sm text-stone-400">未发现明显知识缺口</p>}
            </div>
            {analysis.narrative_threads && analysis.narrative_threads.length > 0 && (
              <div className="space-y-3"><h3 className="font-semibold text-stone-800 dark:text-stone-100 text-sm">叙事线索</h3>{analysis.narrative_threads.map((thread: any) => (<div key={thread.id} className="p-3 rounded-lg border border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800"><h4 className="text-sm font-semibold text-stone-700 dark:text-stone-300"><WikiIcon className="w-4 h-4 inline" /> {thread.title}</h4><p className="text-xs text-stone-500 dark:text-stone-400 mt-1">{thread.description}</p></div>))}</div>
            )}
            {surprises && surprises.surprises && surprises.surprises.length > 0 && (
              <div className="space-y-3">
                <div className="flex items-center justify-between"><h3 className="font-semibold text-stone-800 dark:text-stone-100 text-sm"><InfoIcon className="w-4 h-4 inline" /> 惊喜发现</h3>{surprises.stats && <span className="text-xs text-stone-400 dark:text-stone-500">{surprises.stats.high_surprise} 高 · {surprises.stats.medium_surprise} 中 · {surprises.stats.low_surprise} 低</span>}</div>
                {surprises.surprises.map((s: any, i: number) => {
                  const colors: Record<string, string> = { cross_doc_contradiction: 'border-red-400 bg-red-50 dark:bg-red-900/10 dark:border-red-800', temporal_anomaly: 'border-amber-400 bg-amber-50 dark:bg-amber-900/10 dark:border-amber-800', isolated_entity: 'border-orange-400 bg-orange-50 dark:bg-orange-900/10 dark:border-orange-800', skewed_distribution: 'border-yellow-400 bg-yellow-50 dark:bg-yellow-900/10 dark:border-yellow-800' }
                  const scoreBadge = s.score >= 0.8 ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' : s.score >= 0.5 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                  return <div key={i} className={`p-3 rounded-lg border ${colors[s.type] || 'border-stone-200 bg-white dark:border-slate-700 dark:bg-slate-800'}`}><div className="flex items-center gap-2 mb-1"><span className={`px-1.5 py-0.5 rounded text-xs font-mono ${scoreBadge}`}>{Math.round(s.score * 100)}%</span><span className="text-xs text-stone-400 dark:text-stone-500">{s.type.replace(/_/g, ' ')}</span></div><p className="text-sm text-stone-700 dark:text-stone-300">{s.description}</p><p className="text-xs text-stone-500 dark:text-stone-400 mt-1">{s.reason}</p></div>
                })}
              </div>
            )}
          </div>
        )}
        {activeTab === 'analysis' && !analysis && (
          <div className="flex flex-col items-center justify-center h-full"><SearchIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" /><p className="text-stone-500 dark:text-stone-400">暂无分析数据，请确保已完成编译</p></div>
        )}
      </div>
    </div>
  )
}
