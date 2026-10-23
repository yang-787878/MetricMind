import { AlertCircle, BadgeCheck, CheckCircle2 } from 'lucide-react'
import type { ReactNode } from 'react'

import { ChartCard } from '@/components/result/ChartCard'
import { ClaimEvidenceList } from '@/components/result/ClaimEvidenceList'
import { DataTable, type Column } from '@/components/result/DataTable'
import { KpiCard } from '@/components/result/KpiCard'
import { LimitationList } from '@/components/report/LimitationList'
import { formatDateTime, formatPercent } from '@/lib/format'
import type { ChartSpec, ReportModel } from '@/types/contract'

export function ReportView({
  report,
  charts,
  actions,
  compact = false,
}: {
  report: ReportModel
  charts: ChartSpec[]
  actions?: ReactNode
  compact?: boolean
}) {
  const methodologyColumns: Column[] = [
    { key: 'step_id', label: '步骤' },
    { key: 'description', label: '说明' },
    { key: 'tool', label: '工具' },
    { key: 'caliber', label: '口径 / SQL' },
  ]

  return (
    <article className={compact ? 'space-y-5' : 'space-y-7'}>
      <header className="space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className={compact ? 'text-h3 font-semibold text-ink' : 'text-h2 font-semibold tracking-tight text-ink'}>
              {report.title}
            </h1>
            <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-micro text-muted">
              <span className={report.mode === 'live' ? 'text-success-600' : 'text-warning-600'}>
                {report.mode === 'live' ? 'Live model' : 'Demo mode'}
              </span>
              <span>{formatDateTime(report.generated_at)}</span>
              {report.verification ? (
                <span>数字审计覆盖 {formatPercent(report.verification.coverage, 0)}</span>
              ) : null}
              <span>状态 {report.status}</span>
            </p>
          </div>
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </div>

        {report.status === 'partial' ? (
          <div className="flex items-start gap-2 rounded-md border border-warning-600/30 bg-warning-50 px-3 py-2 text-caption text-warning-600">
            <AlertCircle size={15} className="mt-0.5 shrink-0" aria-hidden />
            <span>
              本次为部分结果：{report.claims.filter((claim) => claim.status !== 'supported').length} 条结论未通过数字核验，
              已在局限性中标注。
            </span>
          </div>
        ) : null}
        {report.status === 'failed' ? (
          <div className="flex items-start gap-2 rounded-md border border-danger-600/30 bg-danger-50 px-3 py-2 text-caption text-danger-600">
            <AlertCircle size={15} className="mt-0.5 shrink-0" aria-hidden />
            <span>运行失败，以下内容仅来自已完成的步骤。</span>
          </div>
        ) : null}

        <p className="text-body-lg leading-[26px] text-ink">{report.headline}</p>
      </header>

      {report.kpis.length > 0 ? (
        <section aria-label="关键指标" className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          {report.kpis.map((kpi) => (
            <KpiCard key={`${kpi.label}-${kpi.evidence_ids.join()}`} kpi={kpi} />
          ))}
        </section>
      ) : null}

      {charts.length > 0 ? (
        <section
          aria-label="图表"
          className={compact || charts.length === 1 ? 'space-y-4' : 'grid gap-4 lg:grid-cols-2'}
        >
          {charts.map((chart) => (
            <ChartCard key={chart.chart_id} spec={chart} />
          ))}
        </section>
      ) : null}

      {report.sections.length > 0 ? (
        <section aria-labelledby="findings">
          <h2 id="findings" className="mb-2 text-h4 font-semibold text-ink">
            结论
          </h2>
          <ol className="space-y-3">
            {report.sections.map((section, index) => (
              <li key={section.id} className="card p-3">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 font-mono text-micro text-muted">{index + 1}</span>
                  <div className="min-w-0">
                    <h3 className="text-body-lg font-semibold text-ink">
                      {section.heading}
                      {section.degraded ? (
                        <span className="ml-2 rounded-sm bg-warning-50 px-1.5 text-micro text-warning-600">
                          证据不足，已降级
                        </span>
                      ) : null}
                    </h3>
                    <p className="mt-1 text-body text-secondary">{section.body}</p>
                    {section.evidence_ids.length > 0 ? (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {section.evidence_ids.map((id) => (
                          <span key={id} className="rounded-sm bg-surface-3 px-1.5 font-mono text-micro text-secondary">
                            {id}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <section aria-labelledby="claims">
        <h2 id="claims" className="mb-2 flex items-center gap-1.5 text-h4 font-semibold text-ink">
          数字核验
          <BadgeCheck size={15} className="text-teal-600" aria-hidden />
        </h2>
        <ClaimEvidenceList claims={report.claims} />
      </section>

      {report.methodology.length > 0 ? (
        <section aria-labelledby="methodology">
          <h2 id="methodology" className="mb-2 text-h4 font-semibold text-ink">
            方法论与口径
          </h2>
          <DataTable
            columns={methodologyColumns}
            rows={report.methodology.map((item) => ({
              step_id: item.step_id,
              description: item.description,
              tool: item.tool,
              caliber: item.formula ?? item.sql ?? '—',
            }))}
            maxHeight={320}
          />
        </section>
      ) : null}

      {report.data_quality.length > 0 ? (
        <section aria-labelledby="quality">
          <h2 id="quality" className="mb-2 text-h4 font-semibold text-ink">
            数据质量
          </h2>
          <ul className="card space-y-1.5 p-3">
            {report.data_quality.map((note, index) => (
              <li key={`${note.code}-${index}`} className="flex items-start gap-2 text-caption">
                <span
                  className={
                    note.severity === 'error'
                      ? 'mt-1.5 size-1.5 shrink-0 rounded-full bg-danger-600'
                      : note.severity === 'warning'
                        ? 'mt-1.5 size-1.5 shrink-0 rounded-full bg-warning-600'
                        : 'mt-1.5 size-1.5 shrink-0 rounded-full bg-brand-600'
                  }
                  aria-hidden
                />
                <span className="font-mono text-micro text-muted">{note.code}</span>
                <span className="min-w-0 flex-1 text-secondary">{note.message}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section aria-labelledby="limitations">
        <h2 id="limitations" className="mb-2 text-h4 font-semibold text-ink">
          局限性
        </h2>
        <LimitationList limitations={report.limitations} />
      </section>

      {report.next_steps.length > 0 ? (
        <section aria-labelledby="next-steps">
          <h2 id="next-steps" className="mb-2 text-h4 font-semibold text-ink">
            后续建议
          </h2>
          <ul className="space-y-1 text-body text-secondary">
            {report.next_steps.map((item) => (
              <li key={item} className="flex gap-2">
                <CheckCircle2 size={14} className="mt-1 shrink-0 text-muted" aria-hidden />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <footer className="border-t border-border pt-3 text-micro text-muted">
        由 MetricMind 生成 · 模式 {report.mode} · 所有数值来自工具执行结果，可回溯至 result_id
      </footer>
    </article>
  )
}
