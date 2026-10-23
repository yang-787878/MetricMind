import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useRunStream } from '@/hooks/useRunStream'
import type { AppEvent } from '@/types/events'

class FakeEventSource {
  static instances: FakeEventSource[] = []
  listeners = new Map<string, ((event: { data: string }) => void)[]>()
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  closed = false

  constructor(public url: string) {
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, handler: (event: { data: string }) => void) {
    const list = this.listeners.get(type) ?? []
    list.push(handler)
    this.listeners.set(type, list)
  }

  emit(type: string, payload: unknown) {
    for (const handler of this.listeners.get(type) ?? []) handler({ data: JSON.stringify(payload) })
  }

  close() {
    this.closed = true
  }
}

function event(seq: number, type: AppEvent['type'], payload: Record<string, unknown> = {}): AppEvent {
  return {
    seq,
    run_id: 'run_1',
    ts: '2026-10-22T10:00:00Z',
    type,
    step_id: null,
    payload,
  }
}

describe('useRunStream', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('合并事件并按 seq 去重', async () => {
    const { result } = renderHook(() => useRunStream('run_1'))

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    const source = FakeEventSource.instances[0]
    if (!source) throw new Error('EventSource 未创建')

    act(() => {
      source.onopen?.()
      source.emit('run_created', event(1, 'run_created'))
      source.emit('plan_created', event(2, 'plan_created', { plan_version: 1, objective: '目标', steps: [] }))
      // 重连后重复推送 seq=2，必须被丢弃
      source.emit('plan_created', event(2, 'plan_created', { plan_version: 1, objective: '目标', steps: [] }))
      source.emit('step_started', event(3, 'step_started', { step_id: 's1', title: '步骤', tool: 'calculate_metrics' }))
    })

    expect(result.current.events.map((item) => item.seq)).toEqual([1, 2, 3])
    expect(result.current.state).toBe('live')
  })

  it('连续两次错误后降级为轮询', async () => {
    const { result } = renderHook(() => useRunStream('run_1'))
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    const source = FakeEventSource.instances[0]
    if (!source) throw new Error('EventSource 未创建')

    act(() => {
      source.onopen?.()
      source.onerror?.()
      source.onerror?.()
    })

    await waitFor(() => expect(result.current.state).toBe('polling'))
  })
})
