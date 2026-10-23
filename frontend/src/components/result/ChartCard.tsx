import { ChartColumn, ExternalLink } from 'lucide-react'
import { useMemo, useState } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { EmptyState } from '@/components/feedback/EmptyState'
import { DataTable, type Column } from '@/components/result/DataTable'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { formatAxis, formatValue } from '@/lib/format'
import type { ChartSpec } from '@/types/contract'

const COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)']

function useChartRows(spec: ChartSpec) {
  return useMemo(() => {
    const series = spec.series
    if (!series) return spec.data
    const pivot = new Map<string, Record<string, unknown>>()
    for (const row of spec.data) {
      const key = String(row[spec.x.key] ?? '')
      const bucket = pivot.get(key) ?? { [spec.x.key]: row[spec.x.key] }
      bucket[String(row[series.key] ?? '')] = row[spec.y.key]
      pivot.set(key, bucket)
    }
    return Array.from(pivot.values())
  }, [spec])
}

const TOOLTIP_STYLE = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  fontSize: 12,
  boxShadow: 'var(--shadow-md)',
  padding: '6px 8px',
} as const

export function ChartCard({ spec }: { spec: ChartSpec }) {
  const [open, setOpen] = useState(false)
  const rows = useChartRows(spec)
  const seriesKeys = useMemo(() => {
    const series = spec.series
    if (!series) return [spec.y.key]
    return Array.from(new Set(spec.data.map((row) => String(row[series.key] ?? ''))))
  }, [spec])

  const axisProps = {
    tick: { fontSize: 11, fill: 'var(--text-muted)' },
    stroke: 'var(--grid)',
  } as const

  const tooltip = (
    <Tooltip
      contentStyle={TOOLTIP_STYLE}
      labelStyle={{ color: 'var(--text-secondary)' }}
      formatter={(value: number | string) => [formatValue(Number(value), spec.unit), spec.y.label]}
    />
  )

  const chart = (() => {
    if (spec.type === 'line') {
      return (
        <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey={spec.x.key} {...axisProps} />
          <YAxis {...axisProps} width={64} tickFormatter={(value) => formatAxis(Number(value), spec.unit)} />
          {tooltip}
          {seriesKeys.map((key, index) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              stroke={COLORS[index % COLORS.length]}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      )
    }
    if (spec.type === 'area') {
      return (
        <AreaChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey={spec.x.key} {...axisProps} />
          <YAxis {...axisProps} width={64} tickFormatter={(value) => formatAxis(Number(value), spec.unit)} />
          {tooltip}
          {seriesKeys.map((key, index) => (
            <Area
              key={key}
              dataKey={key}
              stroke={COLORS[index % COLORS.length]}
              fill={COLORS[index % COLORS.length]}
              fillOpacity={0.14}
              strokeWidth={2}
              isAnimationActive={false}
            />
          ))}
        </AreaChart>
      )
    }
    if (spec.type === 'scatter') {
      return (
        <ScatterChart margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" />
          <XAxis dataKey={spec.x.key} {...axisProps} />
          <YAxis {...axisProps} width={64} tickFormatter={(value) => formatAxis(Number(value), spec.unit)} />
          {tooltip}
          {seriesKeys.map((key, index) => (
            <Scatter key={key} data={rows} dataKey={key} fill={COLORS[index % COLORS.length]} isAnimationActive={false} />
          ))}
        </ScatterChart>
      )
    }
    return (
      <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={spec.x.key} {...axisProps} />
        <YAxis {...axisProps} width={64} tickFormatter={(value) => formatAxis(Number(value), spec.unit)} />
        {tooltip}
        {spec.series ? <Legend wrapperStyle={{ fontSize: 11 }} /> : null}
        {seriesKeys.map((key, index) => (
          <Bar
            key={key}
            dataKey={key}
            stackId={spec.type === 'stacked_bar' ? 'stack' : undefined}
            fill={COLORS[index % COLORS.length]}
            isAnimationActive={false}
            radius={[2, 2, 0, 0]}
          />
        ))}
      </BarChart>
    )
  })()

  const columns: Column[] = [
    { key: spec.x.key, label: spec.x.label },
    ...(spec.series ? [{ key: spec.series.key, label: spec.series.label }] : []),
    { key: spec.y.key, label: spec.y.label, align: 'right' as const },
  ]

  return (
    <section className="card flex flex-col p-3" aria-label={spec.title}>
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-body-lg font-semibold text-ink" title={spec.title}>
            {spec.title}
          </h3>
          {spec.subtitle ? <p className="truncate text-micro text-muted" title={spec.subtitle}>{spec.subtitle}</p> : null}
        </div>
        <Button size="sm" variant="ghost" onClick={() => setOpen(true)} title="查看图表底层数据">
          查看数据
        </Button>
      </header>

      <div className="mt-2 h-[260px] w-full overflow-hidden">
        {rows.length === 0 ? (
          <EmptyState compact icon={<ChartColumn size={18} />} title="暂无数据" description="结果集没有可绘制的行" />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            {chart}
          </ResponsiveContainer>
        )}
      </div>

      <footer className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border pt-2 text-micro text-muted">
        <span className="inline-flex items-center gap-1 font-mono">
          <ExternalLink size={11} aria-hidden />
          {spec.source.result_id}
        </span>
        <span>{spec.source.tool}</span>
        <span>{spec.source.row_count} 行</span>
        {spec.source.truncated ? <span className="text-warning-600">结果已截断</span> : null}
        {spec.notes.map((note) => (
          <span key={note} className="text-warning-600">
            {note}
          </span>
        ))}
      </footer>

      <Dialog open={open} title={`${spec.title} · 底层数据`} onClose={() => setOpen(false)} size="lg">
        <p className="mb-2 text-caption text-secondary">
          数据来自结果集 <span className="font-mono text-ink">{spec.source.result_id}</span>，与图表完全一致。
        </p>
        <DataTable columns={columns} rows={spec.data} maxHeight={420} />
      </Dialog>
    </section>
  )
}

