import { Calculator, ClipboardList, FileBarChart, ScanSearch, TableProperties } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'

import { DatasetDropzone } from '@/components/dataset/DatasetDropzone'
import { QualityBadge } from '@/components/dataset/DatasetCard'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { InlineAlert } from '@/components/feedback/InlineAlert'
import { SkeletonLines } from '@/components/feedback/Skeleton'
import { ModeSelect } from '@/components/app/ModeSelect'
import { QuestionComposer } from '@/components/app/QuestionComposer'
import { StatusPill } from '@/components/ui/status-pill'
import { Button } from '@/components/ui/button'
import { useConfig } from '@/hooks/useSystem'
import { useCreateRun, useDatasets, useLoadSample, useRuns } from '@/hooks/useRuns'
import { ApiError, api } from '@/lib/api'
import { formatCount, formatDuration, formatRelativeTime } from '@/lib/format'
import { useAppStore } from '@/store/app'
import type { DatasetDetail, RequestedMode } from '@/types/contract'

const STEPS = [
  { icon: ScanSearch, title: '检查数据', detail: '推断字段语义、统计缺失与异常，先给出数据质量结论。' },
  { icon: ClipboardList, title: '制定计划', detail: '先产出可读的分析计划：步骤、工具、预期输出与验证方式。' },
  { icon: Calculator, title: '受控计算', detail: '所有数字由 DuckDB / pandas 工具算出，模型只提供结构化参数。' },
  { icon: FileBarChart, title: '验证并生成报告', detail: '逐条核对结论中的数字，无法支撑的推断被降级或删除。' },
]

export function HomePage() {
  const { data: config, isError: configError, error: configErrorValue } = useConfig()
  const { data: datasets } = useDatasets()
  const {
    data: runs,
    isPending: runsPending,
    isError: runsError,
    error: runsErrorValue,
    refetch: refetchRuns,
  } = useRuns(8)
  const selectedId = useAppStore((state) => state.selectedDatasetId)
  const selectDataset = useAppStore((state) => state.selectDataset)
  const loadSample = useLoadSample()
  const createRun = useCreateRun()
  const navigate = useNavigate()

  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<RequestedMode>('auto')
  const [liveBlocked, setLiveBlocked] = useState(false)
  const [lastQuestion, setLastQuestion] = useState('')
  const [loadingSample, setLoadingSample] = useState<string | null>(null)

  const { data: selected } = useQuery({
    queryKey: ['dataset', selectedId],
    queryFn: () => api.getDataset(selectedId as string),
    enabled: Boolean(selectedId),
  })

  useEffect(() => {
    if (!selectedId && datasets && datasets.items.length > 0) {
      selectDataset(datasets.items[0]?.dataset_id ?? null)
    }
  }, [datasets, selectedId, selectDataset])

  const examples = (config?.samples ?? []).flatMap((sample) => sample.recommended_questions).slice(0, 3)

  const submit = async (question: string, overrideMode?: RequestedMode) => {
    const requested = overrideMode ?? mode
    setError(null)
    setLiveBlocked(false)
    setLastQuestion(question)
    // 直接读 store 的最新值：effect 里自动选中第一个数据集可能还没触发重渲染
    const targetId =
      useAppStore.getState().selectedDatasetId ?? datasets?.items[0]?.dataset_id ?? null
    if (!targetId) {
      setError('请先在右侧上传一份数据，或点击下方示例数据')
      return
    }
    if (targetId !== selectedId) selectDataset(targetId)
    try {
      const created = await createRun.mutateAsync({
        dataset_id: targetId,
        question,
        mode: requested,
      })
      navigate(`/workspace/${created.run_id}`)
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === 'LLM_NOT_CONFIGURED') {
        setLiveBlocked(true)
        setError(caught.message)
        return
      }
      setError(caught instanceof ApiError ? caught.message : '创建分析失败，请稍后重试')
    }
  }

  const useSample = async (key: string) => {
    setError(null)
    setLoadingSample(key)
    try {
      const dataset = (await loadSample.mutateAsync(key)) as DatasetDetail
      selectDataset(dataset.dataset_id)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : '载入示例数据失败')
    } finally {
      setLoadingSample(null)
    }
  }

  return (
    <div className="space-y-8">
      <section className="grid items-start gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div>
          <h1 className="text-h1 font-semibold tracking-tight text-ink">用自然语言完成一次严谨的数据分析</h1>
          <p className="mt-2 max-w-[52ch] text-body-lg text-secondary">
            先看计划，再看计算：每个数字都能回溯到一次真实的工具调用结果。
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-2 text-caption">
            <span className="text-muted">当前数据集：</span>
            {selected ? (
              <>
                <span className="font-medium text-ink">{selected.name}</span>
                <span className="tabular text-muted">
                  {formatCount(selected.row_count)} 行 · {selected.column_count} 列
                </span>
                <QualityBadge quality={selected.quality} />
              </>
            ) : (
              <span className="text-muted">尚未选择（右侧上传或使用示例数据）</span>
            )}
          </div>

          <QuestionComposer
            examples={examples.length > 0 ? examples : ['为什么 9 月销售额下降了？']}
            onSubmit={(question) => void submit(question)}
            disabled={createRun.isPending}
            disabledReason={createRun.isPending ? '正在创建分析…' : undefined}
          />

          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
            <ModeSelect
              value={mode}
              onChange={setMode}
              disabled={createRun.isPending}
              liveAvailable={config?.llm_mode === 'live'}
            />
            <span className="text-micro text-muted">
              {mode === 'live'
                ? 'Live 需要 OPENAI_API_KEY；未配置会提示切换 Demo'
                : mode === 'demo'
                  ? 'Demo 不调用模型，数字仍来自工具执行'
                  : '自动：有 Key 用 Live，否则 Demo'}
            </span>
          </div>

          {mode === 'live' && config?.llm_mode === 'demo' && !liveBlocked ? (
            <InlineAlert
              tone="warning"
              className="mt-2"
              action={
                <Button size="sm" variant="secondary" onClick={() => setMode('demo')}>
                  改用 Demo
                </Button>
              }
            >
              当前后端未配置 API Key（/api/config 返回 demo 模式），现在用 Live 提交会返回 409。
              在 .env 配置 OPENAI_API_KEY 并重启后端即可启用 Live。
            </InlineAlert>
          ) : null}

          <div className="mt-3 flex flex-wrap items-center gap-2 text-caption text-secondary">
            <span className="text-muted">示例数据：</span>
            {(config?.samples ?? []).length > 0 ? (
              (config?.samples ?? []).map((sample) => (
                <button
                  key={sample.key}
                  type="button"
                  onClick={() => void useSample(sample.key)}
                  disabled={loadingSample !== null}
                  className="focus-ring rounded-pill border border-border bg-surface px-2.5 py-1 text-caption text-secondary transition-colors hover:border-brand-500 hover:bg-brand-50 hover:text-brand-600 disabled:opacity-60"
                  title={sample.description}
                >
                  {loadingSample === sample.key ? '载入中…' : sample.name}
                </button>
              ))
            ) : (
              <span className="text-muted">示例数据尚未生成</span>
            )}
          </div>

          {liveBlocked ? (
            <InlineAlert
              tone="danger"
              className="mt-4"
              action={
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setMode('demo')
                    void submit(lastQuestion, 'demo')
                  }}
                >
                  改用 Demo 重试
                </Button>
              }
            >
              未配置大模型 API Key，无法以 live 模式运行。可以在 .env 配置 Key，或直接改用 Demo 模式。
            </InlineAlert>
          ) : error ? (
            <InlineAlert tone="danger" className="mt-4">
              {error}
            </InlineAlert>
          ) : null}
          {configError ? (
            <InlineAlert tone="danger" title="无法读取后端配置" className="mt-4">
              {configErrorValue instanceof Error ? configErrorValue.message : '请确认后端已在 127.0.0.1:8000 启动'}
            </InlineAlert>
          ) : null}
          {createRun.isError && !liveBlocked ? (
            <ErrorState compact error={createRun.error} title="创建分析失败" />
          ) : null}
        </div>

        <DatasetDropzone maxUploadMb={config?.limits.max_upload_mb} onUploaded={(dataset) => selectDataset(dataset.dataset_id)} />
      </section>

      <section aria-labelledby="recent-runs">
        <div className="mb-3 flex items-end justify-between">
          <div>
            <h2 id="recent-runs" className="text-h4 font-semibold text-ink">
              最近分析
            </h2>
            <p className="mt-0.5 text-caption text-secondary">按创建时间倒序，最多显示 8 条</p>
          </div>
          <span className="text-micro text-muted">共 {runs?.total ?? 0} 条</span>
        </div>

        <div className="card overflow-hidden">
          {runsError ? (
            <div className="p-4">
              <ErrorState error={runsErrorValue} title="最近分析加载失败" onRetry={() => void refetchRuns()} />
            </div>
          ) : runsPending ? (
            <div className="p-4">
              <SkeletonLines rows={3} />
            </div>
          ) : runs && runs.items.length > 0 ? (
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-border bg-surface-2 text-micro uppercase tracking-wide text-muted">
                  <th className="px-4 py-2 font-medium">问题</th>
                  <th className="px-4 py-2 font-medium">数据集</th>
                  <th className="px-4 py-2 font-medium">状态</th>
                  <th className="px-4 py-2 font-medium">模式</th>
                  <th className="px-4 py-2 font-medium">耗时</th>
                  <th className="px-4 py-2 font-medium">创建时间</th>
                  <th className="px-4 py-2 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {runs.items.map((run) => (
                  <tr key={run.run_id} className="border-b border-border/60 last:border-0 hover:bg-surface-2">
                    <td className="max-w-[320px] px-4 py-2">
                      <Link
                        to={`/workspace/${run.run_id}`}
                        className="focus-ring line-clamp-2 rounded-sm text-caption text-ink hover:text-brand-600"
                        title={run.question}
                      >
                        {run.question}
                      </Link>
                    </td>
                    <td className="px-4 py-2 text-caption text-secondary">{run.dataset_name ?? '—'}</td>
                    <td className="px-4 py-2">
                      <StatusPill status={run.status} />
                    </td>
                    <td className="px-4 py-2 text-caption text-secondary">{run.mode === 'live' ? 'Live' : 'Demo'}</td>
                    <td className="tabular px-4 py-2 text-caption text-secondary">{formatDuration(run.duration_ms)}</td>
                    <td className="px-4 py-2 text-caption text-muted">{formatRelativeTime(run.created_at)}</td>
                    <td className="px-4 py-2">
                      <Link
                        to={run.status === 'succeeded' || run.status === 'partial' ? `/runs/${run.run_id}/report` : `/workspace/${run.run_id}`}
                        className="focus-ring rounded-sm text-caption text-brand-600 hover:text-brand-700"
                      >
                        {run.status === 'succeeded' || run.status === 'partial' ? '查看报告' : '查看进度'}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="p-4">
              <EmptyState
                compact
                icon={<TableProperties size={20} />}
                title="还没有分析记录"
                description="上传一份数据并提一个问题，Agent 会先给计划、再逐步执行，结果与证据都会留在这里。"
              />
            </div>
          )}
        </div>
      </section>

      <section aria-labelledby="how-it-works" className="border-t border-border pt-6">
        <h2 id="how-it-works" className="mb-4 text-h4 font-semibold text-ink">
          工作方式
        </h2>
        <ol className="grid gap-0 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step, index) => (
            <li
              key={step.title}
              className="flex gap-3 px-0 py-3 lg:px-4 lg:first:pl-0 lg:last:pr-0 [&:not(:first-child)]:lg:border-l [&:not(:first-child)]:lg:border-border"
            >
              <span className="mt-0.5 text-muted" aria-hidden>
                <step.icon size={16} />
              </span>
              <div>
                <p className="text-body-lg font-medium text-ink">
                  <span className="mr-1.5 font-mono text-micro text-muted">{index + 1}</span>
                  {step.title}
                </p>
                <p className="mt-0.5 text-caption leading-[18px] text-secondary">{step.detail}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
