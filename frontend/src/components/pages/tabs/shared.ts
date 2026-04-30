export const API_BASE = import.meta.env.VITE_API_BASE || ''

export type TabType = 'documents' | 'compile' | 'wiki' | 'graph' | 'chat'

export interface KBInfo {
  name: string
  description: string
  compile_status: string
  document_count: number
}

export const statusMap: Record<string, { label: string; color: string }> = {
  pending: { label: '待编译', color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
  processing: { label: '编译中', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' },
  completed: { label: '已完成', color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' },
  failed: { label: '失败', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
  partial: { label: '部分完成', color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' },
  paused: { label: '已暂停', color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' },
}

export const TYPE_LABELS: Record<string, string> = { person: '人物', location: '地点', organization: '组织', event: '事件', object: '物品', concept: '概念' }

export const compileStatusLabels: Record<string, { label: string; color: string }> = {
  pending: { label: '待编译', color: 'bg-stone-100 text-stone-500 dark:bg-stone-700 dark:text-stone-400' },
  processing: { label: '编译中', color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' },
  completed: { label: '已编译', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' },
  failed: { label: '编译失败', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
  partial: { label: '部分编译', color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' },
  paused: { label: '已暂停', color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' },
}

export const parseStatusLabels: Record<string, { label: string; color: string }> = {
  pending: { label: '待解析', color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
  parsing: { label: '解析中', color: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300' },
  processing: { label: '解析中', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' },
  completed: { label: '已解析', color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' },
  failed: { label: '解析失败', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
}

export function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export const typeLabels: Record<string, string> = { pdf: 'PDF', docx: 'Word', txt: '文本', md: 'Markdown' }
