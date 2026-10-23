/** 与后端 models/events.py 一一对应的 SSE 事件契约。 */

import type { Budget, RunMode, RunStatus, StepStatus } from './contract'

export type EventType =
  | 'run_created'
  | 'run_started'
  | 'dataset_inspected'
  | 'plan_created'
  | 'step_started'
  | 'tool_call_started'
  | 'tool_call_succeeded'
  | 'tool_call_failed'
  | 'step_completed'
  | 'replan_requested'
  | 'verification_completed'
  | 'report_created'
  | 'budget_warning'
  | 'run_succeeded'
  | 'run_failed'
  | 'run_cancelled'

interface PayloadMap {
  run_created: { run_id: string; mode: RunMode; dataset_id: string }
  run_started: { model: string | null; budget: Budget }
  dataset_inspected: { row_count: number; column_count: number; quality_issue_count: number }
  plan_created: {
    plan_version: number
    objective: string
    steps: { step_id: string; title: string; tool: string }[]
  }
  step_started: { step_id: string; title: string; tool: string }
  tool_call_started: { call_id: string; tool: string; args_summary: Record<string, unknown> }
  tool_call_succeeded: {
    call_id: string
    tool: string
    result_id: string | null
    duration_ms: number
    rows_returned: number | null
    data_preview: unknown
  }
  tool_call_failed: {
    call_id: string
    tool: string
    error: { code: string; message: string }
    duration_ms: number
  }
  step_completed: { step_id: string; status: StepStatus; summary: string }
  replan_requested: { reason: string; replan_count: number; failed_step_id: string | null }
  verification_completed: {
    coverage: number
    supported: number
    unsupported: number
    unverifiable: number
  }
  report_created: { report_id: string; kpi_count: number; chart_count: number; status: RunStatus }
  budget_warning: { kind: 'max_steps' | 'max_tool_calls' | 'max_replans'; used: number; limit: number }
  run_succeeded: { status: RunStatus; finished_at: string | null; duration_ms: number | null; error: null }
  run_failed: {
    status: RunStatus
    finished_at: string | null
    duration_ms: number | null
    error: { code: string; message: string; hint?: string | null } | null
  }
  run_cancelled: { status: RunStatus; finished_at: string | null; duration_ms: number | null; error: null }
}

export interface AppEvent {
  seq: number
  run_id: string
  ts: string
  type: EventType
  step_id: string | null
  payload: Record<string, unknown>
}

export interface EventsResponse {
  events: AppEvent[]
  run_id: string
  status: RunStatus
  is_terminal: boolean
}

export function isAppEvent(value: unknown): value is AppEvent {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Partial<AppEvent>
  return typeof candidate.seq === 'number' && typeof candidate.type === 'string'
}

export function payloadOf<T extends EventType>(event: AppEvent, _type: T): PayloadMap[T] {
  return event.payload as PayloadMap[T]
}

export const TERMINAL_EVENTS: ReadonlySet<string> = new Set([
  'run_succeeded',
  'run_failed',
  'run_cancelled',
])

const LABELS: Record<EventType, string> = {
  run_created: '创建运行',
  run_started: '开始执行',
  dataset_inspected: '检查数据集',
  plan_created: '生成分析计划',
  step_started: '开始步骤',
  tool_call_started: '调用工具',
  tool_call_succeeded: '工具返回',
  tool_call_failed: '工具失败',
  step_completed: '步骤完成',
  replan_requested: '重新规划',
  verification_completed: '数字审计完成',
  report_created: '生成报告',
  budget_warning: '预算告警',
  run_succeeded: '运行结束',
  run_failed: '运行失败',
  run_cancelled: '运行已取消',
}

export function eventLabel(event: AppEvent): string {
  const base = LABELS[event.type] ?? event.type
  const payload = event.payload as Record<string, unknown>
  const tool = typeof payload.tool === 'string' ? payload.tool : ''
  if (event.type === 'tool_call_started' || event.type === 'tool_call_succeeded') {
    return `${base}：${tool}`
  }
  if (event.type === 'step_started' || event.type === 'step_completed') {
    const title = typeof payload.title === 'string' ? payload.title : String(payload.step_id ?? '')
    return `${base}：${title}`
  }
  if (event.type === 'replan_requested') return `${base}（第 ${String(payload.replan_count ?? 1)} 次）`
  if (event.type === 'verification_completed') {
    const coverage = Number(payload.coverage ?? 0)
    return `${base}：覆盖率 ${(coverage * 100).toFixed(0)}%`
  }
  if (event.type === 'budget_warning') {
    return `${base}：${String(payload.kind ?? '')} ${String(payload.used ?? '')}/${String(payload.limit ?? '')}`
  }
  return base
}
