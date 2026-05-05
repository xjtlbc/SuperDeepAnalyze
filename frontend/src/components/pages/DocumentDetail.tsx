import React, { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { PersonIcon, FolderIcon, ClockIcon, DatabaseIcon, InfoIcon, FileTextIcon, DocumentIcon, GraphIcon } from '../Icons'
import { ExcelViewer } from '../ExcelViewer'

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
  entities_mentioned?: Array<string | { name: string; type?: string }>
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
  pending: { label: '待编译', color: 'badge badge--pending' },
  processing: { label: '编译中', color: 'badge badge--processing' },
  completed: { label: '已完成', color: 'badge badge--completed' },
  failed: { label: '失败', color: 'badge badge--failed' },
  partial: { label: '部分完成', color: 'badge badge--partial' },
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

/** Extract a meaningful heading from summary text. */
function extractHeading(text: string): string {
  if (!text) return '(无标题)'
  // Markdown heading: # Title or ## Title
  const mdMatch = text.match(/^#{1,3}\s+(.+)/)
  if (mdMatch) return mdMatch[1].trim()
  // Chinese chapter pattern
  const zhMatch = text.match(/^(第[一二三四五六七八九十百千万\d]+\s*[章节回卷集篇幕][^\n.]*)/)
  if (zhMatch) return zhMatch[1].trim()
  // First sentence (up to 。or . or \n, max 60 chars)
  const firstSentence = text.match(/^[^。\n.]{2,60}?[。\n.]?/)
  if (firstSentence) {
    const s = firstSentence[0].replace(/[。\n.]$/, '').trim()
    return s.length > 50 ? s.slice(0, 50) + '...' : s
  }
  return text.slice(0, 60) + (text.length > 60 ? '...' : '')
}

export function DocumentDetail() {
  const { kbId, docId } = useParams<{ kbId: string; docId: string }>()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<LevelTab>('l1')
  const [detail, setDetail] = useState<DocumentDetailData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchDetail = useCallback(() => {
    if (!kbId || !docId) return
    setLoading(true)
    setError(null)
    fetch(`${API_BASE}/api/documents/${docId}/detail?kb_id=${kbId}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => { setDetail(data); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [kbId, docId])

  useEffect(() => { fetchDetail() }, [fetchDetail])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full document-detail__spinner"></div>
      </div>
    )
  }

  if (error || !detail) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <p className="document-detail__error-text mb-2">{error || '未找到文档详情'}</p>
        <button onClick={fetchDetail} className="document-detail__btn-retry mb-2">重试</button>
        <button onClick={() => navigate(-1)} className="text-sm document-detail__back-link">返回</button>
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
      <div className="document-detail__header">
        <Link
          to={`/knowledge/${kbId}`}
          className="document-detail__back-btn"
          title="返回知识库"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <div className="min-w-0">
          <h1 className="document-detail__title truncate">{filename}</h1>
          <p className="document-detail__meta-text">
            {formatSize(fileSize)} · {fileType.toUpperCase()} · {createdAt ? new Date(createdAt).toLocaleDateString('zh-CN') : '未知日期'}
          </p>
        </div>
        {detail.kb_compile_status && (
          <span className={`document-detail__status-badge ${statusMap[detail.kb_compile_status]?.color || 'badge badge--muted'}`}>
            {statusMap[detail.kb_compile_status]?.label || detail.kb_compile_status}
          </span>
        )}
      </div>

      {/* Level Tabs */}
      <div className="document-detail__tab-bar">
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
        {activeTab === 'l2' && <L2Tab kbId={kbId!} docId={docId!} totalChunks={detail.l2_summary.chunk_count} fileType={fileType} />}
        {activeTab === 'l0' && <L0Tab kbId={kbId!} docId={docId!} />}
      </div>
    </div>
  )
}

function TabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`document-detail__tab-btn ${active ? 'document-detail__tab-btn--active' : ''}`}
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
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const limit = 50

  const fetchSummaries = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/api/documents/${docId}/l1-summaries?kb_id=${kbId}&offset=${offset}&limit=${limit}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setSummaries(data.summaries || [])
      setTotal(data.total || 0)
    } catch (e: any) {
      setError(e.message)
    }
    setLoading(false)
  }, [kbId, docId, offset])

  useEffect(() => { fetchSummaries() }, [fetchSummaries])

  const toggleExpand = (idx: number) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  if (loading && summaries.length === 0) {
    return <div className="flex items-center justify-center h-full"><div className="animate-spin rounded-full document-detail__spinner"></div></div>
  }

  if (error && summaries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <p className="document-detail__error-text mb-2">加载L1摘要失败: {error}</p>
        <button onClick={fetchSummaries} className="document-detail__btn-retry">重试</button>
      </div>
    )
  }

  if (summaries.length === 0) {
    return <div className="flex flex-col items-center justify-center h-full"><FileTextIcon className="document-detail__empty-icon mx-auto mb-3" /><p className="text-secondary">暂无 L1 摘要</p></div>
  }

  return (
    <div className="document-detail__l1-list">
      {summaries.map((entry, i) => {
        const globalIdx = offset + i
        const summaryText = (entry.summary as string) || (entry.content as string) || ''
        const entities = entry.entities_mentioned || []
        const chunkIds = entry.chunk_ids || []
        const isExpanded = expanded.has(globalIdx)
        const heading = extractHeading(summaryText)

        return (
          <div
            key={globalIdx}
            className="document-detail__l1-card"
          >
            <button
              onClick={() => toggleExpand(globalIdx)}
              className="document-detail__l1-card-header"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="document-detail__l1-index">#{globalIdx + 1}</span>
                <span className="text-sm font-medium text-secondary truncate">{heading}</span>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {entities.length > 0 && (
                  <div className="flex items-center gap-1">
                    {entities.slice(0, 3).map((ent, ei) => {
                      const label = typeof ent === 'string' ? ent : typeof (ent as any)?.name === 'string' ? (ent as any).name : JSON.stringify(ent)
                      return (
                      <span key={ei} className="document-detail__entity-tag truncate">{label}</span>
                      )
                    })}
                    {entities.length > 3 && <span className="text-xs text-muted">+{entities.length - 3}</span>}
                  </div>
                )}
                <svg className={`document-detail__chevron-icon ${isExpanded ? 'document-detail__chevron-icon--expanded' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </button>
            {isExpanded && (
              <div className="document-detail__l1-card-body">
                <div className="document-detail__prose mt-3">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{summaryText}</ReactMarkdown>
                </div>
                {chunkIds.length > 0 && (
                  <p className="text-xs text-muted mt-2">覆盖 {chunkIds.length} 个 L2 片段</p>
                )}
              </div>
            )}
          </div>
        )
      })}

      {/* Pagination */}
      {offset > 0 && (
        <button onClick={() => setOffset(Math.max(0, offset - limit))} className="document-detail__page-btn">← 上一页</button>
      )}
      {offset + limit < total && (
        <button onClick={() => setOffset(offset + limit)} className="document-detail__page-btn">下一页 →</button>
      )}
    </div>
  )
}

// ─── L2 Tab ───

const MAX_CHUNKS_PER_CHAPTER = 200

function L2Tab({ kbId, docId, totalChunks, fileType }: { kbId: string; docId: string; totalChunks: number; fileType: string }) {
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [selectedChapter, setSelectedChapter] = useState<Chapter | null>(null)
  const [content, setContent] = useState('')
  const [contentLoading, setContentLoading] = useState(false)
  const [contentError, setContentError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tocError, setTocError] = useState<string | null>(null)
  const [continuousMode, setContinuousMode] = useState(false)
  const [allContent, setAllContent] = useState<Map<string, string>>(new Map())
  const [loadingAll, setLoadingAll] = useState(false)
  const [excelMarkdown, setExcelMarkdown] = useState<string | null>(null)
  const [excelLoading, setExcelLoading] = useState(false)
  const [excelError, setExcelError] = useState<string | null>(null)
  const [showRawMarkdown, setShowRawMarkdown] = useState(false)

  const isExcel = fileType === 'xlsx'

  const fetchChapters = useCallback(async () => {
    setLoading(true)
    setTocError(null)
    try {
      const res = await fetch(`${API_BASE}/api/documents/${docId}/l2-toc?kb_id=${kbId}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setChapters(data.chapters || [])
    } catch (e: any) {
      setTocError(e.message)
    }
    setLoading(false)
  }, [kbId, docId])

  useEffect(() => { fetchChapters() }, [fetchChapters])

  const loadChapter = useCallback(async (chapter: Chapter) => {
    setSelectedChapter(chapter)
    setContentLoading(true)
    setContentError(null)
    setContent('')

    const startIdx = chapter.chunk_index
    const endIdx = chapter.chunk_end !== undefined ? chapter.chunk_end : chapter.chunk_index

    const indices: number[] = []
    for (let i = startIdx; i <= endIdx && i < totalChunks && indices.length < MAX_CHUNKS_PER_CHAPTER; i++) {
      indices.push(i)
    }

    try {
      const indicesStr = indices.join(',')
      const res = await fetch(`${API_BASE}/api/documents/${docId}/l2-batch?kb_id=${kbId}&indices=${indicesStr}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: L2BatchResult = await res.json()
      setContent(data.merged_content || '')
    } catch (e: any) {
      setContentError(e.message)
    }
    setContentLoading(false)
  }, [kbId, docId, totalChunks])

  const loadAllChapters = useCallback(async () => {
    if (chapters.length === 0) return
    setLoadingAll(true)
    const newContent = new Map(allContent)
    for (const chapter of chapters) {
      if (chapter.is_volume) continue
      const key = `${chapter.chunk_index}-${chapter.chunk_end}`
      if (newContent.has(key)) continue
      const startIdx = chapter.chunk_index
      const endIdx = chapter.chunk_end !== undefined ? chapter.chunk_end : chapter.chunk_index
      const indices: number[] = []
      for (let i = startIdx; i <= endIdx && i < totalChunks && indices.length < MAX_CHUNKS_PER_CHAPTER; i++) {
        indices.push(i)
      }
      try {
        const res = await fetch(`${API_BASE}/api/documents/${docId}/l2-batch?kb_id=${kbId}&indices=${indices.join(',')}`)
        if (res.ok) {
          const data: L2BatchResult = await res.json()
          newContent.set(key, data.merged_content || '')
        }
      } catch { /* skip failed chapters */ }
    }
    setAllContent(newContent)
    setLoadingAll(false)
    setContinuousMode(true)
  }, [chapters, allContent, kbId, docId, totalChunks])

  // Fetch Excel markdown on demand
  useEffect(() => {
    if (!isExcel) return
    setExcelLoading(true)
    setExcelError(null)
    fetch(`${API_BASE}/api/documents/${kbId}/${docId}/parsed`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => { setExcelMarkdown(data.content); setExcelLoading(false) })
      .catch(e => { setExcelError(e.message); setExcelLoading(false) })
  }, [kbId, docId, isExcel])

  if (loading) {
    return <div className="flex items-center justify-center h-full"><div className="animate-spin rounded-full document-detail__spinner"></div></div>
  }

  if (tocError && chapters.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <p className="document-detail__error-text mb-2">加载章节列表失败: {tocError}</p>
        <button onClick={fetchChapters} className="document-detail__btn-retry">重试</button>
      </div>
    )
  }

  if (totalChunks === 0) {
    return <div className="flex flex-col items-center justify-center h-full"><DocumentIcon className="document-detail__empty-icon mx-auto mb-3" /><p className="text-secondary">暂无 L2 内容</p></div>
  }

  // Excel mode — use ExcelViewer
  if (isExcel) {
    if (excelLoading) {
      return <div className="flex items-center justify-center h-full"><div className="animate-spin rounded-full document-detail__spinner"></div></div>
    }
    if (excelError) {
      return (
        <div className="flex flex-col items-center justify-center h-full">
          <p className="document-detail__error-text mb-2">加载Excel内容失败: {excelError}</p>
          <button onClick={() => window.location.reload()} className="document-detail__btn-retry">重试</button>
        </div>
      )
    }
    return (
      <div className="h-full flex flex-col">
        <div className="document-detail__excel-toolbar">
          <button
            onClick={() => setShowRawMarkdown(!showRawMarkdown)}
            className="document-detail__toggle-btn"
          >
            {showRawMarkdown ? '表格视图' : '原始Markdown'}
          </button>
        </div>
        <div className="flex-1 min-h-0 overflow-hidden">
          {showRawMarkdown && excelMarkdown ? (
            <div className="document-detail__raw-markdown-container h-full overflow-y-auto p-4">
              <pre className="document-detail__raw-markdown-pre">{excelMarkdown}</pre>
            </div>
          ) : excelMarkdown ? (
            <ExcelViewer markdown={excelMarkdown} />
          ) : (
            <div className="flex items-center justify-center h-full"><p className="text-muted">无内容</p></div>
          )}
        </div>
      </div>
    )
  }

  // Continuous reading mode
  if (continuousMode) {
    return (
      <div className="h-full flex flex-col">
        <div className="document-detail__continuous-toolbar">
          <button
            onClick={() => setContinuousMode(false)}
            className="document-detail__toggle-btn"
          >
            章节模式
          </button>
          {/* Sticky chapter navigation */}
          <select
            className="document-detail__chapter-select"
            onChange={(e) => {
              const idx = parseInt(e.target.value)
              const ch = chapters[idx]
              if (ch) {
                const el = document.getElementById(`chapter-${ch.chunk_index}`)
                el?.scrollIntoView({ behavior: 'smooth' })
              }
            }}
          >
            <option value="">跳转到章节...</option>
            {chapters.filter(c => !c.is_volume).map((ch, i) => (
              <option key={i} value={i}>{ch.name}</option>
            ))}
          </select>
        </div>
        <div className="flex-1 overflow-y-auto document-detail__l1-list">
          {chapters.filter(c => !c.is_volume).map((chapter, ci) => {
            const key = `${chapter.chunk_index}-${chapter.chunk_end}`
            const chapterContent = allContent.get(key)
            return (
              <div key={ci} id={`chapter-${chapter.chunk_index}`} className="document-detail__continuous-chapter">
                <h2 className="document-detail__chapter-title">
                  {chapter.name}
                </h2>
                {chapterContent ? (
                  <div className="document-detail__prose">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{chapterContent}</ReactMarkdown>
                  </div>
                ) : (
                  <p className="document-detail__loading-text text-sm">加载中...</p>
                )}
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  // Default two-pane mode
  return (
    <div className="document-detail__two-pane">
      {/* Left: Chapter list */}
      <div className="document-detail__toc-panel">
        <div className="document-detail__toc-header">
          <p className="text-xs font-medium text-muted">
            共 {totalChunks} 片 · {chapters.length} 个章节
          </p>
          <button
            onClick={loadAllChapters}
            disabled={loadingAll}
            className="document-detail__load-all-btn"
          >
            {loadingAll ? '加载中...' : '加载全部'}
          </button>
        </div>
        <div className="document-detail__toc-list">
          {chapters.map((ch, i) =>
            ch.is_volume ? (
              <div
                key={i}
                className="document-detail__volume-label"
              >
                {ch.name}
              </div>
            ) : (
              <button
                key={i}
                onClick={() => loadChapter(ch)}
                className={`document-detail__chapter-btn ${selectedChapter?.chunk_index === ch.chunk_index ? 'document-detail__chapter-btn--active' : ''}`}
              >
                {ch.name}
              </button>
            )
          )}
        </div>
      </div>

      {/* Right: Content */}
      <div className="document-detail__content-panel">
        {contentLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="animate-spin rounded-full document-detail__spinner"></div>
          </div>
        ) : contentError ? (
          <div className="flex flex-col items-center justify-center h-full">
            <p className="document-detail__error-text mb-2">加载章节失败: {contentError}</p>
            {selectedChapter && (
              <button onClick={() => loadChapter(selectedChapter)} className="document-detail__btn-retry">重试</button>
            )}
          </div>
        ) : selectedChapter ? (
          <div className="p-6">
            <div className="document-detail__content-title-row">
              <button
                onClick={() => { setSelectedChapter(null); setContent('') }}
                className="document-detail__content-back-btn"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <h2 className="document-detail__content-heading">{selectedChapter.name}</h2>
            </div>
            {content ? (
              <div className="document-detail__prose">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {content}
                </ReactMarkdown>
              </div>
            ) : (
              <p className="document-detail__no-content text-center py-8">该章节无内容</p>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full">
            <DocumentIcon className="document-detail__empty-icon mx-auto mb-3" />
            <p className="text-secondary">点击左侧章节加载内容</p>
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
  const [error, setError] = useState<string | null>(null)

  const fetchEntities = useCallback(() => {
    setLoading(true)
    setError(null)
    fetch(`${API_BASE}/api/documents/${docId}/l0-entities?kb_id=${kbId}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => { setEntities(data.entities || []); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [kbId, docId])

  useEffect(() => { fetchEntities() }, [fetchEntities])

  if (loading) {
    return <div className="flex items-center justify-center h-full"><div className="animate-spin rounded-full document-detail__spinner"></div></div>
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <p className="document-detail__error-text mb-2">加载实体失败: {error}</p>
        <button onClick={fetchEntities} className="document-detail__btn-retry">重试</button>
      </div>
    )
  }

  if (entities.length === 0) {
    return <div className="flex flex-col items-center justify-center h-full"><GraphIcon className="document-detail__empty-icon mx-auto mb-3" /><p className="text-secondary">暂无关联实体</p></div>
  }

  return (
    <div className="document-detail__l0-container">
      <div className="document-detail__l0-grid">
        {entities.map((entity, i) => (
          <div
            key={i}
            className="document-detail__entity-card"
          >
            <div className="flex items-center gap-2 mb-2">
              {(() => { const Icon = getTypeIcon(entity.type); return Icon ? <Icon className="w-5 h-5" /> : <InfoIcon className="w-5 h-5" />; })()}
              <h3 className="text-sm font-semibold text-secondary">{String(entity.name)}</h3>
              <span className="document-detail__entity-type-badge">
                {TYPE_LABELS[String(entity.type)] || String(entity.type)}
              </span>
            </div>
            {entity.attributes && Object.keys(entity.attributes).length > 0 && (
              <div className="document-detail__entity-attrs mt-2">
                {Object.entries(entity.attributes).map(([k, v]) => (
                  <div key={k} className="document-detail__entity-attr-row">
                    <span className="text-muted">{k}</span>
                    <span className="document-detail__entity-attr-value truncate ml-2">{typeof v === 'string' || typeof v === 'number' ? String(v) : JSON.stringify(v)}</span>
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
