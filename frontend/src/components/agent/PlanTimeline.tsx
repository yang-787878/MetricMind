import { ListChecks } from 'lucide-react'
import { useEffect, useState } from 'react'

import { StepCard } from '@/components/agent/StepCard'
import { EmptyState } from '@/components/feedback/EmptyState'
import type { StructuredPlan, StepRecord } from '@/types/contract'

/** 垂直时间线：当前 running 的步骤默认展开，其余折叠（§7.5 第 3 条）。 */
export function PlanTimeline({
  steps,
  plan,
  replans = [],
}: {
  steps: StepRecord[]
  plan: StructuredPlan | null
  replans?: { failedStepId: string | null; count: number }[]
}) {
  const running = steps.find((step) => step.status === 'running')
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (!running) return
    setExpanded((current) => (current[running.step_id] ? current : { ...current, [running.step_id]: true }))
  }, [running?.step_id])

  if (steps.length === 0) {
    return (
      <EmptyState
        compact
        icon={<ListChecks size={18} />}
        title="还没有计划"
        description="运行开始后会先产出结构化分析计划：步骤、工具、预期输出与验证方式。"
      />
    )
  }

  return (
    <div>
      {plan?.objective ? (
        <p className="mb-2 rounded-md bg-surface-2 px-3 py-2 text-caption text-secondary">
          <span className="text-muted">分析目标：</span>
          {plan.objective}
        </p>
      ) : null}

      <ol className="relative">
        <span className="absolute bottom-2 left-[13px] top-3 w-px bg-border" aria-hidden />
        {steps.map((step, index) => {
          const isExpanded = expanded[step.step_id] ?? step.status === 'running'
          const replan = replans.find((item) => item.failedStepId === step.step_id)
          return (
            <div key={step.step_id}>
              <StepCard
                step={step}
                index={index}
                expanded={isExpanded}
                onToggle={() =>
                  setExpanded((current) => ({ ...current, [step.step_id]: !isExpanded }))
                }
              />
              {replan ? (
                <li className="relative my-2 ml-9 list-none border-t border-dashed border-border-strong pt-1 text-micro text-muted">
                  已重新规划（第 {replan.count} 次）
                </li>
              ) : null}
            </div>
          )
        })}
      </ol>
    </div>
  )
}
