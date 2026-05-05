import { useAppStore } from '../../store/app';
import { Search } from 'lucide-react';

interface HeaderProps {
  onSearchOpen?: () => void;
}

export function Header({ onSearchOpen }: HeaderProps) {
  const currentKbName = useAppStore((s) => s.currentKbName);

  return (
    <header
      style={{
        height: 48,
        minHeight: 48,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 16px',
        background: 'var(--bg)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {currentKbName && (
          <span
            style={{
              fontSize: 13,
              fontWeight: 500,
              color: 'var(--text-secondary)',
              padding: '2px 10px',
              background: 'var(--bg-tertiary)',
              borderRadius: 4,
            }}
          >
            {currentKbName}
          </span>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {onSearchOpen && (
          <button
            onClick={onSearchOpen}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '4px 10px',
              borderRadius: 6,
              fontSize: 12,
              color: 'var(--text-muted)',
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              cursor: 'pointer',
            }}
          >
            <Search size={14} />
            Ctrl+K
          </button>
        )}
        <div
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: 'var(--success)',
          }}
          title="服务运行中"
        />
      </div>
    </header>
  );
}
