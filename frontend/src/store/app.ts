import { create } from 'zustand';

type TabType = 'documents' | 'compile' | 'wiki' | 'graph' | 'chat';

interface AppState {
  currentKbId: string | null;
  currentKbName: string | null;
  activeTab: TabType;
  setCurrentKbId: (id: string | null) => void;
  setCurrentKb: (id: string | null, name?: string) => void;
  setActiveTab: (tab: TabType) => void;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
}

const storedKbId = typeof localStorage !== 'undefined' ? localStorage.getItem('currentKbId') : null;
const storedKbName = typeof localStorage !== 'undefined' ? localStorage.getItem('currentKbName') : null;
const storedTab = typeof localStorage !== 'undefined' ? localStorage.getItem('activeTab') : null;

export const useAppStore = create<AppState>((set) => ({
  currentKbId: storedKbId,
  currentKbName: storedKbName,
  activeTab: (storedTab as TabType) || 'documents',
  setCurrentKbId: (id) => {
    if (typeof localStorage !== 'undefined') {
      if (id) localStorage.setItem('currentKbId', id); else localStorage.removeItem('currentKbId');
    }
    set({ currentKbId: id });
  },
  setCurrentKb: (id, name) => {
    if (typeof localStorage !== 'undefined') {
      if (id) { localStorage.setItem('currentKbId', id); localStorage.setItem('currentKbName', name || ''); }
      else { localStorage.removeItem('currentKbId'); localStorage.removeItem('currentKbName'); }
    }
    set({ currentKbId: id, currentKbName: name || null });
  },
  setActiveTab: (tab) => {
    if (typeof localStorage !== 'undefined') localStorage.setItem('activeTab', tab);
    set({ activeTab: tab });
  },
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}));

export type { TabType };
