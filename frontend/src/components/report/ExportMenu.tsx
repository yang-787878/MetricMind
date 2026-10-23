import { Check, ChevronDown, Download, FileText } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { api } from '@/lib/api'
import { cn } from '@/lib/cn'

type Format = 'html' | 'md'

/** 导出下拉：真实下载（window.open 到后端导出端点），含 loading 与失败提示。 */
export function ExportMenu({
  runId,
  disabled,
  disabledReason,
  onError,
}: {
  runId: string
  disabled?: boolean
  disabledReason?: string
  onError?: (message: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [pending, setPending] = useState<Format | null>(null)
  const [done, setDone] = useState<Format | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const trigger = async (format: Format) => {
    if (disabled) return
    setPending(format)
    try {
      const response = await fetch(api.exportUrl(runId, format))
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { error?: { message?: string } } | null
        throw new Error(payload?.error?.message ?? `导出失败（HTTP ${response.status}）`)
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `metricmind-${runId}.${format === 'html' ? 'html' : 'md'}`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
      setDone(format)
      setOpen(false)
      window.setTimeout(() => setDone(null), 2000)
    } catch (error) {
      onError?.(error instanceof Error ? error.message : '导出失败')
    } finally {
      setPending(null)
    }
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={disabled ? disabledReason : '导出报告'}
        className={cn(
          'focus-ring inline-flex h-8 items-center gap-1.5 rounded-md border border-border-strong bg-surface px-3 text-caption font-medium text-ink transition-colors hover:bg-surface-3',
          disabled && 'cursor-not-allowed text-muted',
        )}
      >
        <Download size={14} aria-hidden />
        导出
        <ChevronDown size={12} aria-hidden />
      </button>

      {open && !disabled ? (
        <div
          role="menu"
          aria-label="导出格式"
          className="absolute right-0 top-9 z-30 w-56 rounded-md border border-border bg-surface p-1 shadow-md"
        >
          {(
            [
              { key: 'html' as const, label: 'HTML 报告', detail: '自包含单文件，可离线打开' },
              { key: 'md' as const, label: 'Markdown', detail: 'GFM 表格，图表为数据表' },
            ] satisfies { key: Format; label: string; detail: string }[]
          ).map((item) => (
            <button
              key={item.key}
              type="button"
              role="menuitem"
              onClick={() => void trigger(item.key)}
              className="focus-ring flex w-full items-start gap-2 rounded-sm px-2 py-1.5 text-left hover:bg-surface-3"
            >
              <FileText size={14} className="mt-0.5 shrink-0 text-muted" aria-hidden />
              <span className="min-w-0">
                <span className="block text-caption font-medium text-ink">
                  {item.label}
                  {pending === item.key ? '（生成中…）' : done === item.key ? '（已下载）' : ''}
                </span>
                <span className="block text-micro text-muted">{item.detail}</span>
              </span>
            </button>
          ))}
        </div>
      ) : null}

      {done ? (
        <span className="ml-2 inline-flex items-center gap-1 text-micro text-success-600">
          <Check size={12} aria-hidden />
          已下载
        </span>
      ) : null}
    </div>
  )
}
