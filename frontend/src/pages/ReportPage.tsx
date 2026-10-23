import { ArrowLeft } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'

import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { InlineAlert } from '@/components/feedback/InlineAlert'
import { SkeletonBlock, SkeletonLines } from '@/components/feedback/Skeleton'
import { ExportMenu } from '@/components/report/ExportMenu'
import { ReportView } from '@/components/report/ReportView'
import { Button } from '@/components/ui/button'
import { useRun, TERMINAL_STATUSES } from '@/hooks/useRuns'
import { api } from '@/lib/api'
import { chartsFromRun } from '@/lib/charts'
import { formatDateTime } from '@/lib/format'

export function ReportPage() {
  const { runId } = useParams()
  const { data: run, isPending, error, refetch } = useRun(runId)
  const terminal = Boolean(run && TERMINAL_STATUSES.has(run.status))

  const reportQuery = useQuery({
    queryKey: ['report', runId],
    queryFn: () => api.getReport(runId as string),
    enabled: Boolean(runId) && terminal,
    retry: false,
  })

  if (!runId) {
    return (
      <EmptyState
        icon={<ArrowLeft size={20} />}
        title="没有可查看的报告"
        description="完成一次分析后，报告会在这里以阅读版式呈现，并可导出 HTML / Markdown。"
        action={
          <Link to="/" className="focus-ring rounded-md border border-border-strong bg-surface px-3 py-1.5 text-caption text-ink hover:bg-surface-3">
            返回工作台
          </Link>
        }
      />
    )
  }

  const breadcrumb = (
    <nav className="mb-5 flex items-center gap-1.5 text-caption text-muted" aria-label="面包屑">
      <Link to="/" className="focus-ring rounded-sm hover:text-ink">
        工作台
      </Link>
      <span aria-hidden>/</span>
      <Link to={`/workspace/${runId}`} className="focus-ring rounded-sm hover:text-ink">
        分析过程
      </Link>
      <span aria-hidden>/</span>
      <span className="text-secondary">分析报告</span>
    </nav>
  )

  return (
    <div className="mx-auto w-full max-w-prose">
      {breadcrumb}

      {isPending ? (
        <div className="space-y-4">
          <SkeletonBlock className="h-8 w-2/3" />
          <SkeletonBlock className="h-4 w-1/2" />
          <div className="card p-4">
            <SkeletonLines rows={5} />
          </div>
        </div>
      ) : error || !run ? (
        <ErrorState error={error} title="报告加载失败" onRetry={() => void refetch()} />
      ) : !terminal ? (
        <div className="space-y-3">
          <h1 className="text-h2 font-semibold tracking-tight text-ink">报告尚未生成</h1>
          <InlineAlert tone="warning" title="分析仍在进行">
            当前状态：{run.status}。完成后本页会自动刷新，你也可以先查看执行过程。
          </InlineAlert>
          <Link
            to={`/workspace/${runId}`}
            className="focus-ring inline-flex h-9 items-center rounded-md bg-brand-600 px-4 text-body-lg font-medium text-ink-inverse hover:bg-brand-700"
          >
            查看执行过程
          </Link>
        </div>
      ) : reportQuery.isPending ? (
        <div className="card p-4">
          <SkeletonLines rows={6} />
        </div>
      ) : reportQuery.error ? (
        <ErrorState error={reportQuery.error} title="报告不可用" onRetry={() => void reportQuery.refetch()} />
      ) : reportQuery.data ? (
        <ReportView
          report={reportQuery.data}
          charts={chartsFromRun(run)}
          actions={
            <div className="flex items-center gap-2">
              <ExportMenu runId={runId} onError={(message) => window.alert(message)} />
              <Link
                to={`/workspace/${runId}`}
                className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-md border border-border-strong bg-surface px-3 text-caption text-ink hover:bg-surface-3"
              >
                <ArrowLeft size={14} aria-hidden />
                返回工作台
              </Link>
            </div>
          }
        />
      ) : (
        <EmptyState icon={<ArrowLeft size={20} />} title="报告尚未生成" description="请稍后重试或查看执行过程。" />
      )}

      {run ? (
        <p className="mt-6 border-t border-border pt-3 text-micro text-muted">
          运行 {run.run_id} · 创建于 {formatDateTime(run.created_at)} · 状态 {run.status}
        </p>
      ) : null}

      <div className="mt-3">
        <Button size="sm" variant="ghost" onClick={() => window.print()}>
          打印 / 另存为 PDF
        </Button>
      </div>
    </div>
  )
}
