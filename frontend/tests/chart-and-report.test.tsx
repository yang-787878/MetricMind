import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ChartCard } from '@/components/result/ChartCard'
import { ReportView } from '@/components/report/ReportView'
import type { ChartSpec, ReportModel } from '@/types/contract'

function chart(overrides: Partial<ChartSpec> = {}): ChartSpec {
  return {
    chart_id: 'ch_1',
    type: 'line',
    title: '月度销售额趋势',
    subtitle: '口径：求和',
    unit: 'CNY',
    x: { key: 'month', label: '月份', type: 'temporal' },
    y: { key: 'revenue', label: '销售额', type: 'numeric' },
    series: null,
    data: [],
    source: { result_id: 'res_1', tool: 'calculate_metrics', step_id: 's2', row_count: 0, truncated: false },
    notes: [],
    ...overrides,
  }
}

function report(overrides: Partial<ReportModel> = {}): ReportModel {
  return {
    run_id: 'run_1',
    title: '测试报告',
    generated_at: '2026-10-22T10:00:00Z',
    mode: 'demo',
    status: 'partial',
    headline: '9 月销售额环比下降 18.4%',
    kpis: [],
    sections: [],
    charts: [],
    claims: [],
    methodology: [],
    data_quality: [],
    limitations: ['数据缺少营销成本'],
    next_steps: [],
    verification: { coverage: 0.75, supported: 3, unsupported: 1, unverifiable: 0 },
    narrative_source: 'template',
    ...overrides,
  }
}

describe('ChartCard', () => {
  it('无数据时显示空态与原因', () => {
    render(<ChartCard spec={chart()} />)
    expect(screen.getByText('暂无数据')).toBeInTheDocument()
    expect(screen.getByText('结果集没有可绘制的行')).toBeInTheDocument()
  })

  it('截断与来源标注可见', () => {
    render(
      <ChartCard
        spec={chart({
          data: [{ month: '2025-01', revenue: 100 }],
          notes: ['结果共 300 行，图表只展示前 200 行'],
          source: { result_id: 'res_9', tool: 'calculate_metrics', step_id: null, row_count: 300, truncated: true },
        })}
      />,
    )
    expect(screen.getByText('结果已截断')).toBeInTheDocument()
    expect(screen.getByText('res_9')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查看数据' })).toBeInTheDocument()
  })
})

describe('ReportView', () => {
  it('partial 状态显示横幅并列出局限', () => {
    render(<ReportView report={report()} charts={[]} />)
    expect(screen.getByText(/本次为部分结果/)).toBeInTheDocument()
    expect(screen.getByText('9 月销售额环比下降 18.4%')).toBeInTheDocument()
    expect(screen.getByText('数据缺少营销成本')).toBeInTheDocument()
  })

  it('失败状态显示红色说明', () => {
    render(<ReportView report={report({ status: 'failed' })} charts={[]} />)
    expect(screen.getByText('运行失败，以下内容仅来自已完成的步骤。')).toBeInTheDocument()
  })

  it('方法论与数据质量渲染为表格/列表', () => {
    render(
      <ReportView
        report={report({
          methodology: [
            { step_id: 's1', description: '按月汇总', tool: 'calculate_metrics', result_id: 'res_1', sql: null, formula: 'SUM(revenue)' },
          ],
          data_quality: [{ code: 'NULL_VALUES', severity: 'warning', message: 'region 有 120 个空值', column: 'region' }],
        })}
        charts={[]}
      />,
    )
    expect(screen.getByText('SUM(revenue)')).toBeInTheDocument()
    expect(screen.getByText('region 有 120 个空值')).toBeInTheDocument()
  })
})
