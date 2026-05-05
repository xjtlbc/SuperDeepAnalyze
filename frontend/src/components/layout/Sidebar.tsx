import { useNavigate, useLocation } from 'react-router-dom';
import { FolderIcon, MessageSquare, BookOpen, FileBarChart, Settings } from 'lucide-react';
import { useAppStore } from '../../store/app';

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  route: string;
}

const navItems: NavItem[] = [
  { id: 'chat', label: '对话', icon: <MessageSquare size={18} />, route: '/chat' },
  { id: 'knowledge', label: '知识库', icon: <BookOpen size={18} />, route: '/knowledge' },
  { id: 'graph', label: '图谱', icon: <FileBarChart size={18} />, route: '/graph' },
  { id: 'wiki', label: 'Wiki', icon: <FolderIcon size={18} />, route: '/wiki' },
];

const bottomItems: NavItem[] = [
  { id: 'settings', label: '设置', icon: <Settings size={18} />, route: '/settings' },
];

export function Sidebar() {
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const currentKbId = useAppStore((s) => s.currentKbId);
  const navigate = useNavigate();
  const location = useLocation();

  const width = collapsed ? 56 : 220;

  const isActive = (route: string) => {
    const hash = location.hash.replace('#', '');
    return hash.startsWith(route);
  };

  const handleNav = (item: NavItem) => {
    if (item.route === '/knowledge') {
      const kbId = currentKbId || localStorage.getItem('currentKbId');
      if (kbId) {
        navigate(`/knowledge/${kbId}`);
      } else {
        navigate('/knowledge');
      }
    } else if (item.route === '/graph' || item.route === '/wiki' || item.route === '/chat') {
      const kbId = currentKbId || localStorage.getItem('currentKbId');
      if (kbId) {
        navigate(`/knowledge/${kbId}`);
        sessionStorage.setItem('pendingTab', item.id);
      } else {
        navigate('/knowledge');
        sessionStorage.setItem('pendingTab', item.id);
      }
    } else {
      navigate(item.route);
    }
  };

  return (
    <aside
      style={{
        width,
        minWidth: width,
        height: '100%',
        background: 'var(--bg-secondary)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        transition: 'width 0.2s ease, min-width 0.2s ease',
        overflow: 'hidden',
      }}
    >
      {/* Brand */}
      {!collapsed && (
        <div
          style={{
            padding: '16px 16px 12px',
            borderBottom: '1px solid var(--border)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 8,
                background: 'var(--accent)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#fff',
                fontSize: 14,
                fontWeight: 600,
                flexShrink: 0,
              }}
            >
              SD
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
                SuperDeepAnalyze
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                卷宗深度分析
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Toggle */}
      <button
        onClick={toggleSidebar}
        style={{
          margin: collapsed ? '8px auto' : '4px 8px',
          padding: '4px',
          borderRadius: 6,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-muted)',
          cursor: 'pointer',
          background: 'none',
          border: 'none',
          alignSelf: collapsed ? 'center' : 'flex-end',
        }}
        title={collapsed ? '展开侧边栏' : '收起侧边栏'}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          {collapsed ? (
            <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="2" fill="none" />
          ) : (
            <path d="M10 4l-4 4 4 4" stroke="currentColor" strokeWidth="2" fill="none" />
          )}
        </svg>
      </button>

      {/* Nav items */}
      <nav style={{ flex: 1, padding: collapsed ? '4px' : '4px 8px' }}>
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => handleNav(item)}
            title={collapsed ? item.label : undefined}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: collapsed ? 0 : 10,
              width: '100%',
              padding: collapsed ? '10px 0' : '8px 12px',
              marginBottom: 2,
              borderRadius: 8,
              fontSize: 13,
              fontWeight: isActive(item.route) ? 600 : 400,
              color: isActive(item.route) ? 'var(--accent)' : 'var(--text-secondary)',
              background: isActive(item.route) ? 'var(--accent-subtle)' : 'transparent',
              border: 'none',
              cursor: 'pointer',
              justifyContent: collapsed ? 'center' : 'flex-start',
              transition: 'background 0.15s ease',
            }}
            onMouseEnter={(e) => {
              if (!isActive(item.route)) {
                e.currentTarget.style.background = 'var(--bg-tertiary)';
              }
            }}
            onMouseLeave={(e) => {
              if (!isActive(item.route)) {
                e.currentTarget.style.background = 'transparent';
              }
            }}
          >
            <span style={{ display: 'flex', flexShrink: 0 }}>{item.icon}</span>
            {!collapsed && <span>{item.label}</span>}
          </button>
        ))}
      </nav>

      {/* Bottom items */}
      <div style={{ padding: collapsed ? '4px' : '4px 8px', borderTop: '1px solid var(--border)' }}>
        {bottomItems.map((item) => (
          <button
            key={item.id}
            onClick={() => handleNav(item)}
            title={collapsed ? item.label : undefined}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: collapsed ? 0 : 10,
              width: '100%',
              padding: collapsed ? '10px 0' : '8px 12px',
              marginBottom: 2,
              borderRadius: 8,
              fontSize: 13,
              fontWeight: isActive(item.route) ? 600 : 400,
              color: isActive(item.route) ? 'var(--accent)' : 'var(--text-secondary)',
              background: isActive(item.route) ? 'var(--accent-subtle)' : 'transparent',
              border: 'none',
              cursor: 'pointer',
              justifyContent: collapsed ? 'center' : 'flex-start',
              transition: 'background 0.15s ease',
            }}
          >
            <span style={{ display: 'flex', flexShrink: 0 }}>{item.icon}</span>
            {!collapsed && <span>{item.label}</span>}
          </button>
        ))}
      </div>
    </aside>
  );
}
