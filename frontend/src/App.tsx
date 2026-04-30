import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { Sidebar } from './components/Sidebar'
import { ToastContainer } from './components/Toast'
import { SearchDialog } from './components/SearchDialog'
import { Settings as SettingsView } from './components/settings/SettingsView'
import { KnowledgeBaseList } from './components/pages/KnowledgeBaseList'
import { KnowledgeBaseDetail } from './components/pages/KnowledgeBaseDetail'
import { DocumentDetail } from './components/pages/DocumentDetail'
import { FolderIcon, GraphIcon, ChatIcon, WikiIcon, PlusIcon, ArrowRightIcon } from './components/Icons'

function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  )
}

function AppShell() {
  const [searchOpen, setSearchOpen] = useState(false)

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
    <div className="flex h-screen overflow-hidden bg-stone-50 dark:bg-slate-900">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/knowledge" element={<KnowledgeBaseList />} />
          <Route path="/knowledge/:kbId" element={<KnowledgeBaseDetail />} />
          <Route path="/knowledge/:kbId/documents/:docId" element={<DocumentDetail />} />
          <Route path="/upload" element={<NavigateToTab tab="documents" />} />
          <Route path="/graph" element={<NavigateToTab tab="graph" />} />
          <Route path="/chat" element={<NavigateToTab tab="chat" />} />
          <Route path="/wiki" element={<NavigateToTab tab="wiki" />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
      <ToastContainer />
      <SearchDialog open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  )
}

/**
 * Route handler for /graph, /chat, /wiki — stores target tab, then navigates
 * to the current KB's detail page, or to the KB list if no KB is selected.
 */
function NavigateToTab({ tab }: { tab: 'documents' | 'compile' | 'wiki' | 'graph' | 'chat' }) {
  const navigate = useNavigate()
  const location = useLocation()

  // Read current KB from localStorage (set by app store)
  const stored = localStorage.getItem('currentKbId')

  if (stored) {
    sessionStorage.setItem('pendingTab', tab)
    navigate(`/knowledge/${stored}`, { replace: true })
  } else {
    sessionStorage.setItem('pendingTab', tab)
    navigate('/knowledge', { replace: true, state: { from: location.pathname } })
  }

  return null
}

const API_BASE = import.meta.env.VITE_API_BASE || ''

function Home() {
  const navigate = useNavigate()
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
    {
      title: '知识库管理',
      desc: '上传卷宗文档，管理案件材料，构建结构化知识库',
      Icon: FolderIcon,
      to: '/knowledge',
      accent: 'from-blue-500 to-indigo-600',
      bg: 'bg-blue-50 dark:bg-blue-900/20',
      text: 'text-blue-700 dark:text-blue-400',
    },
    {
      title: '关系图谱',
      desc: '实体关联关系可视化，事件脉络一目了然',
      Icon: GraphIcon,
      to: '/graph',
      accent: 'from-emerald-500 to-teal-600',
      bg: 'bg-emerald-50 dark:bg-emerald-900/20',
      text: 'text-emerald-700 dark:text-emerald-400',
    },
    {
      title: '智能对话',
      desc: '基于案情数据的多跳推理问答，深度挖掘信息',
      Icon: ChatIcon,
      to: '/chat',
      accent: 'from-violet-500 to-purple-600',
      bg: 'bg-violet-50 dark:bg-violet-900/20',
      text: 'text-violet-700 dark:text-violet-400',
    },
    {
      title: '案情 Wiki',
      desc: '自动生成结构化案件百科，支持交叉引用与溯源',
      Icon: WikiIcon,
      to: '/wiki',
      accent: 'from-amber-500 to-orange-600',
      bg: 'bg-amber-50 dark:bg-amber-900/20',
      text: 'text-amber-700 dark:text-amber-400',
    },
  ]

  const handleFeatureClick = (to: string) => {
    if (to === '/knowledge') {
      navigate(to)
    } else {
      const stored = localStorage.getItem('currentKbId')
      const tab = to.slice(1) // 'graph', 'chat', 'wiki'
      sessionStorage.setItem('pendingTab', tab)
      if (stored) {
        navigate(`/knowledge/${stored}`)
      } else {
        navigate('/knowledge', { state: { from: to } })
      }
    }
  }

  return (
    <div className="max-w-4xl mx-auto animate-fade-in">
      {/* Hero */}
      <div className="text-center mb-12 pt-8">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary-50 dark:bg-primary-900/30 text-xs font-medium text-primary-700 dark:text-primary-400 mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-primary-500" />
          卷宗深度分析引擎
        </div>
        <h1 className="text-4xl font-bold text-slate-800 dark:text-slate-100 mb-3 tracking-tight">
          SuperDeepAnalyze
        </h1>
        <p className="text-lg text-slate-500 dark:text-slate-400 max-w-md mx-auto leading-relaxed">
          面向公安、检察院、法院的智能卷宗分析系统，支持多层级检索、关系图谱与案情推理
        </p>
      </div>

      {/* Stats (if has data) */}
      {stats && stats.kbs > 0 && (
        <div className="flex justify-center gap-8 mb-12">
          <div className="text-center">
            <p className="text-3xl font-bold text-slate-800 dark:text-slate-100">{stats.kbs}</p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">知识库</p>
          </div>
          <div className="w-px bg-slate-200 dark:bg-slate-700" />
          <div className="text-center">
            <p className="text-3xl font-bold text-slate-800 dark:text-slate-100">{stats.docs}</p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">文档数</p>
          </div>
        </div>
      )}

      {/* Feature Cards */}
      <div className="grid grid-cols-2 gap-4 mb-12">
        {features.map(({ title, desc, Icon, to, bg, text }) => (
          <button
            key={title}
            onClick={() => handleFeatureClick(to)}
            className="group text-left p-5 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:shadow-lg hover:border-slate-300 dark:hover:border-slate-600 transition-all duration-300 hover:-translate-y-0.5"
          >
            <div className={`w-10 h-10 rounded-lg ${bg} flex items-center justify-center mb-3 group-hover:scale-110 transition-transform duration-300`}>
              <Icon className={`w-5 h-5 ${text}`} />
            </div>
            <h3 className="font-semibold text-slate-800 dark:text-slate-100 mb-1 text-sm">
              {title}
            </h3>
            <p className="text-xs text-slate-400 dark:text-slate-500 leading-relaxed mb-3">
              {desc}
            </p>
            <span className={`inline-flex items-center gap-1 text-xs font-medium ${text} opacity-0 group-hover:opacity-100 transition-opacity duration-200`}>
              进入 <ArrowRightIcon className="w-3 h-3" />
            </span>
          </button>
        ))}
      </div>

      {/* Quick Start */}
      <div className="text-center pb-8">
        <p className="text-sm text-slate-400 dark:text-slate-500 mb-4">
          首次使用？从创建知识库开始
        </p>
        <button
          onClick={() => navigate('/knowledge')}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-700 text-white rounded-xl text-sm font-medium transition-all duration-200 hover:shadow-md active:scale-95"
        >
          <PlusIcon className="w-4 h-4" />
          新建知识库
        </button>
      </div>
    </div>
  )
}

function Settings() {
  return <SettingsView />
}

export default App
