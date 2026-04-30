import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '../../store/app'
import { FolderOpenIcon } from '../Icons'

interface KB {
  id: string
  name: string
  description: string
  compile_status: string
  document_count: number
  created_at: string
}

const API_BASE = import.meta.env.VITE_API_BASE || ''

export function KnowledgeBaseList() {
  const navigate = useNavigate()
  const { currentKbId, setCurrentKbId, setActiveTab } = useAppStore()
  const [kbs, setKbs] = useState<KB[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')

  useEffect(() => {
    fetchKbs()
  }, [])

  // 自动导航：如果侧边栏设置了 pendingTab，加载后自动进入第一个 KB 的对应 Tab
  useEffect(() => {
    const pendingTab = sessionStorage.getItem('pendingTab')
    if (!pendingTab || kbs.length === 0) return

    sessionStorage.removeItem('pendingTab')
    const firstKb = kbs[0]
    setActiveTab(pendingTab as any)
    navigate(`/knowledge/${firstKb.id}`)
  }, [kbs])

  const fetchKbs = async () => {
    try {
      setError(null)
      const res = await fetch(`${API_BASE}/api/knowledge-bases`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setKbs(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(`加载知识库失败: ${e}`)
      console.error('Failed to fetch KBs:', e)
    }
  }

  const createKB = async () => {
    if (!newName.trim()) return
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/knowledge-bases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName, description: newDesc }),
      })
      if (res.ok) {
        setNewName('')
        setNewDesc('')
        setShowCreate(false)
        await fetchKbs()
      }
    } catch (e) {
      console.error('Failed to create KB:', e)
    }
    setLoading(false)
  }

  const deleteKB = async (id: string) => {
    if (!confirm('确定删除此知识库及所有数据？此操作不可恢复。')) return
    try {
      const res = await fetch(`${API_BASE}/api/knowledge-bases/${id}`, {
        method: 'DELETE',
      })
      if (res.ok || res.status === 204) {
        if (currentKbId === id) {
          setCurrentKbId(null)
          navigate('/knowledge', { replace: true })
        }
        await fetchKbs()
      } else {
        const detail = await res.text().catch(() => '')
        setError(`删除失败: ${detail || `HTTP ${res.status}`}`)
      }
    } catch (e) {
      setError(`删除失败: ${e}`)
    }
  }

  const statusMap: Record<string, { label: string; color: string }> = {
    pending: { label: '待编译', color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
    processing: { label: '编译中', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' },
    completed: { label: '已完成', color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' },
    failed: { label: '失败', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
    partial: { label: '部分完成', color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' },
  }

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-stone-800 dark:text-stone-100">知识库管理</h1>
          <p className="text-sm text-stone-500 dark:text-stone-400 mt-1">管理知识库，上传卷宗，编译分析</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          新建知识库
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={fetchKbs} className="underline text-xs ml-2">重试</button>
        </div>
      )}

      {showCreate && (
        <div className="mb-6 p-5 bg-white dark:bg-slate-800 rounded-xl border border-stone-200 dark:border-slate-700 shadow-sm">
          <h3 className="font-semibold text-stone-800 dark:text-stone-100 mb-4">新建知识库</h3>
          <div className="space-y-3">
            <input
              type="text"
              placeholder="知识库名称"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-stone-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-stone-800 dark:text-stone-100 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && createKB()}
            />
            <input
              type="text"
              placeholder="描述（可选）"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-stone-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-stone-800 dark:text-stone-100 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
            <div className="flex gap-2">
              <button
                onClick={createKB}
                disabled={loading || !newName.trim()}
                className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
              >
                {loading ? '创建中...' : '创建'}
              </button>
              <button
                onClick={() => { setShowCreate(false); setNewName(''); setNewDesc('') }}
                className="px-4 py-2 bg-stone-100 hover:bg-stone-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-stone-600 dark:text-stone-300 rounded-lg text-sm transition-colors"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {kbs.length === 0 ? (
        <div className="text-center py-16 bg-white dark:bg-slate-800 rounded-xl border border-stone-200 dark:border-slate-700">
          <FolderOpenIcon className="w-12 h-12 text-stone-300 dark:text-slate-600 mx-auto mb-3" />
          <p className="text-stone-500 dark:text-stone-400">暂无知识库</p>
          <p className="text-sm text-stone-400 dark:text-stone-500 mt-1">点击上方按钮创建第一个知识库</p>
        </div>
      ) : (
        <div className="space-y-3">
          {kbs.map((kb) => (
            <div
              key={kb.id}
              className={`p-4 bg-white dark:bg-slate-800 rounded-xl border transition-all ${
                currentKbId === kb.id
                  ? 'border-amber-400 dark:border-amber-500 shadow-md ring-1 ring-amber-200 dark:ring-amber-800'
                  : 'border-stone-200 dark:border-slate-700 hover:border-amber-300 dark:hover:border-amber-600'
              }`}
            >
              <div className="flex items-start justify-between">
                <button
                  onClick={() => { setCurrentKbId(kb.id); navigate(`/knowledge/${kb.id}`) }}
                  className="flex-1 text-left cursor-pointer focus:outline-none"
                >
                  <div className="flex items-center gap-3">
                    <h3 className="font-semibold text-stone-800 dark:text-stone-100">{kb.name}</h3>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusMap[kb.compile_status]?.color || 'bg-gray-100 text-gray-600'}`}>
                      {statusMap[kb.compile_status]?.label || kb.compile_status}
                    </span>
                  </div>
                  <p className="text-sm text-stone-500 dark:text-stone-400 mt-1">
                    {kb.description || '暂无描述'} · {kb.document_count} 篇文档 · {kb.id}
                  </p>
                  <p className="text-xs text-stone-400 dark:text-stone-500 mt-1">
                    创建于 {new Date(kb.created_at).toLocaleDateString('zh-CN')}
                  </p>
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); deleteKB(kb.id) }}
                  className="p-2 text-stone-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
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
      )}
    </div>
  )
}
