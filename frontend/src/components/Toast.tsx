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
  success: 'toast--success',
  error: 'toast--error',
  info: 'toast--info',
  warning: 'toast--warning',
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
    <div className="toast-container">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`toast animate-fade-in ${TYPE_STYLES[toast.type]}`}
        >
          <span className="toast__icon">{TYPE_ICONS[toast.type]}</span>
          <span className="toast__message">{toast.message}</span>
          <button
            onClick={() => removeToast(toast.id)}
            className="toast__close-btn"
          >
            {'✕'}
          </button>
        </div>
      ))}
    </div>
  )
}
