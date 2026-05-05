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
  const { currentKbId, setActiveTab, activeTab } = useAppStore()

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

  return (
    <aside className="icon-sidebar">
      {/* Brand */}
      <div className="icon-sidebar-brand">
        <DatabaseIcon />
      </div>

      <div className="icon-sidebar-divider" />

      {/* Navigation */}
      <nav className="icon-sidebar-nav">
        {NAV_ITEMS.map((item) => {
          const active = isActive(item)
          return (
            <a
              key={item.label}
              href={item.tab ? '#' : item.to}
              onClick={(e) => handleNav(item, e)}
              className={`icon-sidebar-item${active ? ' active' : ''}`}
            >
              <item.Icon />
              <span className="icon-sidebar-tooltip">{item.label}</span>
            </a>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="icon-sidebar-footer">
        <a
          href="/settings"
          onClick={(e) => { e.preventDefault(); navigate('/settings') }}
          className={`icon-sidebar-item${location.pathname === '/settings' ? ' active' : ''}`}
        >
          <SettingsIcon />
          <span className="icon-sidebar-tooltip">设置</span>
        </a>
        <button
          onClick={toggleTheme}
          className="icon-sidebar-item"
          title="切换主题"
        >
          <SunIcon className="theme-icon-sun" />
          <MoonIcon className="theme-icon-moon" />
          <span className="icon-sidebar-tooltip">切换主题</span>
        </button>
      </div>
    </aside>
  )
}
