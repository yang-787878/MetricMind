import { ChevronDown } from 'lucide-react'
import { useState } from 'react'

import { StatusPill } from '@/components/ui/status-pill'
import { cn } from '@/lib/cn'
import type { Claim } from '@/types/contract'

/** 结论证据：展开后显示 claimed → matched 的对比（§6.4 第 4 条）。 */
export function ClaimEvidenceList({ claims }: { claims: Claim[] }) {
  const [open, setOpen] = useState<string | null>(null)

  if (claims.length === 0) {
    return <p className="text-caption text-muted">本报告没有可核验的数字结论。</p>
  }

  return (
    <ul className="space-y-2">
      {claims.map((claim) => {
        const expanded = open === claim.claim_id
        return (
          <li key={claim.claim_id} className="rounded-md border border-border bg-surface">
            <button
              type="button"
              onClick={() => setOpen(expanded ? null : claim.claim_id)}
              aria-expanded={expanded}
              className="focus-ring flex w-full items-start gap-2 p-2.5 text-left"
            >
              <div className="min-w-0 flex-1">
                <p className="text-body text-ink">{claim.text}</p>
                <p className="mt-1 flex flex-wrap items-center gap-1.5 text-micro text-muted">
                  {claim.display_numbers.length > 0 ? (
                    claim.display_numbers.map((value) => (
                      <span key={value} className="tabular rounded-sm bg-surface-3 px-1.5 font-mono text-secondary">
                        {value}
                      </span>
                    ))
                  ) : (
                    <span>无数字</span>
                  )}
                  <span>证据 {claim.evidence_ids.length} 条</span>
                </p>
              </div>
              <StatusPill status={claim.status} kind="verification" />
              <ChevronDown
                size={14}
                className={cn('mt-1 shrink-0 text-muted transition-transform', expanded && 'rotate-180')}
                aria-hidden
              />
            </button>

            {expanded ? (
              <div className="border-t border-border px-2.5 py-2">
                <dl className="grid grid-cols-[72px_minmax(0,1fr)] gap-y-1 text-micro">
                  <dt className="text-muted">证据 ID</dt>
                  <dd className="break-all font-mono text-ink">{claim.evidence_ids.join(', ') || '—'}</dd>
                  <dt className="text-muted">声称值</dt>
                  <dd className="tabular text-ink">
                    {claim.numbers.length > 0
                      ? claim.numbers.map((number) => `${number.value}${number.unit}`).join('，')
                      : '—'}
                  </dd>
                  <dt className="text-muted">证据值</dt>
                  <dd className="tabular text-ink">{claim.matched_value ?? '—'}</dd>
                  <dt className="text-muted">判定</dt>
                  <dd className="text-secondary">{claim.reason || (claim.status === 'supported' ? '在容差范围内命中' : '—')}</dd>
                </dl>
              </div>
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}
