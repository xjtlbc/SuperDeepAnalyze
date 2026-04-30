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
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-amber-500 border-t-transparent"></div>
      </div>
    )
  }

  if (!kbInfo) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <p className="text-stone-500 dark:text-stone-400 mb-4">未找到知识库</p>
        <button onClick={() => navigate('/knowledge')} className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm">
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
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/knowledge')}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-slate-700 text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 transition-colors"
            title="返回知识库列表"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <h1 className="text-2xl font-bold text-stone-800 dark:text-stone-100">{kbInfo.name}</h1>
          {kbInfo.compile_status && (
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusMap[kbInfo.compile_status]?.color || 'bg-gray-100 text-gray-600'}`}>
              {statusMap[kbInfo.compile_status]?.label || kbInfo.compile_status}
            </span>
          )}
          <span className="text-xs text-stone-400 dark:text-stone-500">{kbInfo.document_count} 篇文档</span>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 mb-4 border-b border-stone-200 dark:border-slate-700">
        {tabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 ${
              activeTab === tab.key
                ? 'border-amber-500 text-amber-700 dark:text-amber-400'
                : 'border-transparent text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-300'
            }`}
          >
            <tab.Icon className="w-4 h-4" /> <span className="ml-1">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {activeTab === 'documents' && <DocumentsTab kbId={kbId!} onRefresh={handleDocRefresh} />}
        {activeTab === 'compile' && <CompileTab kbId={kbId!} onCompileDone={handleCompileDone} />}
        {activeTab === 'wiki' && <WikiTab kbId={kbId!} refreshKey={refreshKey} />}
        {activeTab === 'graph' && <GraphTab kbId={kbId!} refreshKey={refreshKey} />}
        {activeTab === 'chat' && <ChatTab kbId={kbId!} />}
      </div>
    </div>
  )
}
