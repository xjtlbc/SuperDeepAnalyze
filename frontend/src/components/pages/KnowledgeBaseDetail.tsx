import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAppStore } from '../../store/app'
import { API_BASE, statusMap } from './tabs/shared'
import type { TabType } from './tabs/shared'
import { DocumentIcon, CompileIcon, WikiIcon, GraphIcon, ChatIcon } from '../Icons'
import { DocumentsTab } from './tabs/DocumentsTab'
import { CompileTab } from './tabs/CompileTab'
import { WikiTab } from './tabs/WikiTab'
import { GraphTab } from './tabs/GraphTab'
import { ChatTab } from './tabs/ChatTab'

interface KBInfo {
  name: string
  description: string
  compile_status: string
  document_count: number
}

export function KnowledgeBaseDetail() {
  const { kbId } = useParams<{ kbId: string }>()
  const navigate = useNavigate()
  const { setCurrentKb, activeTab, setActiveTab } = useAppStore()
  const [kbInfo, setKbInfo] = useState<KBInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshKey, setRefreshKey] = useState(0)

  const refreshKbInfo = () => {
    fetch(`${API_BASE}/api/knowledge-bases`)
      .then(r => r.json())
      .then(data => {
        const kb = (Array.isArray(data) ? data : []).find((k: any) => k.id === kbId)
        if (kb) setKbInfo({
          name: kb.name,
          description: kb.description,
          compile_status: kb.compile_status,
          document_count: kb.document_count,
        })
      })
  }

  useEffect(() => {
    if (!kbId) return
    fetch(`${API_BASE}/api/knowledge-bases`)
      .then(r => r.json())
      .then(data => {
        const kb = (Array.isArray(data) ? data : []).find((k: any) => k.id === kbId)
        if (kb) {
          setKbInfo({
            name: kb.name,
            description: kb.description,
            compile_status: kb.compile_status,
            document_count: kb.document_count,
          })
          setCurrentKb(kb.id, kb.name)
        }
        setLoading(false)
      })
      .catch(() => setLoading(false))

    const savedTab = sessionStorage.getItem('pendingTab')
    if (savedTab && ['documents', 'compile', 'wiki', 'graph', 'chat'].includes(savedTab)) {
      setActiveTab(savedTab as TabType)
      sessionStorage.removeItem('pendingTab')
    }
  }, [kbId])

  const handleCompileDone = () => {
    refreshKbInfo()
    setRefreshKey(k => k + 1)
  }

  const handleDocRefresh = () => refreshKbInfo()

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full document-detail__spinner"></div>
      </div>
    )
  }

  if (!kbInfo) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <p className="text-secondary mb-4">未找到知识库</p>
        <button onClick={() => navigate('/knowledge')} className="document-detail__btn-retry">
          返回列表
        </button>
      </div>
    )
  }

  const tabs: { key: TabType; label: string; Icon: React.ComponentType<{className?: string}> }[] = [
    { key: 'documents', label: '文档', Icon: DocumentIcon },
    { key: 'compile', label: '编译', Icon: CompileIcon },
    { key: 'wiki', label: 'Wiki', Icon: WikiIcon },
    { key: 'graph', label: '图谱', Icon: GraphIcon },
    { key: 'chat', label: '对话', Icon: ChatIcon },
  ]

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="kb-detail__header">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/knowledge')}
            className="document-detail__back-btn"
            title="返回知识库列表"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <h1 className="kb-detail__title">{kbInfo.name}</h1>
          {kbInfo.compile_status && (
            <span className={`${statusMap[kbInfo.compile_status]?.color || 'badge badge--muted'}`}>
              {statusMap[kbInfo.compile_status]?.label || kbInfo.compile_status}
            </span>
          )}
          <span className="text-xs text-muted">{kbInfo.document_count} 篇文档</span>
        </div>
      </div>

      {/* Tab bar */}
      <div className="kb-detail__tab-bar">
        {tabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`kb-detail__tab-btn ${activeTab === tab.key ? 'kb-detail__tab-btn--active' : ''}`}
          >
            <tab.Icon className="w-4 h-4" /> <span className="ml-1">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab content — always mounted to preserve WebSocket/streaming state */}
      <div style={{ flex: 1, minHeight: 0, position: 'relative', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', inset: 0, visibility: activeTab === 'documents' ? 'visible' : 'hidden', zIndex: activeTab === 'documents' ? 1 : 0 }}>
          <DocumentsTab kbId={kbId!} onRefresh={handleDocRefresh} />
        </div>
        <div style={{ position: 'absolute', inset: 0, visibility: activeTab === 'compile' ? 'visible' : 'hidden', zIndex: activeTab === 'compile' ? 1 : 0 }}>
          <CompileTab kbId={kbId!} onCompileDone={handleCompileDone} />
        </div>
        <div style={{ position: 'absolute', inset: 0, visibility: activeTab === 'wiki' ? 'visible' : 'hidden', zIndex: activeTab === 'wiki' ? 1 : 0 }}>
          <WikiTab kbId={kbId!} refreshKey={refreshKey} />
        </div>
        <div style={{ position: 'absolute', inset: 0, visibility: activeTab === 'graph' ? 'visible' : 'hidden', zIndex: activeTab === 'graph' ? 1 : 0 }}>
          <GraphTab kbId={kbId!} refreshKey={refreshKey} />
        </div>
        <div style={{ position: 'absolute', inset: 0, visibility: activeTab === 'chat' ? 'visible' : 'hidden', zIndex: activeTab === 'chat' ? 1 : 0 }}>
          <ChatTab kbId={kbId!} />
        </div>
      </div>
    </div>
  )
}
