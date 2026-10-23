import { X } from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/cn'

/**
 * 轻量弹层：role=dialog + aria-modal + Escape 关闭 + 初始焦点。
 * 复杂场景（下拉、tooltip）在后续用到 Radix 时替换，这里只覆盖确认/抽屉。
 */
export function Dialog({
  open,
  title,
  description,
  children,
  footer,
  onClose,
  size = 'sm',
}: {
  open: boolean
  title: string
  description?: string
  children?: ReactNode
  footer?: ReactNode
  onClose: () => void
  size?: 'sm' | 'lg'
}) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    panelRef.current?.focus()
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/20 px-4">
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={cn(
          'w-full rounded-lg border border-border bg-surface shadow-md focus:outline-none',
          size === 'sm' ? 'max-w-[440px]' : 'max-w-[860px]',
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-4 py-3">
          <div>
            <h2 className="text-body-lg font-semibold text-ink">{title}</h2>
            {description ? <p className="mt-0.5 text-caption text-secondary">{description}</p> : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="focus-ring -mr-1 inline-flex size-7 items-center justify-center rounded-sm text-muted hover:bg-surface-3 hover:text-ink"
          >
            <X size={16} aria-hidden />
          </button>
        </div>
        {children ? <div className="max-h-[70vh] overflow-auto p-4">{children}</div> : null}
        {footer ? (
          <div className="flex items-center justify-end gap-2 border-t border-border px-4 py-3">{footer}</div>
        ) : null}
      </div>
    </div>
  )
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = '确认',
  onConfirm,
  onClose,
  danger,
}: {
  open: boolean
  title: string
  description: string
  confirmLabel?: string
  onConfirm: () => void
  onClose: () => void
  danger?: boolean
}) {
  return (
    <Dialog
      open={open}
      title={title}
      description={description}
      onClose={onClose}
      footer={
        <>
          <Button size="sm" variant="secondary" onClick={onClose}>
            取消
          </Button>
          <Button size="sm" variant={danger ? 'danger' : 'primary'} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    />
  )
}
