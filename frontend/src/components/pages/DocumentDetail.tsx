import React, { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { PersonIcon, FolderIcon, ClockIcon, DatabaseIcon, InfoIcon, FileTextIcon, DocumentIcon, GraphIcon } from '../Icons'

const API_BASE = import.meta.env.VITE_API_BASE || ''

type LevelTab = 'l1' | 'l2' | 'l0'

interface DocumentDetailData {
  document: Record<string, unknown>
  kb_compile_status: string
  l1_summary: { batch_count: number; total_chunks_covered: number }
  l2_summary: { chunk_count: number }
}

interface L1SummaryEntry {
  chunk_ids?: string[]
  summary?: string
  content?: string
  entities_mentioned?: string[]
  [key: string]: unknown
}

interface Chapter {
  name: string
  chunk_index: number
  chunk_end?: number
  is_volume: boolean
}

interface L2BatchResult {
  chunks: Array<{ index: number; content: string }>
  merged_content: string
  total: number
}

interface L0Entity {
  name: string
  type: string
  attributes: Record<string, unknown>
}

const statusMap: Record<string, { label: string; color: string }> = {
  pending: { label: '待编译', color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
  processing: { label: '编译中', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' },
  completed: { label: '已完成', color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' },
  failed: { label: '失败', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
  partial: { label: '部分完成', color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' },
}

function PinIcon({ className }: { className?: string }) {
  return (
    <svg className={className || 'w-5 h-5'} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  )
}

function getTypeIcon(type: string): React.ComponentType<{className?: string}> | null {
  const icons: Record<string, React.ComponentType<{className?: string}>> = {
    person: PersonIcon,
    location: PinIcon,
    organization: FolderIcon,
    event: ClockIcon,
    object: DatabaseIcon,
    concept: InfoIcon,
  }
  return icons[type] || null
}

const TYPE_LABELS: Record<string, string> = { person: '人物', location: '地点', organization: '组织', event: '事件', object: '物品', concept: '概念' }

export function DocumentDetail() {
  const { kbId, docId } = useParams<{ kbId: string; docId: string }>()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<LevelTab>('l1')
  const [detail, setDetail] = useState<DocumentDetailData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!kbId || !docId) return
    fetch(`${API_BASE}/api/documents/${docId}/detail?kb_id=${kbId}`)
      .then(r => r.json())
      .then(data => { setDetail(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [kbId, docId])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent"></div>
      </div>
    )
  }

  if (!detail) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <p className="text-stone-500 dark:text-stone-400 mb-4">未找到文档详情</p>
        <button onClick={() => navigate(-1)} className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm">返回</button>
      </div>
    )
  }

  const doc = detail.document
  const filename = (doc.filename as string) || '未知文件'
  const fileSize = (doc.file_size as number) || 0
  const fileType = (doc.file_type as string) || ''
  const createdAt = (doc.created_at as string) || ''

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <Link
          to={`/knowledge/${kbId}`}
          className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-slate-700 text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 transition-colors"
          title="返回知识库"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <div className="min-w-0">
          <h1 className="text-xl font-bold text-stone-800 dark:text-stone-100 truncate">{filename}</h1>
          <p className="text-xs text-stone-400 dark:text-stone-500 mt-0.5">
            {formatSize(fileSize)} · {fileType.toUpperCase()} · {createdAt ? new Date(createdAt).toLocaleDateString('zh-CN') : '未知日期'}
          </p>
        </div>
        {detail.kb_compile_status && (
          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusMap[detail.kb_compile_status]?.color || 'bg-gray-100 text-gray-600'}`}>
            {statusMap[detail.kb_compile_status]?.label || detail.kb_compile_status}
          </span>
        )}
      </div>

      {/* Level Tabs */}
      <div className="flex gap-1 mb-4 border-b border-stone-200 dark:border-slate-700">
        <TabButton
          label={`L1 摘要 (${detail.l1_summary.batch_count} 条)`}
          active={activeTab === 'l1'}
          onClick={() => setActiveTab('l1')}
        />
        <TabButton
          label={`L2 全文 (${detail.l2_summary.chunk_count} chunks)`}
          active={activeTab === 'l2'}
          onClick={() => setActiveTab('l2')}
        />
        <TabButton
          label={`L0 关联实体`}
          active={activeTab === 'l0'}
          onClick={() => setActiveTab('l0')}
        />
      </div>

      {/* Tab Content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {activeTab === 'l1' && <L1Tab kbId={kbId!} docId={docId!} />}
        {activeTab === 'l2' && <L2Tab kbId={kbId!} docId={docId!} totalChunks={detail.l2_summary.chunk_count} />}
        {activeTab === 'l0' && <L0Tab kbId={kbId!} docId={docId!} />}
      </div>
    </div>
  )
}

function TabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 ${
        active
          ? 'border-amber-500 text-amber-700 dark:text-amber-400'
          : 'border-transparent text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-300'
      }`}
    >
      {label}
    </button>
  )
}

// ─── L1 Tab ───

function L1Tab({ kbId, docId }: { kbId: string; docId: string }) {
  const [summaries, setSummaries] = useState<L1SummaryEntry[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const limit = 50

  useEffect(() => {
    fetchSummaries()
  }, [kbId, docId, offset])

  const fetchSummaries = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/documents/${docId}/l1-summaries?kb_id=${kbId}&offset=${offset}&limit=${limit}`)
      if (res.ok) {
        const data = await res.json()
        setSummaries(data.summaries || [])
        setTotal(data.total || 0)
      }
    } catch (e) {
      console.error('Failed to fetch L1 summaries:', e)
    }
    setLoading(false)
  }

  const toggleExpand = (idx: number) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  if (loading && summaries.length === 0) {
    return <div className="flex items-center justify-center h-full"><div className="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent"></div></div>
  }

  if (summaries.length === 0) {
    return <div className="flex flex-col items-center justify-center h-full"><FileTextIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" /><p className="text-stone-500 dark:text-stone-400">暂无 L1 摘要</p></div>
  }

  return (
    <div className="h-full overflow-y-auto space-y-3">
      {summaries.map((entry, i) => {
        const globalIdx = offset + i
        const summaryText = (entry.summary as string) || (entry.content as string) || ''
        const entities = entry.entities_mentioned || []
        const chunkIds = entry.chunk_ids || []
        const isExpanded = expanded.has(globalIdx)

        return (
          <div
            key={globalIdx}
            className="bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700 overflow-hidden"
          >
            <button
              onClick={() => toggleExpand(globalIdx)}
              className="w-full flex items-center justify-between p-4 text-left hover:bg-stone-50 dark:hover:bg-slate-700/50 transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="text-xs font-mono text-stone-400 dark:text-stone-500 w-10 flex-shrink-0">#{globalIdx + 1}</span>
                <span className="text-sm font-medium text-stone-700 dark:text-stone-300 truncate">{summaryText.slice(0, 100)}{summaryText.length > 100 ? '...' : ''}</span>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {entities.length > 0 && (
                  <span className="text-xs text-stone-400 dark:text-stone-500">{entities.length} 实体</span>
                )}
                <svg className={`w-4 h-4 text-stone-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </button>
            {isExpanded && (
              <div className="px-4 pb-4 border-t border-stone-100 dark:border-slate-700">
                <div className="mt-3 prose prose-sm dark:prose-invert max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{summaryText}</ReactMarkdown>
                </div>
                {chunkIds.length > 0 && (
                  <p className="text-xs text-stone-400 dark:text-stone-500 mt-2">覆盖 {chunkIds.length} 个 L2 片段</p>
                )}
              </div>
            )}
          </div>
        )
      })}

      {/* Pagination */}
      {offset > 0 && (
        <button onClick={() => setOffset(Math.max(0, offset - limit))} className="w-full py-2 text-sm text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/20 rounded-lg transition-colors">← 上一页</button>
      )}
      {offset + limit < total && (
        <button onClick={() => setOffset(offset + limit)} className="w-full py-2 text-sm text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/20 rounded-lg transition-colors">下一页 →</button>
      )}
    </div>
  )
}

// ─── L2 Tab ───

const MAX_CHUNKS_PER_CHAPTER = 200

function L2Tab({ kbId, docId, totalChunks }: { kbId: string; docId: string; totalChunks: number }) {
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [selectedChapter, setSelectedChapter] = useState<Chapter | null>(null)
  const [content, setContent] = useState('')
  const [contentLoading, setContentLoading] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchChapters()
  }, [kbId, docId])

  const fetchChapters = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/documents/${docId}/l2-toc?kb_id=${kbId}`)
      if (res.ok) {
        const data = await res.json()
        setChapters(data.chapters || [])
      }
    } catch (e) {
      console.error('Failed to fetch L2 TOC:', e)
    }
    setLoading(false)
  }

  const loadChapter = async (chapter: Chapter) => {
    setSelectedChapter(chapter)
    setContentLoading(true)
    setContent('')

    const startIdx = chapter.chunk_index
    const endIdx = chapter.chunk_end !== undefined ? chapter.chunk_end : chapter.chunk_index

    // Build indices list (cap at 200 chunks per chapter like DeepAnalyze)
    const indices: number[] = []
    for (let i = startIdx; i <= endIdx && i < totalChunks && indices.length < MAX_CHUNKS_PER_CHAPTER; i++) {
      indices.push(i)
    }

    try {
      const indicesStr = indices.join(',')
      const res = await fetch(`${API_BASE}/api/documents/${docId}/l2-batch?kb_id=${kbId}&indices=${indicesStr}`)
      if (res.ok) {
        const data: L2BatchResult = await res.json()
        setContent(data.merged_content || '')
      }
    } catch (e) {
      console.error('Failed to load chapter:', e)
    }
    setContentLoading(false)
  }

  if (loading) {
    return <div className="flex items-center justify-center h-full"><div className="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent"></div></div>
  }

  if (totalChunks === 0) {
    return <div className="flex flex-col items-center justify-center h-full"><DocumentIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" /><p className="text-stone-500 dark:text-stone-400">暂无 L2 内容</p></div>
  }

  return (
    <div className="h-full flex gap-4 min-h-0">
      {/* Left: Chapter list */}
      <div className="w-72 bg-white dark:bg-slate-800 rounded-xl border border-stone-200 dark:border-slate-700 flex flex-col overflow-hidden">
        <div className="px-3 py-2 border-b border-stone-200 dark:border-slate-700">
          <p className="text-xs font-medium text-stone-500 dark:text-stone-400">
            共 {totalChunks} 片 · {chapters.length} 个章节
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
          {chapters.map((ch, i) =>
            ch.is_volume ? (
              // Volume header — unclickable separator
              <div
                key={i}
                className="px-3 py-2 mt-1 mb-0.5 rounded text-xs font-semibold text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800"
              >
                {ch.name}
              </div>
            ) : (
              // Chapter entry — clickable
              <button
                key={i}
                onClick={() => loadChapter(ch)}
                className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-colors ${
                  selectedChapter?.chunk_index === ch.chunk_index
                    ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 font-medium'
                    : 'text-stone-600 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-slate-700'
                } pl-5`}
              >
                {ch.name}
              </button>
            )
          )}
        </div>
      </div>

      {/* Right: Content */}
      <div className="flex-1 bg-white dark:bg-slate-800 rounded-xl border border-stone-200 dark:border-slate-700 overflow-y-auto">
        {contentLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent"></div>
          </div>
        ) : selectedChapter ? (
          <div className="p-6">
            {/* Chapter header */}
            <div className="flex items-center gap-2 mb-4 pb-3 border-b border-stone-200 dark:border-slate-700">
              <button
                onClick={() => { setSelectedChapter(null); setContent('') }}
                className="p-1 rounded hover:bg-stone-100 dark:hover:bg-slate-700 text-stone-400 hover:text-stone-600 transition-colors"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <h2 className="text-lg font-bold text-stone-800 dark:text-stone-100">{selectedChapter.name}</h2>
            </div>
            {/* Markdown content */}
            {content ? (
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {content}
                </ReactMarkdown>
              </div>
            ) : (
              <p className="text-stone-400 dark:text-stone-500 text-center py-8">该章节无内容</p>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full">
            <DocumentIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
            <p className="text-stone-500 dark:text-stone-400">点击左侧章节加载内容</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── L0 Tab ───

function L0Tab({ kbId, docId }: { kbId: string; docId: string }) {
  const [entities, setEntities] = useState<L0Entity[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API_BASE}/api/documents/${docId}/l0-entities?kb_id=${kbId}`)
      .then(r => r.json())
      .then(data => { setEntities(data.entities || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [kbId, docId])

  if (loading) {
    return <div className="flex items-center justify-center h-full"><div className="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent"></div></div>
  }

  if (entities.length === 0) {
    return <div className="flex flex-col items-center justify-center h-full"><GraphIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" /><p className="text-stone-500 dark:text-stone-400">暂无关联实体</p></div>
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {entities.map((entity, i) => (
          <div
            key={i}
            className="bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700 p-4"
          >
            <div className="flex items-center gap-2 mb-2">
              {(() => { const Icon = getTypeIcon(entity.type); return Icon ? <Icon className="w-5 h-5" /> : <InfoIcon className="w-5 h-5" />; })()}
              <h3 className="text-sm font-semibold text-stone-700 dark:text-stone-300">{entity.name}</h3>
              <span className="text-xs px-1.5 py-0.5 bg-stone-100 dark:bg-slate-700 rounded text-stone-500 dark:text-stone-400">
                {TYPE_LABELS[entity.type] || entity.type}
              </span>
            </div>
            {entity.attributes && Object.keys(entity.attributes).length > 0 && (
              <div className="space-y-1 mt-2">
                {Object.entries(entity.attributes).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-xs">
                    <span className="text-stone-400 dark:text-stone-500">{k}</span>
                    <span className="text-stone-600 dark:text-stone-300 truncate ml-2 max-w-32">{String(v)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
