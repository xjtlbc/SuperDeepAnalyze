import type { ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';

interface AppLayoutProps {
  children: ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        overflow: 'hidden',
        background: 'var(--bg-primary, var(--bg-secondary))',
        color: 'var(--text)',
      }}
    >
      <Header />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Sidebar />
        <main
          style={{
            flex: 1,
            overflow: 'auto',
            background: 'var(--bg)',
            position: 'relative',
            minWidth: 0,
          }}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
