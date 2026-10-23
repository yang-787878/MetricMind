import { ArrowLeft, Ban, FileText } from 'lucide-react'
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { PlanTimeline } from '@/components/agent/PlanTimeline'
import { TracePanel } from '@/components/agent/TracePanel'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { InlineAlert } from '@/components/feedback/InlineAlert'
import { SkeletonBlock, SkeletonLines } from '@/components/feedback/Skeleton'
import { ReportView } from '@/components/report/ReportView'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/dialog'
import { StatusPill } from '@/components/ui/status-pill'
import { useRunStream } from '@/hooks/useRunStream'
import { useRun, TERMINAL_STATUSES } from '@/hooks/useRuns'
import { api } from '@/lib/api'
import { chartsFromRun } from '@/lib/charts'
import { formatDuration, formatPercent } from '@/lib/format'

export function WorkspacePage() {
  const { runId } = useParams()
  const navigate = useNavigate()
  const { data: run, isPending, error, refetch } = useRun(runId)
  const terminal = Boolean(run && TERMINAL_STATUSES.has(run.status))
  const { events, state: streamState } = useRunStream(runId, { enabled: Boolean(runId) && !terminal })
  const [confirmCancel, setConfirmCancel] = useState(false)

  const cancel = useMutation({
    mutationFn: () => api.cancelRun(runId as string),
    onSuccess: () => {
      setConfirmCancel(false)
      void refetch()
    },
  })

  if (!runId) {
    return (
      <EmptyState
        icon={<FileText size={20} />}
        title="还没有进行中的分析"
        description="先回到首页选择数据集并提一个问题，Agent 会先给计划、再逐步执行。"
        action={
          <Link to="/" className="focus-ring rounded-md border border-border-strong bg-surface px-3 py-1.5 text-caption text-ink hover:bg-surface-3">
            返回首页
          </Link>
        }
      />
    )
  }

  if (isPending) {
    return (
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]" aria-busy="true">
        <div className="space-y-4">
          <SkeletonBlock className="h-7 w-2/3" />
          <SkeletonBlock className="h-8 w-full" />
          <div className="card space-y-3 p-4">
            <SkeletonLines rows={4} />
          </div>
          <SkeletonBlock className="h-24 w-full" />
        </div>
        <SkeletonBlock className="h-[420px] w-full" />
      </div>
    )
  }

  if (error || !run) {
    return <ErrorState error={error} title="运行详情加载失败" onRetry={() => void refetch()} />
  }

  const budget = run.budget
  const coverage = run.verification?.coverage
  const charts = chartsFromRun(run)
  const replans = events
    .filter((event) => event.type === 'replan_requested')
    .map((event) => ({
      failedStepId: (event.payload.failed_step_id as string | null) ?? null,
      count: Number(event.payload.replan_count ?? 1),
    }))

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px] xl:grid-cols-[minmax(0,1fr)_380px]">
      <div className="min-w-0 space-y-4">
        <header>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="flex items-center gap-2 text-micro text-muted">
                <span>{run.dataset_name ?? '数据集'}</span>
                <span aria-hidden>·</span>
                <span className="font-mono">{run.run_id}</span>
              </p>
              <h1 className="mt-1 line-clamp-2 text-h4 font-semibold text-ink" title={run.question}>
                {run.question}
              </h1>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <StatusPill status={run.status} />
              {!terminal ? (
                <Button size="sm" variant="secondary" icon={<Ban size={14} aria-hidden />} onClick={() => setConfirmCancel(true)}>
                  终止分析
                </Button>
              ) : (
                <Button size="sm" variant="ghost" icon={<ArrowLeft size={14} aria-hidden />} onClick={() => navigate('/')}>
                  返回首页
                </Button>
              )}
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md bg-surface-3 px-3 py-1.5 text-micro text-secondary">
            <span className="font-mono">{run.model ?? '—'}</span>
            <span>
              已用 <span className="tabular text-ink">{run.usage.steps_used}</span>/{budget.max_steps} 步
            </span>
            <span>
              工具 <span className="tabular text-ink">{run.usage.tool_calls_used}</span>/{budget.max_tool_calls}
            </span>
            <span>耗时 {formatDuration(run.duration_ms)}</span>
            <span>验证覆盖 {coverage !== undefined ? formatPercent(coverage) : '—'}</span>
          </div>
        </header>

        {run.error ? (
          <InlineAlert tone="danger" title={`运行失败（${run.error.code}）`}>
            {run.error.message}
            {run.error.hint ? <span className="mt-0.5 block text-secondary">{run.error.hint}</span> : null}
          </InlineAlert>
        ) : null}
        {run.warnings.length > 0 ? (
          <InlineAlert tone="warning" title={`运行提示（${run.warnings.length}）`}>
            <ul className="mt-1 space-y-0.5">
              {run.warnings.slice(0, 4).map((warning) => (
                <li key={warning}>· {warning}</li>
              ))}
            </ul>
          </InlineAlert>
        ) : null}

        <section aria-labelledby="plan">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 id="plan" className="text-h4 font-semibold text-ink">
              分析计划
            </h2>
            <span className="text-micro text-muted">{run.steps.length} 步</span>
          </div>
          <div className="card p-3">
            <PlanTimeline steps={run.steps} plan={run.plan} replans={replans} />
          </div>
        </section>

        {run.report ? (
          <section aria-labelledby="report">
            <div className="mb-2 flex items-baseline justify-between">
              <h2 id="report" className="text-h4 font-semibold text-ink">
                报告
              </h2>
              <Link to={`/runs/${run.run_id}/report`} className="focus-ring rounded-sm text-caption text-brand-600 hover:text-brand-700">
                打开完整报告 →
              </Link>
            </div>
            <ReportView report={run.report} charts={charts} compact />
          </section>
        ) : (
          <section aria-labelledby="results">
            <h2 id="results" className="mb-2 text-h4 font-semibold text-ink">
              关键结果
            </h2>
            <EmptyState
              compact
              icon={<FileText size={18} />}
              title="结果将在报告生成后出现"
              description="KPI、图表与结论都来自工具执行结果；运行完成后这里会展示可核验的报告。"
            />
          </section>
        )}
      </div>

      <aside className="min-w-0 lg:sticky lg:top-[72px] lg:self-start" aria-label="执行过程">
        <TracePanel
          events={events}
          verification={run.verification}
          claims={run.report?.claims ?? []}
          usage={run.usage}
          budget={run.budget}
          elapsedMs={run.duration_ms}
          streamState={streamState}
        />
        <p className="mt-2 text-micro text-muted">
          预算上限：{run.budget.max_steps} 步 / {run.budget.max_tool_calls} 次工具 / {run.budget.timeout_seconds}s
        </p>
      </aside>

      <ConfirmDialog
        open={confirmCancel}
        title="终止这次分析？"
        description="已产生的事件、工具结果与中间结论会保留，可随时回来查看。"
        confirmLabel="终止分析"
        danger
        onClose={() => setConfirmCancel(false)}
        onConfirm={() => cancel.mutate()}
      />
    </div>
  )
}
