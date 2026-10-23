import { AlertTriangle, CheckCircle2, Database } from 'lucide-react'

import { cn } from '@/lib/cn'
import { formatCount } from '@/lib/format'
import type { DatasetQuality, DatasetSummary } from '@/types/contract'

export function QualityBadge({ quality }: { quality: DatasetQuality | undefined }) {
  if (!quality) return null
  const warnings = quality.issues.filter((issue) => issue.severity !== 'info').length
  const clean = warnings === 0
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-pill px-2 py-0.5 text-micro',
        clean ? 'bg-success-50 text-success-600' : 'bg-warning-50 text-warning-600',
      )}
      title={clean ? '未发现需要关注的数据质量问题' : `${warnings} 项需要关注的质量问题`}
    >
      {clean ? <CheckCircle2 size={11} aria-hidden /> : <AlertTriangle size={11} aria-hidden />}
      {clean ? '质量良好' : `${warnings} 项问题`}
    </span>
  )
}

export function DatasetCard({
  dataset,
  selected,
  onSelect,
}: {
  dataset: DatasetSummary
  selected?: boolean
  onSelect?: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        'focus-ring flex w-full items-start gap-2 rounded-md border px-2.5 py-2 text-left transition-colors',
        selected
          ? 'border-brand-100 bg-brand-50'
          : 'border-border bg-surface hover:border-border-strong hover:bg-surface-2',
      )}
    >
      <Database size={14} className={cn('mt-0.5 shrink-0', selected ? 'text-brand-600' : 'text-muted')} aria-hidden />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-caption font-medium text-ink" title={dataset.name}>
          {dataset.name}
        </span>
        <span className="mt-0.5 block tabular text-micro text-muted">
          {formatCount(dataset.row_count)} 行 · {dataset.column_count} 列
        </span>
      </span>
    </button>
  )
}
