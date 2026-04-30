import { useState, useEffect, useRef, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { API_BASE, compileStatusLabels, parseStatusLabels, formatSize, typeLabels } from './shared'
import { ConfirmDialog } from '../../ConfirmDialog'
import { FileTextIcon, CheckCircleIcon, XIcon } from '../../Icons'

interface DocInfo {
  id: string
  filename: string
  file_size: number
  file_type: string
  parse_status: string
  compile_status: string
  parse_error?: string | null
  created_at: string
}

interface UploadItem {
  file: File
  status: 'pending' | 'uploading' | 'success' | 'error'
  message?: string
}

export function DocumentsTab({ kbId, onRefresh }: { kbId: string; onRefresh: () => void }) {
  const [docs, setDocs] = useState<DocInfo[]>([])
  const [kbCompileStatus, setKbCompileStatus] = useState<string>('pending')
  const [uploadQueue, setUploadQueue] = useState<UploadItem[]>([])
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const uploadIndexRef = useRef(0)
  const pollingRefs = useRef<Map<string, number>>(new Map())

  const fetchDocs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/documents/list/${kbId}`)
      if (res.ok) {
        const data = await res.json()
        setDocs(Array.isArray(data) ? data : [])
      }
    } catch (e) {
      console.error('Failed to fetch docs:', e)
    }
  }, [kbId])

  const fetchKbStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/knowledge-bases`)
      if (res.ok) {
        const data = await res.json()
        const kb = (Array.isArray(data) ? data : []).find((k: any) => k.id === kbId)
        if (kb) setKbCompileStatus(kb.compile_status || 'pending')
      }
    } catch (e) {
      console.error('Failed to fetch KB status:', e)
    }
  }, [kbId])

  useEffect(() => { fetchDocs(); fetchKbStatus() }, [fetchDocs, fetchKbStatus])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      pollingRefs.current.forEach(timer => clearTimeout(timer))
      pollingRefs.current.clear()
    }
  }, [])

  const pollDocumentStatus = useCallback((docId: string) => {
    const maxPolls = 100 // 100 * 3s = 5 minutes
    let pollCount = 0

    const poll = () => {
      fetch(`${API_BASE}/api/documents/${docId}/status`)
        .then(res => res.ok ? res.json() : null)
        .then(data => {
          if (!data) return

          setDocs(prev => prev.map(doc =>
            doc.id === docId
              ? { ...doc, parse_status: data.parse_status, compile_status: data.compile_status, parse_error: data.parse_error }
              : doc
          ))

          if (data.parse_status === 'completed' || data.parse_status === 'failed') {
            pollingRefs.current.delete(docId)
            onRefresh()
            return
          }

          pollCount++
          if (pollCount < maxPolls) {
            const timer = window.setTimeout(poll, 3000)
            pollingRefs.current.set(docId, timer)
          }
        })
        .catch(() => {
          pollingRefs.current.delete(docId)
        })
    }

    poll()
  }, [onRefresh])

  const startBatchUpload = useCallback((files: FileList | File[]) => {
    const items: UploadItem[] = Array.from(files).map(f => ({ file: f, status: 'pending' as const }))
    if (items.length === 0) return
    setUploadQueue(items)
    setUploading(true)
  }, [])

  useEffect(() => {
    if (!uploading || uploadQueue.length === 0) return
    const idx = uploadIndexRef.current
    if (idx >= uploadQueue.length) {
      setUploading(false)
      uploadIndexRef.current = 0
      fetchDocs()
      onRefresh()
      return
    }
    const item = uploadQueue[idx]
    if (item.status !== 'pending') return

    const updated = [...uploadQueue]
    updated[idx] = { ...item, status: 'uploading' as const }
    setUploadQueue(updated)

    const formData = new FormData()
    formData.append('file', item.file)

    fetch(`${API_BASE}/api/documents/upload/${kbId}`, { method: 'POST', body: formData })
      .then(async (res) => {
        const updated2 = [...uploadQueue]
        if (res.ok) {
          const data = await res.json()
          updated2[idx] = { ...updated2[idx], status: 'success', message: data.filename }
          setUploadQueue(updated2)
          uploadIndexRef.current = idx + 1
          // Add doc to list immediately and start polling
          setDocs(prev => [{
            id: data.id,
            filename: data.filename,
            file_size: data.file_size,
            file_type: data.file_type,
            parse_status: data.parse_status,
            compile_status: data.compile_status,
            created_at: new Date().toISOString(),
          }, ...prev])
          if (data.parse_status === 'parsing') {
            pollDocumentStatus(data.id)
          }
        } else {
          const error = await res.json().catch(() => ({ detail: res.statusText }))
          updated2[idx] = { ...updated2[idx], status: 'error', message: error.detail || res.statusText }
          setUploadQueue(updated2)
          uploadIndexRef.current = idx + 1
        }
      })
      .catch((err) => {
        const updated2 = [...uploadQueue]
        updated2[idx] = { ...updated2[idx], status: 'error', message: (err as Error).message }
        setUploadQueue(updated2)
        uploadIndexRef.current = idx + 1
      })
  }, [uploading, uploadQueue, kbId, fetchDocs, onRefresh, pollDocumentStatus])

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files.length > 0) startBatchUpload(e.dataTransfer.files)
  }

  const handleDeleteDoc = async (docId: string) => {
    setConfirmDelete(docId)
  }

  const executeDelete = async () => {
    const docId = confirmDelete
    setConfirmDelete(null)
    if (!docId) return
    try {
      const res = await fetch(`${API_BASE}/api/documents/${docId}`, { method: 'DELETE' })
      if (res.ok || res.status === 204) {
        await fetchDocs()
        onRefresh()
      }
    } catch (e) {
      console.error('Failed to delete doc:', e)
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <ConfirmDialog
        open={confirmDelete !== null}
        title="删除文档"
        message="确定删除此文档？此操作不可撤销。"
        onConfirm={executeDelete}
        onCancel={() => setConfirmDelete(null)}
      />

      {/* Upload area */}
      <div
        className={`mb-6 p-8 bg-white dark:bg-slate-800 rounded-xl border-2 text-center transition-all duration-200 ${
          dragging ? 'border-amber-500 bg-amber-50 dark:bg-amber-900/10 scale-[1.02]' : 'border-dashed border-stone-300 dark:border-slate-600'
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={(e) => { e.preventDefault(); setDragging(false) }}
        onDrop={handleDrop}
      >
        <input ref={fileInputRef} type="file" accept=".pdf,.docx,.doc,.txt,.md,.xlsx,.xls,.csv" multiple onChange={(e) => { if (e.target.files && e.target.files.length > 0) startBatchUpload(e.target.files); if (e.target) e.target.value = '' }} disabled={uploading} className="hidden" id="file-upload-detail" />
        <label htmlFor="file-upload-detail" className={`inline-flex flex-col items-center cursor-pointer ${uploading ? 'opacity-50 pointer-events-none' : ''}`}>
          <svg className="w-12 h-12 text-stone-400 dark:text-stone-500 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4M4 14v6a2 2 0 002 2h12a2 2 0 002-2v-6" />
          </svg>
          <span className="text-stone-600 dark:text-stone-300 font-medium">{dragging ? '松开文件上传' : '点击选择文件（支持批量）'}</span>
          <span className="text-xs text-stone-400 dark:text-stone-500 mt-1">支持 PDF, Word, TXT, Markdown, Excel，可一次选择多个文件</span>
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

      {/* KB compile status */}
      <div className="mb-4 flex items-center gap-3 p-3 bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700">
        <span className="text-sm text-stone-500 dark:text-stone-400">知识库编译状态：</span>
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${compileStatusLabels[kbCompileStatus]?.color || 'bg-gray-100'}`}>
          {compileStatusLabels[kbCompileStatus]?.label || kbCompileStatus}
        </span>
      </div>

      {/* Document list */}
      <div className="space-y-2">
        {docs.length === 0 && <p className="text-sm text-stone-400 dark:text-stone-500 text-center py-8">暂无文档，请上传</p>}
        {docs.map((doc) => (
          <div key={doc.id} className="flex items-center justify-between p-3 bg-white dark:bg-slate-800 rounded-lg border border-stone-200 dark:border-slate-700">
            <div className="flex items-center gap-3">
              <FileTextIcon className="w-5 h-5" />
              <div>
                <p className="text-sm font-medium text-stone-800 dark:text-stone-100">{doc.filename}</p>
                <p className="text-xs text-stone-400 dark:text-stone-500">{formatSize(doc.file_size)} · {typeLabels[doc.file_type] || doc.file_type} · {new Date(doc.created_at).toLocaleDateString('zh-CN')}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {doc.parse_status === 'parsing' ? (
                <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300 inline-flex items-center gap-1">
                  <div className="w-2.5 h-2.5 rounded-full border-2 border-gray-400 border-t-transparent animate-spin" />
                  解析中
                </span>
              ) : (
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${parseStatusLabels[doc.parse_status]?.color || 'bg-gray-100'}`}>
                  {parseStatusLabels[doc.parse_status]?.label || doc.parse_status}
                </span>
              )}
              {doc.parse_status === 'failed' && doc.parse_error && (
                <span className="text-xs text-red-400 cursor-help" title={doc.parse_error}>!</span>
              )}
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${compileStatusLabels[doc.compile_status]?.color || 'bg-gray-100'}`}>
                {compileStatusLabels[doc.compile_status]?.label || doc.compile_status}
              </span>
              <Link to={`/knowledge/${kbId}/documents/${doc.id}`} className="p-1.5 text-stone-400 hover:text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-900/20 rounded-lg transition-colors" title="文档详情">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
                </svg>
              </Link>
              <button onClick={() => handleDeleteDoc(doc.id)} className="p-1.5 text-stone-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors" title="删除">
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
