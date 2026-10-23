import { useId, useState } from 'react'

import { formatValue, unitLabel } from '@/lib/format'
import type { Kpi } from '@/types/contract'

/** KPI 卡：数值统一 tabular-nums；右下角"证据"展开 result_id 与口径。 */
export function KpiCard({ kpi, formula }: { kpi: Kpi; formula?: string }) {
  const [open, setOpen] = useState(false)
  const panelId = useId()

  return (
    <div className="card relative flex h-24 flex-col justify-between p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 truncate text-caption text-muted" title={kpi.label}>
          {kpi.label}
        </p>
        <span className="shrink-0 text-micro text-muted">{unitLabel(kpi.unit)}</span>
      </div>
      <p className="tabular truncate pr-8 text-h3 font-semibold leading-none text-ink" title={kpi.display_value ?? ''}>
        {kpi.display_value ?? formatValue(kpi.value, kpi.unit)}
      </p>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={panelId}
        className="focus-ring absolute bottom-1.5 right-1.5 rounded-sm px-1 text-micro text-muted hover:text-brand-600"
      >
        证据
      </button>
      {open ? (
        <div
          id={panelId}
          className="absolute -bottom-1 left-0 right-0 z-10 translate-y-full rounded-md border border-border bg-surface p-2 text-micro shadow-sm"
        >
          <p className="mb-0.5 text-muted">result_id</p>
          <p className="mb-1 break-all font-mono text-ink">{kpi.evidence_ids.join(', ') || '—'}</p>
          <p className="text-muted">口径</p>
          <p className="break-words text-secondary">{formula ?? '见方法论章节'}</p>
        </div>
      ) : null}
    </div>
  )
}
