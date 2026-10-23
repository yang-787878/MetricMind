import type { ReactNode } from 'react'

import { cn } from '@/lib/cn'

export interface Column {
  key: string
  label: string
  align?: 'left' | 'right'
}

function isNumeric(value: unknown): boolean {
  return typeof value === 'number' || (typeof value === 'string' && value !== '' && !Number.isNaN(Number(value)))
}

function cell(value: unknown): ReactNode {
  if (value === null || value === undefined || value === '') return <span className="text-muted">∅</span>
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') return value.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
  return String(value)
}

/** 表格：粘性表头、数值右对齐、空值灰显（§7.5 第 4 条）。 */
export function DataTable({
  columns,
  rows,
  maxHeight = 320,
  className,
}: {
  columns: Column[]
  rows: Record<string, unknown>[]
  maxHeight?: number
  className?: string
}) {
  if (rows.length === 0) {
    return <p className="rounded-md border border-border bg-surface-2 px-3 py-4 text-caption text-muted">没有数据行</p>
  }

  return (
    <div
      className={cn('overflow-auto rounded-md border border-border', className)}
      style={{ maxHeight }}
      tabIndex={0}
      role="region"
      aria-label="数据表格"
    >
      <table className="w-full table-auto border-collapse text-caption">
        <thead className="sticky top-0 z-10 bg-surface-2">
          <tr className="border-b border-border text-micro text-muted">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cn('whitespace-nowrap px-2.5 py-1.5 font-medium', column.align === 'right' ? 'text-right' : 'text-left')}
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-border/60 last:border-0 hover:bg-surface-2">
              {columns.map((column) => {
                const value = row[column.key]
                const numeric = column.align === 'right' || isNumeric(value)
                return (
                  <td
                    key={column.key}
                    className={cn(
                      'px-2.5 py-1.5 align-top text-ink',
                      numeric && 'text-right tabular',
                      typeof value === 'string' && value.length > 60 && 'max-w-[280px] break-words',
                    )}
                  >
                    {cell(value)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
