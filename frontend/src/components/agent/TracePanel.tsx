import { Activity, ArrowDownUp, Gauge, ShieldCheck } from 'lucide-react'
import { useMemo, useState } from 'react'

import { BudgetMeter } from '@/components/agent/BudgetMeter'
import { EmptyState } from '@/components/feedback/EmptyState'
import { InlineAlert } from '@/components/feedback/InlineAlert'
import { JsonView } from '@/components/ui/json-view'
import { CoverageRing } from '@/components/ui/meter'
import { StatusPill } from '@/components/ui/status-pill'
import { Tabs } from '@/components/ui/tabs'
import { cn } from '@/lib/cn'
import { formatClock, formatDuration } from '@/lib/format'
import type { StreamState } from '@/lib/sse'
import { eventLabel, type AppEvent } from '@/types/events'
import type { Budget, Claim, Usage, VerificationResult } from '@/types/contract'

type TabKey = 'stream' | 'verify' | 'budget'

const DOT_TONE: Record<string, string> = {
  run_created: 'bg-muted',
  run_started: 'bg-brand-600',
  dataset_inspected: 'bg-brand-600',
  plan_created: 'bg-brand-600',
  step_started: 'bg-brand-600',
  tool_call_started: 'bg-brand-500',
  tool_call_succeeded: 'bg-success-600',
  tool_call_failed: 'bg-danger-600',
  step_completed: 'bg-success-600',
  replan_requested: 'bg-warning-600',
  verification_completed: 'bg-teal-600',
  report_created: 'bg-success-600',
  budget_warning: 'bg-warning-600',
  run_succeeded: 'bg-success-600',
  run_failed: 'bg-danger-600',
  run_cancelled: 'bg-muted',
}

export function TracePanel({
  events,
  verification,
  claims,
  usage,
  budget,
  elapsedMs,
  streamState,
}: {
  events: AppEvent[]
  verification: VerificationResult | null
  claims: Claim[]
  usage: Usage
  budget: Budget
  elapsedMs: number | null
  streamState: StreamState
}) {
  const [tab, setTab] = useState<TabKey>('stream')
  const [order, setOrder] = useState<'desc' | 'asc'>('desc')
  const [expanded, setExpanded] = useState<number | null>(null)

  const ordered = useMemo(
    () => (order === 'desc' ? [...events].reverse() : events),
    [events, order],
  )

  const claimText = useMemo(() => {
    const map = new Map<string, string>()
    for (const claim of claims) map.set(claim.claim_id, claim.text)
    return map
  }, [claims])

  return (
    <div className="card overflow-hidden">
      <Tabs
        ariaLabel="执行过程视图"
        value={tab}
        onChange={setTab}
        items={[
          { key: 'stream', label: '执行流', count: events.length },
          { key: 'verify', label: '验证' },
          { key: 'budget', label: '预算' },
        ]}
        className="bg-surface-2"
      />

      {tab === 'stream' ? (
        <div>
          {streamState === 'polling' ? (
            <InlineAlert tone="warning" className="m-2">
              实时连接已断开，正在轮询（每 1.5s）。
            </InlineAlert>
          ) : null}
          <div className="flex items-center justify-between px-2 py-1.5">
            <span className="text-micro text-muted">{events.length} 个事件</span>
            <button
              type="button"
              onClick={() => setOrder((value) => (value === 'desc' ? 'asc' : 'desc'))}
              className="focus-ring inline-flex items-center gap-1 rounded-sm px-1 text-micro text-secondary hover:text-ink"
            >
              <ArrowDownUp size={11} aria-hidden />
              {order === 'desc' ? '最新在上' : '最早在上'}
            </button>
          </div>

          {ordered.length === 0 ? (
            <div className="p-3">
              <EmptyState
                compact
                icon={<Activity size={18} />}
                title="暂无执行事件"
                description="运行开始后，每一步工具调用会按时间线出现在这里。"
              />
            </div>
          ) : (
            <ol className="max-h-[440px] overflow-auto px-2 pb-2">
              {ordered.map((event) => {
                const payload = event.payload as Record<string, unknown>
                const duration = typeof payload.duration_ms === 'number' ? payload.duration_ms : null
                const open = expanded === event.seq
                return (
                  <li key={event.seq} className="relative border-l border-border pl-3">
                    <span
                      className={cn(
                        'absolute -left-[3px] top-2.5 size-1.5 rounded-full',
                        DOT_TONE[event.type] ?? 'bg-muted',
                      )}
                      aria-hidden
                    />
                    <button
                      type="button"
                      onClick={() => setExpanded(open ? null : event.seq)}
                      aria-expanded={open}
                      className="focus-ring flex w-full items-center gap-2 rounded-sm py-1 text-left"
                    >
                      <span className="min-w-0 flex-1 truncate text-caption text-secondary">{eventLabel(event)}</span>
                      {duration !== null ? (
                        <span className="shrink-0 tabular text-micro text-muted">{formatDuration(duration)}</span>
                      ) : null}
                      <span className="shrink-0 tabular text-micro text-muted">{formatClock(event.ts)}</span>
                    </button>
                    {open ? <JsonView value={payload} className="mb-2" /> : null}
                  </li>
                )
              })}
            </ol>
          )}
        </div>
      ) : null}

      {tab === 'verify' ? (
        <div className="space-y-3 p-3">
          {verification ? (
            <>
              <div className="flex items-center gap-4">
                <CoverageRing coverage={verification.coverage} />
                <dl className="grid flex-1 grid-cols-3 gap-2 text-micro">
                  <div>
                    <dt className="text-muted">已证实</dt>
                    <dd className="tabular text-success-600">{verification.supported}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">未通过</dt>
                    <dd className="tabular text-danger-600">{verification.unsupported}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">无法验证</dt>
                    <dd className="tabular text-warning-600">{verification.unverifiable}</dd>
                  </div>
                </dl>
              </div>
              <ul className="space-y-1.5">
                {verification.items.map((item) => (
                  <li key={item.claim_id} className="rounded-md border border-border p-2">
                    <div className="flex items-start justify-between gap-2">
                      <p className="min-w-0 flex-1 text-caption text-secondary">
                        {claimText.get(item.claim_id) ?? item.claim_id}
                      </p>
                      <StatusPill status={item.status} kind="verification" />
                    </div>
                    {item.status !== 'supported' ? (
                      <p className="mt-1 text-micro text-muted">
                        {item.reason || '未找到匹配数字'}
                        {item.matched_value !== null ? ` · 最接近证据值 ${item.matched_value}` : ''}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <EmptyState
              compact
              icon={<ShieldCheck size={18} />}
              title="暂无验证结果"
              description="报告生成后，每条结论的数字都会与工具结果逐一比对。"
            />
          )}
        </div>
      ) : null}

      {tab === 'budget' ? (
        <div>
          {events.length === 0 ? (
            <div className="p-3">
              <EmptyState
                compact
                icon={<Gauge size={18} />}
                title="暂无预算消耗"
                description="步数、工具调用、重规划与耗时会实时显示为进度条。"
              />
            </div>
          ) : (
            <BudgetMeter usage={usage} budget={budget} elapsedMs={elapsedMs} />
          )}
        </div>
      ) : null}
    </div>
  )
}
