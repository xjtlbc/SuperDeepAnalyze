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
    pending: { label: '待编译', color: 'badge badge--pending' },
    processing: { label: '编译中', color: 'badge badge--processing' },
    completed: { label: '已完成', color: 'badge badge--completed' },
    failed: { label: '失败', color: 'badge badge--failed' },
    partial: { label: '部分完成', color: 'badge badge--partial' },
  }

  return (
    <div className="kb-list__container">
      <div className="kb-list__header">
        <div>
          <h1 className="kb-list__title">知识库管理</h1>
          <p className="kb-list__subtitle mt-1">管理知识库，上传卷宗，编译分析</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="document-detail__btn-retry"
        >
          新建知识库
        </button>
      </div>

      {error && (
        <div className="kb-list__error-bar mb-4">
          <span>{error}</span>
          <button onClick={fetchKbs} className="kb-list__error-retry">重试</button>
        </div>
      )}

      {showCreate && (
        <div className="kb-list__create-form mb-6">
          <h3 className="kb-list__create-title mb-4">新建知识库</h3>
          <div className="kb-list__create-fields">
            <input
              type="text"
              placeholder="知识库名称"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="kb-list__input w-full"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && createKB()}
            />
            <input
              type="text"
              placeholder="描述（可选）"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              className="kb-list__input w-full"
            />
            <div className="flex gap-2">
              <button
                onClick={createKB}
                disabled={loading || !newName.trim()}
                className="document-detail__btn-retry"
              >
                {loading ? '创建中...' : '创建'}
              </button>
              <button
                onClick={() => { setShowCreate(false); setNewName(''); setNewDesc('') }}
                className="kb-list__cancel-btn"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {kbs.length === 0 ? (
        <div className="kb-list__empty-state">
          <FolderOpenIcon className="document-detail__empty-icon mx-auto mb-3" />
          <p className="text-secondary">暂无知识库</p>
          <p className="text-sm text-muted mt-1">点击上方按钮创建第一个知识库</p>
        </div>
      ) : (
        <div className="kb-list__items">
          {kbs.map((kb) => (
            <div
              key={kb.id}
              className={`kb-list__item ${currentKbId === kb.id ? 'kb-list__item--active' : ''}`}
            >
              <div className="flex items-start justify-between">
                <button
                  onClick={() => { setCurrentKbId(kb.id); navigate(`/knowledge/${kb.id}`) }}
                  className="flex-1 text-left cursor-pointer"
                >
                  <div className="flex items-center gap-3">
                    <h3 className="font-semibold text-primary">{kb.name}</h3>
                    <span className={`${statusMap[kb.compile_status]?.color || 'badge badge--muted'}`}>
                      {statusMap[kb.compile_status]?.label || kb.compile_status}
                    </span>
                  </div>
                  <p className="text-sm text-secondary mt-1">
                    {kb.description || '暂无描述'} · {kb.document_count} 篇文档 · {kb.id}
                  </p>
                  <p className="text-xs text-muted mt-1">
                    创建于 {new Date(kb.created_at).toLocaleDateString('zh-CN')}
                  </p>
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); deleteKB(kb.id) }}
                  className="kb-list__delete-btn"
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
