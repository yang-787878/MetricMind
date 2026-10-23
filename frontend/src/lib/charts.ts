import type { ChartSpec, RunDetail, StructuredPlan } from '@/types/contract'

/** 从 run 的工具调用里还原 ChartSpec：后端 result 就是 ChartSpec 本身。 */
export function chartsFromRun(run: RunDetail | undefined | null): ChartSpec[] {
  if (!run) return []
  const charts: ChartSpec[] = []
  const seen = new Set<string>()
  for (const step of run.steps) {
    for (const call of step.tool_calls) {
      const result = call.result as ChartSpec | null
      if (call.tool !== 'create_chart' || !result || typeof result !== 'object') continue
      const chartId = (result as ChartSpec).chart_id
      if (!chartId || seen.has(chartId)) continue
      seen.add(chartId)
      charts.push(result as ChartSpec)
    }
  }
  return charts
}

export function mapByStep<T extends { step_id: string }>(items: T[]): Map<string, T[]> {
  const map = new Map<string, T[]>()
  for (const item of items) {
    const list = map.get(item.step_id) ?? []
    list.push(item)
    map.set(item.step_id, list)
  }
  return map
}

export function formulaFor(plan: StructuredPlan | null, index: number): string | undefined {
  const step = plan?.steps[index]
  return step?.validation
}
