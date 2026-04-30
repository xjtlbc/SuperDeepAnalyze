import { useNavigate, useLocation } from 'react-router-dom'
import { toggleTheme } from '../main'
import { useAppStore } from '../store/app'
import {
  HomeIcon, FolderIcon, GraphIcon, ChatIcon, WikiIcon,
  SettingsIcon, SunIcon, MoonIcon, DatabaseIcon,
} from './Icons'

const NAV_ITEMS = [
  { to: '/', label: '首页', Icon: HomeIcon },
  { to: '/knowledge', label: '知识库', Icon: FolderIcon },
  { tab: 'graph', label: '图谱', Icon: GraphIcon },
  { tab: 'chat', label: '对话', Icon: ChatIcon },
  { tab: 'wiki', label: 'Wiki', Icon: WikiIcon },
]

export function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { currentKbId, currentKbName, setActiveTab, activeTab } = useAppStore()

  const isActive = (item: typeof NAV_ITEMS[number]) => {
    if ('to' in item) {
      if (item.to === '/') return location.pathname === '/'
      if (item.to === '/knowledge') return location.pathname.startsWith('/knowledge')
    }
    if ('tab' in item && currentKbId) {
      return location.pathname.includes(currentKbId) && activeTab === item.tab
    }
    return false
  }

  const handleNav = (item: typeof NAV_ITEMS[number], e: React.MouseEvent) => {
    e.preventDefault()
    if ('to' in item) {
      navigate(item.to!)
    } else if ('tab' in item) {
      if (currentKbId) {
        setActiveTab(item.tab as 'graph' | 'chat' | 'wiki')
        navigate(`/knowledge/${currentKbId}`)
      } else {
        sessionStorage.setItem('pendingTab', item.tab)
        navigate('/knowledge')
      }
    }
  }

  const handleDetailHome = (e: React.MouseEvent) => {
    e.preventDefault()
    if (currentKbId) {
      setActiveTab('documents')
      navigate(`/knowledge/${currentKbId}`)
    } else {
      navigate('/knowledge')
    }
  }

  return (
    <aside className="w-56 bg-white dark:bg-slate-800 border-r border-slate-200 dark:border-slate-700 flex flex-col">
      {/* Brand */}
      <div className="px-4 py-4 border-b border-slate-200 dark:border-slate-700">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center">
            <DatabaseIcon className="w-4 h-4 text-white" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-800 dark:text-slate-100 leading-tight">
              SuperDeep
            </h2>
            <p className="text-[10px] text-slate-400 dark:text-slate-500 leading-tight">
              Analyze
            </p>
          </div>
        </div>
      </div>

      {/* Current KB */}
      {currentKbId && currentKbName && (
        <button
          onClick={handleDetailHome}
          className="mx-3 mt-3 px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-700/50 border border-slate-200 dark:border-slate-600 text-left hover:border-primary-300 dark:hover:border-primary-600 transition-colors"
        >
          <p className="text-[10px] uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-0.5">
            当前知识库
          </p>
          <p className="text-sm font-medium text-primary-700 dark:text-primary-400 truncate">
            {currentKbName}
          </p>
        </button>
      )}

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const active = isActive(item)
          return (
            <a
              key={item.label}
              href={item.tab ? '#' : item.to}
              onClick={(e) => handleNav(item, e)}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                active
                  ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-400 border-l-[3px] border-primary-600 dark:border-primary-500 -ml-[3px] pl-[10px]'
                  : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700/50 border-l-[3px] border-transparent -ml-[3px] pl-[10px]'
              }`}
            >
              <item.Icon className="w-[18px] h-[18px] flex-shrink-0" />
              <span>{item.label}</span>
            </a>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-slate-200 dark:border-slate-700 space-y-1">
        <a
          href="/settings"
          onClick={(e) => { e.preventDefault(); navigate('/settings') }}
          className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
            location.pathname === '/settings'
              ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-400'
              : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700/50'
          }`}
        >
          <SettingsIcon className="w-[18px] h-[18px] flex-shrink-0" />
          <span>设置</span>
        </a>
        <button
          onClick={toggleTheme}
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors w-full text-left"
          title="切换主题"
        >
          <span className="w-[18px] h-[18px] flex-shrink-0 flex items-center justify-center">
            <SunIcon className="w-[18px] h-[18px] hidden dark:block" />
            <MoonIcon className="w-[18px] h-[18px] block dark:hidden" />
          </span>
          <span>切换主题</span>
        </button>
      </div>
    </aside>
  )
}
