import { useEffect, useRef } from 'react'
import { AlertCircleIcon, WarningIcon } from './Icons'

interface ConfirmDialogProps {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  variant?: 'danger' | 'default'
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = '确定',
  cancelLabel = '取消',
  variant = 'default',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (open) confirmRef.current?.focus()
  }, [open])

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onCancel])

  if (!open) return null

  const isDanger = variant === 'danger'

  return (
    <div className="confirm-dialog__overlay animate-fade-in" onClick={onCancel}>
      <div className="confirm-dialog__backdrop" />
      <div className="confirm-dialog__content" onClick={(e) => e.stopPropagation()}>
        <div className="confirm-dialog__header">
          <div className={`confirm-dialog__icon-wrap ${isDanger ? 'confirm-dialog__icon-wrap--danger' : 'confirm-dialog__icon-wrap--warning'}`}>
            {isDanger
              ? <AlertCircleIcon className="confirm-dialog__icon confirm-dialog__icon--danger" />
              : <WarningIcon className="confirm-dialog__icon confirm-dialog__icon--warning" />
            }
          </div>
          <div>
            <h3 className="confirm-dialog__title">{title}</h3>
            <p className="confirm-dialog__message">{message}</p>
          </div>
        </div>
        <div className="confirm-dialog__actions">
          <button
            onClick={onCancel}
            className="confirm-dialog__cancel-btn"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            onClick={onConfirm}
            className={`confirm-dialog__confirm-btn ${isDanger ? 'confirm-dialog__confirm-btn--danger' : 'confirm-dialog__confirm-btn--primary'}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
