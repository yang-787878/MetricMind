import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { PlanTimeline } from '@/components/agent/PlanTimeline'
import { ToolCallCard } from '@/components/agent/ToolCallCard'
import { DataTable } from '@/components/result/DataTable'
import { KpiCard } from '@/components/result/KpiCard'
import { ErrorState } from '@/components/feedback/ErrorState'
import { ModeBadge } from '@/components/app/ModeBadge'
import { ConfirmDialog } from '@/components/ui/dialog'
import { ApiError } from '@/lib/api'
import type { StepRecord, ToolCallRecord } from '@/types/contract'

function step(overrides: Partial<StepRecord>): StepRecord {
  return {
    step_id: 's1',
    title: '计算总收入',
    intent: '确认规模',
    tool: 'calculate_metrics',
    tool_args_hint: {},
    status: 'pending',
    expected_output: '总收入',
    validation: '与行数口径一致',
    summary: '',
    tool_calls: [],
    started_at: null,
    finished_at: null,
    duration_ms: null,
    error: null,
    ...overrides,
  }
}

describe('PlanTimeline', () => {
  it('渲染五种步骤状态', () => {
    const steps: StepRecord[] = [
      step({ step_id: 's1', status: 'succeeded', title: '已完成步骤' }),
      step({ step_id: 's2', status: 'running', title: '执行中步骤' }),
      step({ step_id: 's3', status: 'failed', title: '失败步骤' }),
      step({ step_id: 's4', status: 'skipped', title: '跳过步骤' }),
      step({ step_id: 's5', status: 'pending', title: '待执行步骤' }),
    ]
    render(<PlanTimeline steps={steps} plan={null} />)
    expect(screen.getByText('已完成步骤')).toBeInTheDocument()
    expect(screen.getByText('执行中步骤')).toBeInTheDocument()
    expect(screen.getAllByTitle('完成').length).toBeGreaterThan(0)
    expect(screen.getAllByTitle('失败').length).toBeGreaterThan(0)
    expect(screen.getAllByTitle('已跳过').length).toBeGreaterThan(0)
    expect(screen.getAllByTitle('待执行').length).toBeGreaterThan(0)
    // 当前 running 步骤默认展开，能看到意图
    expect(screen.getByText('确认规模')).toBeInTheDocument()
  })

  it('空计划给出引导', () => {
    render(<PlanTimeline steps={[]} plan={null} />)
    expect(screen.getByText('还没有计划')).toBeInTheDocument()
  })

  it('重规划位置有标注', () => {
    render(
      <PlanTimeline
        steps={[step({ step_id: 's1', status: 'succeeded' }), step({ step_id: 's2', status: 'pending' })]}
        plan={null}
        replans={[{ failedStepId: 's1', count: 1 }]}
      />,
    )
    expect(screen.getByText('已重新规划（第 1 次）')).toBeInTheDocument()
  })
})

describe('ToolCallCard', () => {
  it('错误态展示 code、message 与 hint', async () => {
    const record: ToolCallRecord = {
      call_id: 'call_1',
      step_id: 's1',
      tool: 'query_data',
      status: 'rejected',
      arguments: { sql: 'DROP TABLE data' },
      result_id: null,
      duration_ms: 12,
      result: null,
      error: { code: 'SQL_REJECTED', message: '只允许只读查询', hint: '请改写为 SELECT', retryable: false, fields: null },
      warnings: [],
      created_at: new Date().toISOString(),
    }
    render(<ToolCallCard record={record} defaultOpen />)
    await userEvent.click(screen.getByRole('tab', { name: '结果' }))
    expect(screen.getByText('SQL_REJECTED')).toBeInTheDocument()
    expect(screen.getByText('只允许只读查询')).toBeInTheDocument()
    expect(screen.getByText('请改写为 SELECT')).toBeInTheDocument()
  })

  it('参数 Tab 展示 JSON', () => {
    const record: ToolCallRecord = {
      call_id: 'call_2',
      step_id: 's1',
      tool: 'calculate_metrics',
      status: 'ok',
      arguments: { metrics: [{ name: 'total' }] },
      result_id: 'res_1',
      duration_ms: 8,
      result: null,
      error: null,
      warnings: [],
      created_at: new Date().toISOString(),
    }
    render(<ToolCallCard record={record} defaultOpen />)
    expect(screen.getByText(/total/)).toBeInTheDocument()
  })
})

describe('ConfirmDialog', () => {
  it('展示标题与说明，确认与取消分别触发回调', async () => {
    const onConfirm = vi.fn()
    const onClose = vi.fn()
    render(
      <ConfirmDialog
        open
        title="终止这次分析？"
        description="已产生的结果会保留"
        confirmLabel="终止分析"
        danger
        onConfirm={onConfirm}
        onClose={onClose}
      />,
    )
    expect(screen.getByRole('dialog', { name: '终止这次分析？' })).toBeInTheDocument()
    expect(screen.getByText('已产生的结果会保留')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '终止分析' }))
    expect(onConfirm).toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('Esc 关闭弹层', async () => {
    const onClose = vi.fn()
    render(
      <ConfirmDialog open title="关闭我" description="x" onConfirm={() => {}} onClose={onClose} />,
    )
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })
})

describe('KpiCard / DataTable / ModeBadge / ErrorState', () => {
  it('KPI 展示格式化数值与单位', () => {
    render(
      <KpiCard
        kpi={{
          label: '9 月销售额',
          value: 1042180,
          unit: 'CNY',
          delta: -0.184,
          delta_label: '环比',
          evidence_ids: ['res_1'],
          display_value: '¥104.2 万',
        }}
      />,
    )
    expect(screen.getByText('¥104.2 万')).toBeInTheDocument()
    expect(screen.getByText('人民币')).toBeInTheDocument()
  })

  it('DataTable 把空值渲染为 ∅', () => {
    render(
      <DataTable
        columns={[
          { key: 'channel', label: '渠道' },
          { key: 'revenue', label: '收入', align: 'right' },
        ]}
        rows={[{ channel: 'DTC', revenue: null }]}
      />,
    )
    expect(screen.getByText('DTC')).toBeInTheDocument()
    expect(screen.getByText('∅')).toBeInTheDocument()
  })

  it('ModeBadge 区分 live/demo', () => {
    const { rerender } = render(<ModeBadge mode="live" />)
    expect(screen.getByText('Live model')).toBeInTheDocument()
    rerender(<ModeBadge mode="demo" />)
    expect(screen.getByText('Demo mode')).toBeInTheDocument()
  })

  it('ErrorState 渲染错误码、人话与重试', async () => {
    const onRetry = vi.fn()
    const error = new ApiError(503, {
      code: 'LLM_UNAVAILABLE',
      message: '模型暂时不可用',
      details: { hint: '可切换到 Demo 模式' },
      request_id: 'req_1',
    })
    render(<ErrorState error={error} onRetry={onRetry} />)
    expect(screen.getByText('LLM_UNAVAILABLE')).toBeInTheDocument()
    expect(screen.getByText('模型暂时不可用')).toBeInTheDocument()
    expect(screen.getByText('可切换到 Demo 模式')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /重试/ }))
    expect(onRetry).toHaveBeenCalled()
  })
})
