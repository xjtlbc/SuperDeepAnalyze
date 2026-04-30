import { create } from 'zustand'

interface Toast {
  id: string
  type: 'success' | 'error' | 'info' | 'warning'
  message: string
}

interface ToastStore {
  toasts: Toast[]
  addToast: (type: Toast['type'], message: string) => void
  removeToast: (id: string) => void
}

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  addToast: (type, message) => {
    const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 6)
    set(state => ({ toasts: [...state.toasts, { id, type, message }] }))
    setTimeout(() => {
      set(state => ({ toasts: state.toasts.filter(t => t.id !== id) }))
    }, 5000)
  },
  removeToast: (id) => {
    set(state => ({ toasts: state.toasts.filter(t => t.id !== id) }))
  },
}))

const TYPE_STYLES: Record<Toast['type'], string> = {
  success: 'bg-green-50 dark:bg-green-900/30 border-green-200 dark:border-green-800 text-green-700 dark:text-green-400',
  error: 'bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-800 text-red-700 dark:text-red-400',
  info: 'bg-blue-50 dark:bg-blue-900/30 border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-400',
  warning: 'bg-amber-50 dark:bg-amber-900/30 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400',
}

const TYPE_ICONS: Record<Toast['type'], string> = {
  success: '✓',
  error: '✗',
  info: 'i',
  warning: '!',
}

export function ToastContainer() {
  const { toasts, removeToast } = useToastStore()

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`flex items-start gap-2 px-4 py-3 rounded-lg border shadow-lg text-sm animate-fade-in ${TYPE_STYLES[toast.type]}`}
        >
          <span className="font-bold text-base leading-none mt-0.5">{TYPE_ICONS[toast.type]}</span>
          <span className="flex-1">{toast.message}</span>
          <button
            onClick={() => removeToast(toast.id)}
            className="text-current opacity-50 hover:opacity-100 text-xs ml-2"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
