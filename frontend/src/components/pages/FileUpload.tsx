import { useState, useEffect, useRef } from 'react'
import { useAppStore } from '../../store/app'
import { FolderIcon, FileTextIcon, CheckCircleIcon, XIcon } from '../Icons'

const API_BASE = import.meta.env.VITE_API_BASE || ''

interface KB {
  id: string
  name: string
  compile_status: string
  document_count: number
}

interface DocInfo {
  id: string
  filename: string
  file_size: number
  file_type: string
  parse_status: string
  created_at: string
}

interface CompileProgress {
  type: string
  phase: string
  progress: number
  message: string
  stats?: Record<string, unknown>
}

interface UploadItem {
  file: File
  status: 'pending' | 'uploading' | 'success' | 'error'
  message?: string
}

export function FileUpload() {
  const { currentKbId, setCurrentKbId } = useAppStore()
  const [kbs, setKbs] = useState<KB[]>([])
  const [docs, setDocs] = useState<DocInfo[]>([])
  const [uploadQueue, setUploadQueue] = useState<UploadItem[]>([])
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState<string | null>(null)
  const [compiling, setCompiling] = useState(false)
  const [compileProgress, setCompileProgress] = useState<CompileProgress | null>(null)
  const compileWsRef = useRef<WebSocket | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const uploadIndexRef = useRef(0)

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
  }

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files.length > 0) startBatchUpload(e.dataTransfer.files)
  }

  const startBatchUpload = (files: FileList | File[]) => {
    const items: UploadItem[] = Array.from(files).map(f => ({ file: f, status: 'pending' as const }))
    if (items.length === 0) return
    setUploadQueue(items)
    setUploading(true)
    setUploadResult(null)
  }

  useEffect(() => {
    if (!uploading || uploadQueue.length === 0) return
    const idx = uploadIndexRef.current
    if (idx >= uploadQueue.length) {
      setUploading(false)
      uploadIndexRef.current = 0
      fetchDocs()
      const successCount = uploadQueue.filter(q => q.status === 'success').length
      const failCount = uploadQueue.filter(q => q.status === 'error').length
      setUploadResult(`上传完成: ${successCount} 成功${failCount > 0 ? `, ${failCount} 失败` : ''}`)
      return
    }
    const item = uploadQueue[idx]
    if (item.status !== 'pending') return

    const updated = [...uploadQueue]
    updated[idx] = { ...item, status: 'uploading' as const }
    setUploadQueue(updated)

    const formData = new FormData()
    formData.append('file', item.file)

    fetch(`${API_BASE}/api/documents/upload/${currentKbId}`, { method: 'POST', body: formData })
      .then(async (res) => {
        const updated2 = [...uploadQueue]
        if (res.ok) {
          const data = await res.json()
          updated2[idx] = { ...updated2[idx], status: 'success', message: `${data.filename} (${data.chunk_count} chunks)` }
        } else {
          const error = await res.json().catch(() => ({ detail: res.statusText }))
          updated2[idx] = { ...updated2[idx], status: 'error', message: error.detail || res.statusText }
        }
        setUploadQueue(updated2)
        uploadIndexRef.current = idx + 1
      })
      .catch((err) => {
        const updated2 = [...uploadQueue]
        updated2[idx] = { ...updated2[idx], status: 'error', message: (err as Error).message }
        setUploadQueue(updated2)
        uploadIndexRef.current = idx + 1
      })
  }, [uploading, uploadQueue, currentKbId])

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
    if (currentKbId) fetchDocs()
  }, [currentKbId])

  const fetchDocs = async () => {
    if (!currentKbId) return
    try {
      const res = await fetch(`${API_BASE}/api/documents/list/${currentKbId}`)
      if (res.ok) {
        const data = await res.json()
        setDocs(Array.isArray(data) ? data : [])
      }
    } catch (e) {
      console.error('Failed to fetch docs:', e)
    }
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) startBatchUpload(e.target.files)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleCompile = async () => {
    if (!currentKbId || docs.length === 0) return
    setCompiling(true)
    setCompileProgress({ type: 'status', phase: 'connecting', progress: 0, message: '连接中...' })

    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = location.host
    const ws = new WebSocket(`${proto}//${host}/api/compile/ws/${currentKbId}`)
    compileWsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setCompileProgress(data)

        if (data.type === 'done') {
          setCompiling(false)
          const stats = data.stats || {}
          const skipped = stats.documents_skipped || 0
          setUploadResult(`编译完成: ${stats.documents_processed || 0} 文档 (${skipped} 已有, ${stats.documents_processed - skipped} 新增), ${stats.chunks_generated || 0} chunks`)
          fetchDocs()
          ws.close()
        } else if (data.type === 'error') {
          setCompiling(false)
          setUploadResult(`编译失败: ${data.message}`)
          ws.close()
        }
      } catch (e) {
        console.error('Failed to parse compile WS message:', e)
      }
    }

    ws.onclose = () => {
      setCompiling(false)
    }

    ws.onerror = () => {
      setCompiling(false)
      setUploadResult('编译连接失败，请重试')
    }
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const typeLabels: Record<string, string> = {
    pdf: 'PDF',
    docx: 'Word',
    txt: '文本',
    md: 'Markdown',
    xlsx: 'Excel',
    xls: 'Excel',
    csv: 'CSV',
  }

  if (kbs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <FolderIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
        <p className="text-stone-600 dark:text-stone-300 font-medium">暂无知识库，请先创建</p>
      </div>
    )
  }

  if (!currentKbId) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <FolderIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
        <p className="text-stone-600 dark:text-stone-300 font-medium mb-4">选择知识库上传文档</p>
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
    <div className="max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-stone-800 dark:text-stone-100 mb-1">卷宗上传</h1>
      <p className="text-sm text-stone-500 dark:text-stone-400 mb-6">
        当前知识库: <span className="font-mono text-amber-600 dark:text-amber-400">{currentKbId}</span>
      </p>

      {/* Upload area */}
      <div
        className={`mb-6 p-8 bg-white dark:bg-slate-800 rounded-xl border-2 text-center transition-all duration-200 ${
          dragging
            ? 'border-amber-500 bg-amber-50 dark:bg-amber-900/10 scale-[1.02]'
            : 'border-dashed border-stone-300 dark:border-slate-600'
        }`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.txt,.md,.xlsx,.xls,.csv"
          multiple
          onChange={handleUpload}
          disabled={uploading}
          className="hidden"
          id="file-upload"
        />
        <label
          htmlFor="file-upload"
          className={`inline-flex flex-col items-center cursor-pointer ${uploading ? 'opacity-50 pointer-events-none' : ''}`}
        >
          <svg className="w-12 h-12 text-stone-400 dark:text-stone-500 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4M4 14v6a2 2 0 002 2h12a2 2 0 002-2v-6" />
          </svg>
          <span className="text-stone-600 dark:text-stone-300 font-medium">
            {dragging ? '松开文件上传' : '点击选择文件（支持批量）'}
          </span>
          <span className="text-xs text-stone-400 dark:text-stone-500 mt-1">
            {dragging ? '拖拽文件到此处' : '支持 PDF, Word, TXT, Markdown, Excel, CSV，可一次选择多个文件'}
          </span>
        </label>
        {uploadQueue.length > 0 && (
          <div className="mt-4 max-h-48 overflow-y-auto space-y-1.5 text-left">
            {uploadQueue.map((item, i) => (
              <div key={i} className="flex items-center gap-2 px-3 py-1.5 rounded bg-stone-50 dark:bg-slate-700/50 text-xs">
                {item.status === 'pending' && <div className="w-3 h-3 rounded-full border border-stone-300 dark:border-slate-500 flex-shrink-0" />}
                {item.status === 'uploading' && <div className="w-3 h-3 rounded-full border-2 border-amber-500 border-t-transparent animate-spin flex-shrink-0" />}
                {item.status === 'success' && <CheckCircleIcon className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />}
                {item.status === 'error' && <XIcon className="w-3.5 h-3.5 text-red-500 flex-shrink-0" />}
                <span className="text-stone-700 dark:text-stone-300 truncate flex-1">{item.file.name}</span>
                {item.message && <span className={`flex-shrink-0 ${item.status === 'error' ? 'text-red-500' : 'text-stone-400 dark:text-stone-500'}`}>{item.message}</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Compile button + progress */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <div>
            <h3 className="font-semibold text-stone-800 dark:text-stone-100">文档列表</h3>
            <p className="text-xs text-stone-400 dark:text-stone-500">{docs.length} 篇文档</p>
          </div>
          <button
            onClick={handleCompile}
            disabled={compiling || docs.length === 0}
            className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
          >
            {compiling ? '编译中...' : '编译 L0/L1/L2'}
          </button>
        </div>

        {/* Progress bar */}
        {compiling && compileProgress && (
          <div className="mt-3 p-3 bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700">
            <div className="flex items-center justify-between text-xs mb-2">
              <span className="text-stone-600 dark:text-stone-300">{compileProgress.message}</span>
              <span className="text-amber-600 dark:text-amber-400 font-mono">{compileProgress.progress}%</span>
            </div>
            <div className="w-full bg-stone-200 dark:bg-slate-700 rounded-full h-2 overflow-hidden">
              <div
                className="h-full bg-amber-500 rounded-full transition-all duration-300 ease-out"
                style={{ width: `${compileProgress.progress}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Result message */}
      {uploadResult && (
        <div className={`mb-4 p-3 rounded-lg text-sm ${
          uploadResult.includes('成功') || uploadResult.includes('完成')
            ? 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400 border border-green-200 dark:border-green-800'
            : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400 border border-red-200 dark:border-red-800'
        }`}>
          {uploadResult}
        </div>
      )}

      {/* Document list */}
      <div className="space-y-2">
        {docs.map((doc) => (
          <div
            key={doc.id}
            className="flex items-center justify-between p-3 bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700"
          >
            <div className="flex items-center gap-3">
              <FileTextIcon className="w-5 h-5" />
              <div>
                <p className="text-sm font-medium text-stone-800 dark:text-stone-100">{doc.filename}</p>
                <p className="text-xs text-stone-400 dark:text-stone-500">
                  {formatSize(doc.file_size)} · {typeLabels[doc.file_type] || doc.file_type} · {new Date(doc.created_at).toLocaleDateString('zh-CN')}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                doc.parse_status === 'completed'
                  ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                  : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
              }`}>
                {doc.parse_status === 'completed' ? '已解析' : doc.parse_status}
              </span>
              <button
                onClick={async () => {
                  if (!confirm('确定删除此文档？')) return
                  try {
                    const res = await fetch(`${API_BASE}/api/documents/${doc.id}`, { method: 'DELETE' })
                    if (res.ok || res.status === 204) { await fetchDocs(); setUploadResult('文档已删除') }
                  } catch (e) { console.error('Failed to delete doc:', e) }
                }}
                className="p-1.5 text-stone-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                title="删除"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
