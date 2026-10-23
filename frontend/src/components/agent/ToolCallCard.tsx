import { Check, ChevronDown, Copy } from 'lucide-react'
import { useState } from 'react'

import { DataTable, type Column } from '@/components/result/DataTable'
import { JsonView } from '@/components/ui/json-view'
import { StatusPill } from '@/components/ui/status-pill'
import { cn } from '@/lib/cn'
import { formatDuration } from '@/lib/format'
import type { ToolCallRecord } from '@/types/contract'

function asTable(result: Record<string, unknown> | null): { columns: Column[]; rows: Record<string, unknown>[] } | null {
  if (!result) return null
  const columns = result.columns
  const rows = result.rows
  if (!Array.isArray(columns) || !Array.isArray(rows)) return null
  const names = columns.map((item) =>
    typeof item === 'object' && item !== null && 'name' in item ? String((item as { name: unknown }).name) : String(item),
  )
  const records = rows.slice(0, 20).map((row) => {
    if (Array.isArray(row)) {
      return Object.fromEntries(names.map((name, index) => [name, row[index]]))
    }
    return row as Record<string, unknown>
  })
  return { columns: names.map((name) => ({ key: name, label: name })), rows: records }
}

export function ToolCallCard({ record, defaultOpen }: { record: ToolCallRecord; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(Boolean(defaultOpen))
  const [tab, setTab] = useState<'args' | 'result'>('args')
  const [copied, setCopied] = useState(false)

  const table = asTable(record.result)

  const copyResultId = async () => {
    if (!record.result_id) return
    try {
      await navigator.clipboard.writeText(record.result_id)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="rounded-md border border-border bg-surface">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="focus-ring flex w-full items-center gap-2 px-2.5 py-1.5 text-left"
      >
        <ChevronDown size={14} className={cn('text-muted transition-transform', open && 'rotate-180')} aria-hidden />
        <span className="font-mono text-caption text-ink">{record.tool}</span>
        <StatusPill status={record.status} kind="tool" />
        <span className="tabular text-micro text-muted">{formatDuration(record.duration_ms)}</span>
        {record.result_id ? (
          <span
            role="button"
            tabIndex={0}
            onClick={(event) => {
              event.stopPropagation()
              void copyResultId()
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.stopPropagation()
                void copyResultId()
              }
            }}
            className="ml-auto inline-flex items-center gap-1 rounded-sm px-1 font-mono text-micro text-muted hover:text-brand-600"
            title="复制 result_id"
          >
            {copied ? <Check size={11} aria-hidden /> : <Copy size={11} aria-hidden />}
            {record.result_id}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="border-t border-border p-2">
          <div role="tablist" aria-label="工具调用详情" className="mb-2 flex gap-1">
            {(['args', 'result'] as const).map((key) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                onClick={() => setTab(key)}
                className={cn(
                  'focus-ring h-6 rounded-sm px-2 text-micro',
                  tab === key ? 'bg-surface-3 font-medium text-ink' : 'text-secondary hover:bg-surface-3',
                )}
              >
                {key === 'args' ? '参数' : '结果'}
              </button>
            ))}
          </div>

          {tab === 'args' ? (
            <JsonView value={record.arguments} />
          ) : record.error ? (
            <div className="rounded-md border border-danger-600/30 bg-danger-50 p-2.5">
              <p className="font-mono text-micro text-danger-600">{record.error.code}</p>
              <p className="mt-1 text-caption text-danger-600">{record.error.message}</p>
              {record.error.hint ? <p className="mt-1 text-micro text-secondary">{record.error.hint}</p> : null}
            </div>
          ) : table ? (
            <div>
              <DataTable columns={table.columns} rows={table.rows} maxHeight={260} />
              {record.warnings.length > 0 ? (
                <ul className="mt-2 space-y-0.5 text-micro text-warning-600">
                  {record.warnings.map((warning) => (
                    <li key={warning}>· {warning}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : (
            <JsonView value={record.result} />
          )}
        </div>
      ) : null}
    </div>
  )
}
