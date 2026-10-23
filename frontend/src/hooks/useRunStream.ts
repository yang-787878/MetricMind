import { useEffect, useRef, useState } from 'react'

import { api } from '@/lib/api'
import { openRunStream, type StreamState } from '@/lib/sse'
import type { AppEvent } from '@/types/events'

interface UseRunStreamResult {
  events: AppEvent[]
  state: StreamState
  lastSeq: number
}

/**
 * 订阅一次 run 的事件流：
 * - 用 seq 去重，避免 SSE 重连/轮询重复插入；
 * - SSE 连续失败后自动降级为轮询（每 1.5s 拉一次 after_seq），前端仍能继续更新。
 */
export function useRunStream(
  runId: string | undefined,
  options: { enabled?: boolean; pollIntervalMs?: number } = {},
): UseRunStreamResult {
  const { enabled = true, pollIntervalMs = 1500 } = options
  const [events, setEvents] = useState<AppEvent[]>([])
  const [state, setState] = useState<StreamState>('connecting')
  const seqRef = useRef(0)
  const buffered = useRef<AppEvent[]>([])

  useEffect(() => {
    if (!runId || !enabled) return
    setEvents([])
    buffered.current = []
    seqRef.current = 0
    let cancelled = false

    const append = (event: AppEvent) => {
      if (event.seq <= seqRef.current) return
      seqRef.current = event.seq
      buffered.current = [...buffered.current, event]
      setEvents(buffered.current)
    }

    const stop = openRunStream(runId, 0, {
      onEvent: append,
      onState: (next) => {
        if (!cancelled) setState(next)
      },
    })

    return () => {
      cancelled = true
      stop()
    }
  }, [runId, enabled])

  useEffect(() => {
    if (!runId || !enabled || state !== 'polling') return
    let cancelled = false
    const tick = async () => {
      try {
        const response = await api.listEvents(runId, seqRef.current)
        if (cancelled) return
        for (const event of response.events) {
          if (event.seq > seqRef.current) {
            seqRef.current = event.seq
            buffered.current = [...buffered.current, event]
          }
        }
        if (response.events.length > 0) setEvents([...buffered.current])
        if (response.is_terminal) setState('closed')
      } catch {
        // 轮询失败保持静默，下一轮继续；顶部状态条已提示降级
      }
    }
    const timer = window.setInterval(tick, pollIntervalMs)
    void tick()
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [runId, enabled, state, pollIntervalMs])

  return { events, state, lastSeq: seqRef.current }
}
