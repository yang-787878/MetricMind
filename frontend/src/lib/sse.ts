/** SSE 解析与降级：优先 EventSource，连续两次错误后由调用方切到轮询。 */

import { api } from '@/lib/api'
import { isAppEvent, type AppEvent, type EventType } from '@/types/events'

export type StreamState = 'connecting' | 'live' | 'polling' | 'closed'

export const EVENT_TYPES: EventType[] = [
  'run_created',
  'run_started',
  'dataset_inspected',
  'plan_created',
  'step_started',
  'tool_call_started',
  'tool_call_succeeded',
  'tool_call_failed',
  'step_completed',
  'replan_requested',
  'verification_completed',
  'report_created',
  'budget_warning',
  'run_succeeded',
  'run_failed',
  'run_cancelled',
]

export function parseEvent(raw: string): AppEvent | null {
  try {
    const payload: unknown = JSON.parse(raw)
    return isAppEvent(payload) ? payload : null
  } catch {
    return null
  }
}

export interface StreamHandlers {
  onEvent: (event: AppEvent) => void
  onState: (state: StreamState) => void
}

/**
 * 打开一条 run 的事件流，返回取消函数。
 * EventSource 自带重连，但对 4xx/断网会无限重试；这里连续两次失败就交回调用方降级。
 */
export function openRunStream(runId: string, afterSeq: number, handlers: StreamHandlers): () => void {
  let closed = false
  let failures = 0
  handlers.onState('connecting')
  const source = new EventSource(api.streamUrl(runId, afterSeq))

  const cleanup = () => {
    closed = true
    source.close()
  }

  source.onopen = () => {
    failures = 0
    handlers.onState('live')
  }

  for (const type of EVENT_TYPES) {
    source.addEventListener(type, (message) => {
      const event = parseEvent((message as MessageEvent<string>).data)
      if (event) handlers.onEvent(event)
    })
  }

  source.onerror = () => {
    if (closed) return
    failures += 1
    if (failures >= 2) {
      cleanup()
      handlers.onState('polling')
      return
    }
    handlers.onState('connecting')
  }

  return () => {
    closed = true
    source.close()
    handlers.onState('closed')
  }
}
