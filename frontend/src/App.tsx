import React, { Component, Suspense, useEffect, useState } from 'react'
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { ToastContainer } from './components/Toast'
import { SearchDialog } from './components/SearchDialog'
import { useAppStore } from './store/app'

// Lazy-loaded pages
const KnowledgeBaseList = React.lazy(() => import('./components/pages/KnowledgeBaseList').then(m => ({ default: m.KnowledgeBaseList })))
const KnowledgeBaseDetail = React.lazy(() => import('./components/pages/KnowledgeBaseDetail').then(m => ({ default: m.KnowledgeBaseDetail })))
const DocumentDetail = React.lazy(() => import('./components/pages/DocumentDetail').then(m => ({ default: m.DocumentDetail })))
const SettingsView = React.lazy(() => import('./components/settings/SettingsView').then(m => ({ default: m.Settings })))

class ErrorBoundary extends Component<{ children: React.ReactNode }, { hasError: boolean; error: string }> {
  state = { hasError: false, error: '' }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message || 'Unknown error' }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 32, textAlign: 'center', color: '#333' }}>
          <h2>页面出现错误</h2>
          <p style={{ color: '#666', margin: '12px 0' }}>{this.state.error}</p>
          <button
            onClick={() => { this.setState({ hasError: false, error: '' }); window.location.reload() }}
            style={{ padding: '8px 24px', background: '#4c6ef5', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer' }}
          >
            刷新页面
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function LoadingFallback() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
      <span style={{ color: 'var(--text-muted)', fontSize: 14 }}>加载中...</span>
    </div>
  )
}

function PageErrorBoundary({ children }: { children: React.ReactNode }) {
  return <ErrorBoundary>{children}</ErrorBoundary>
}

function RedirectTo({ to }: { to: string }) {
  // Substitute :params from the current URL into the target path
  const currentHash = window.location.hash.replace('#/', '')
  const targetPath = to.replace(/:(\w+)/g, (_match, key) => {
    // Extract the corresponding segment from the current URL
    const segments = currentHash.split('/')
    const toSegments = to.split('/')
    const idx = toSegments.findIndex(s => s === `:${key}`)
    return idx >= 0 && idx < segments.length ? segments[idx] : `:${key}`
  })
  return <Navigate to={`/${targetPath}`} replace />
}

function NavigateToTab({ tab }: { tab: 'documents' | 'compile' | 'wiki' | 'graph' | 'chat' }) {
  const stored = localStorage.getItem('currentKbId')
  sessionStorage.setItem('pendingTab', tab)
  if (stored) {
    return <Navigate to={`/knowledge/${stored}`} replace />
  }
  return <Navigate to="/knowledge" replace />
}

function App() {
  return (
    <HashRouter>
      <AppShell />
    </HashRouter>
  )
}

function AppShell() {
  const [searchOpen, setSearchOpen] = useState(false)
  const currentKbId = useAppStore((s) => s.currentKbId)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setSearchOpen(prev => !prev)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <AppLayout>
      <Suspense fallback={<LoadingFallback />}>
        <Routes>
          <Route path="/" element={<PageErrorBoundary><Home /></PageErrorBoundary>} />
          <Route path="/knowledge" element={<PageErrorBoundary><KnowledgeBaseList /></PageErrorBoundary>} />
          <Route path="/knowledge/:kbId" element={<PageErrorBoundary><KnowledgeBaseDetail /></PageErrorBoundary>} />
          <Route path="/knowledge/:kbId/documents/:docId" element={<PageErrorBoundary><DocumentDetail /></PageErrorBoundary>} />
          <Route path="/upload" element={<NavigateToTab tab="documents" />} />
          <Route path="/graph" element={<NavigateToTab tab="graph" />} />
          <Route path="/chat" element={<NavigateToTab tab="chat" />} />
          <Route path="/wiki" element={<NavigateToTab tab="wiki" />} />
          <Route path="/settings" element={<PageErrorBoundary><Settings /></PageErrorBoundary>} />
          {/* Aliases for common URL patterns */}
          <Route path="/kb/:kbId" element={<RedirectTo to="/knowledge/:kbId" />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
      <ToastContainer />
      <SearchDialog open={searchOpen} onClose={() => setSearchOpen(false)} kbId={currentKbId || undefined} />
    </AppLayout>
  )
}

const API_BASE = (import.meta as any).env?.VITE_API_BASE || ''

function Home() {
  const [stats, setStats] = useState<{ kbs: number; docs: number } | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/knowledge-bases`)
      .then(r => r.json())
      .then(data => {
        if (Array.isArray(data)) {
          const totalDocs = data.reduce((sum: number, kb: any) => sum + (kb.document_count || 0), 0)
          setStats({ kbs: data.length, docs: totalDocs })
        }
      })
      .catch(() => {})
  }, [])

  const features = [
    { title: '知识库管理', desc: '上传卷宗文档，管理案件材料，构建结构化知识库', to: '/knowledge', color: '#4c6ef5' },
    { title: '关系图谱', desc: '实体关联关系可视化，事件脉络一目了然', to: '/graph', color: '#2f9e44' },
    { title: '智能对话', desc: '基于案情数据的多跳推理问答，深度挖掘信息', to: '/chat', color: '#7950f2' },
    { title: '案情 Wiki', desc: '自动生成结构化案件百科，支持交叉引用与溯源', to: '/wiki', color: '#e8590c' },
  ]

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '48px 24px' }}>
      <div style={{ textAlign: 'center', marginBottom: 48 }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '4px 14px', borderRadius: 20, background: 'var(--accent-subtle)', fontSize: 13, color: 'var(--accent)', marginBottom: 20 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--success)' }} />
          卷宗深度分析引擎
        </div>
        <h1 style={{ fontSize: 30, fontWeight: 700, margin: '0 0 8px', color: 'var(--text)' }}>
          SuperDeepAnalyze
        </h1>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', margin: 0 }}>
          面向公安、检察院、法院的智能卷宗分析系统，支持多层级检索、关系图谱与案情推理
        </p>
      </div>

      {stats && stats.kbs > 0 && (
        <div style={{ display: 'flex', justifyContent: 'center', gap: 32, marginBottom: 40 }}>
          <div style={{ textAlign: 'center' }}>
            <p style={{ fontSize: 28, fontWeight: 700, margin: 0, color: 'var(--accent)' }}>{stats.kbs}</p>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '4px 0 0' }}>知识库</p>
          </div>
          <div style={{ width: 1, background: 'var(--border)' }} />
          <div style={{ textAlign: 'center' }}>
            <p style={{ fontSize: 28, fontWeight: 700, margin: 0, color: 'var(--accent)' }}>{stats.docs}</p>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '4px 0 0' }}>文档数</p>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 16, marginBottom: 40 }}>
        {features.map(({ title, desc, to, color }) => (
          <a
            key={title}
            href={`#${to}`}
            style={{
              display: 'block',
              padding: 20,
              borderRadius: 12,
              border: '1px solid var(--border)',
              background: 'var(--bg)',
              textDecoration: 'none',
              color: 'inherit',
              transition: 'box-shadow 0.15s ease, transform 0.15s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.boxShadow = 'var(--shadow-md)'
              e.currentTarget.style.transform = 'translateY(-2px)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.boxShadow = 'none'
              e.currentTarget.style.transform = 'translateY(0)'
            }}
          >
            <div style={{ width: 36, height: 36, borderRadius: 10, background: `${color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
              <div style={{ width: 16, height: 16, borderRadius: 4, background: color }} />
            </div>
            <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 4px', color: 'var(--text)' }}>{title}</h3>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: 0, lineHeight: 1.5 }}>{desc}</p>
          </a>
        ))}
      </div>

      <div style={{ textAlign: 'center' }}>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>首次使用？从创建知识库开始</p>
        <a
          href="#/knowledge"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 20px',
            borderRadius: 8,
            background: 'var(--accent)',
            color: '#fff',
            fontSize: 14,
            fontWeight: 500,
            textDecoration: 'none',
          }}
        >
          + 新建知识库
        </a>
      </div>
    </div>
  )
}

function Settings() {
  return <SettingsView />
}

export default App
