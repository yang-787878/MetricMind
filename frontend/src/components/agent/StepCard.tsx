import { ChevronDown } from 'lucide-react'
import { useState } from 'react'

import { ToolCallCard } from '@/components/agent/ToolCallCard'
import { StatusPill } from '@/components/ui/status-pill'
import { cn } from '@/lib/cn'
import { formatDuration } from '@/lib/format'
import type { StepRecord } from '@/types/contract'

const DOT: Record<string, string> = {
  pending: 'border border-border-strong bg-surface',
  running: 'border-2 border-brand-600 bg-surface animate-pulse',
  succeeded: 'bg-success-600',
  failed: 'bg-danger-600',
  skipped: 'border border-dashed border-border-strong bg-surface',
}

/** 计划时间线中的一个步骤：折叠时 64px，当前步自动展开（§7.5 第 3 条）。 */
export function StepCard({
  step,
  index,
  expanded,
  onToggle,
}: {
  step: StepRecord
  index: number
  expanded: boolean
  onToggle: () => void
}) {
  const [showPlanBasis, setShowPlanBasis] = useState(false)

  return (
    <li className="relative pl-9">
      <span
        className={cn(
          'absolute left-[3px] top-3 flex size-5 items-center justify-center rounded-full text-micro font-medium',
          DOT[step.status] ?? DOT.pending,
          step.status === 'succeeded' && 'text-ink-inverse',
          step.status === 'failed' && 'text-ink-inverse',
          (step.status === 'pending' || step.status === 'skipped') && 'text-muted',
        )}
        aria-hidden
      >
        {step.status === 'succeeded' ? '✓' : step.status === 'failed' ? '!' : index + 1}
      </span>

      <div className={cn('border-b border-border py-2', expanded ? '' : 'pb-2')}>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          className="focus-ring flex w-full items-center gap-2 rounded-sm text-left"
        >
          <span className="min-w-0 flex-1 truncate text-body-lg font-medium text-ink">{step.title}</span>
          <span className="shrink-0 rounded-sm bg-surface-3 px-1.5 font-mono text-micro text-secondary">{step.tool}</span>
          <span className="shrink-0 tabular text-micro text-muted">{formatDuration(step.duration_ms)}</span>
          <StatusPill status={step.status} kind="step" />
          <ChevronDown size={14} className={cn('shrink-0 text-muted transition-transform', expanded && 'rotate-180')} aria-hidden />
        </button>

        {expanded ? (
          <div className="mt-1.5 space-y-2">
            {step.intent ? <p className="text-caption text-secondary">{step.intent}</p> : null}
            {step.summary ? <p className="text-caption text-secondary">{step.summary}</p> : null}

            <div>
              <button
                type="button"
                onClick={() => setShowPlanBasis((value) => !value)}
                aria-expanded={showPlanBasis}
                className="focus-ring rounded-sm text-micro text-muted hover:text-ink"
              >
                {showPlanBasis ? '收起计划依据' : '计划依据'}
              </button>
              {showPlanBasis ? (
                <dl className="mt-1 space-y-1 rounded-md bg-surface-2 p-2 text-micro text-secondary">
                  <div className="flex gap-2">
                    <dt className="w-16 shrink-0 text-muted">预期输出</dt>
                    <dd className="min-w-0 flex-1">{step.expected_output || '—'}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="w-16 shrink-0 text-muted">验证方式</dt>
                    <dd className="min-w-0 flex-1">{step.validation || '—'}</dd>
                  </div>
                </dl>
              ) : null}
            </div>

            {step.tool_calls.length > 0 ? (
              <div className="space-y-1.5">
                {step.tool_calls.map((record) => (
                  <ToolCallCard key={record.call_id} record={record} defaultOpen={step.status === 'failed'} />
                ))}
              </div>
            ) : (
              <p className="rounded-md border border-dashed border-border px-2.5 py-2 text-caption text-muted">
                这一步还没有执行记录
              </p>
            )}
          </div>
        ) : null}
      </div>
    </li>
  )
}
