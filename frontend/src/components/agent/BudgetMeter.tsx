import { Meter } from '@/components/ui/meter'
import { formatDuration } from '@/lib/format'
import type { Budget, Usage } from '@/types/contract'

export function BudgetMeter({
  usage,
  budget,
  elapsedMs,
}: {
  usage: Usage
  budget: Budget
  elapsedMs: number | null
}) {
  const elapsed = elapsedMs ?? 0
  const timeoutMs = budget.timeout_seconds * 1000

  return (
    <div className="space-y-3 p-3">
      <Meter label="步数" used={usage.steps_used} limit={budget.max_steps} suffix="步" />
      <Meter label="工具调用" used={usage.tool_calls_used} limit={budget.max_tool_calls} suffix="次" />
      <Meter label="重规划" used={usage.replans_used} limit={budget.max_replans} suffix="次" />
      <Meter
        label="耗时"
        used={Math.round(elapsed / 1000)}
        limit={budget.timeout_seconds}
        suffix={`/ ${formatDuration(timeoutMs)}`}
      />
      <dl className="grid grid-cols-2 gap-2 border-t border-border pt-2 text-micro">
        <div>
          <dt className="text-muted">LLM 调用</dt>
          <dd className="tabular text-ink">{usage.llm_calls}</dd>
        </div>
        <div>
          <dt className="text-muted">Token</dt>
          <dd className="tabular text-ink">{usage.prompt_tokens + usage.completion_tokens}</dd>
        </div>
      </dl>
    </div>
  )
}
