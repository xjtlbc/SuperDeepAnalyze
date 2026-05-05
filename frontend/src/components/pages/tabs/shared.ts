export const API_BASE = import.meta.env.VITE_API_BASE || ''

export type TabType = 'documents' | 'compile' | 'wiki' | 'graph' | 'chat'

export interface KBInfo {
  name: string
  description: string
  compile_status: string
  document_count: number
}

export const statusMap: Record<string, { label: string; color: string }> = {
  pending: { label: '待编译', color: 'badge badge--pending' },
  processing: { label: '编译中', color: 'badge badge--processing' },
  completed: { label: '已完成', color: 'badge badge--completed' },
  failed: { label: '失败', color: 'badge badge--failed' },
  partial: { label: '部分完成', color: 'badge badge--partial' },
  paused: { label: '已暂停', color: 'badge badge--partial' },
}

export const TYPE_LABELS: Record<string, string> = { person: '人物', location: '地点', organization: '组织', event: '事件', object: '物品', concept: '概念' }

export const compileStatusLabels: Record<string, { label: string; color: string }> = {
  pending: { label: '待编译', color: 'badge badge--muted' },
  processing: { label: '编译中', color: 'badge badge--pending' },
  completed: { label: '已编译', color: 'badge badge--processing' },
  failed: { label: '编译失败', color: 'badge badge--failed' },
  partial: { label: '部分编译', color: 'badge badge--partial' },
  paused: { label: '已暂停', color: 'badge badge--partial' },
}

export const parseStatusLabels: Record<string, { label: string; color: string }> = {
  pending: { label: '待解析', color: 'badge badge--pending' },
  parsing: { label: '解析中', color: 'badge badge--muted' },
  processing: { label: '解析中', color: 'badge badge--processing' },
  completed: { label: '已解析', color: 'badge badge--completed' },
  failed: { label: '解析失败', color: 'badge badge--failed' },
}

export function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export const typeLabels: Record<string, string> = { pdf: 'PDF', docx: 'Word', txt: '文本', md: 'Markdown' }
