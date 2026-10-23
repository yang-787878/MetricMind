/** 数字/单位/时长/时间的统一格式化。所有页面只允许用这里的实现。 */

const UNIT_LABELS: Record<string, string> = {
  CNY: '人民币',
  ratio: '比率',
  count: '条数',
}

export function unitLabel(unit: string | null | undefined): string {
  if (!unit) return ''
  return UNIT_LABELS[unit] ?? unit
}

/** 与后端 report_builder.format_value 保持一致：金额 万/亿、比率百分比。 */
export function formatValue(value: number | null | undefined, unit?: string | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  if (unit === 'CNY') {
    const amount = Number(value)
    if (Math.abs(amount) >= 1e8) return `¥${(amount / 1e8).toFixed(2)} 亿`
    if (Math.abs(amount) >= 1e4) return `¥${(amount / 1e4).toFixed(1)} 万`
    return `¥${amount.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`
  }
  if (unit === 'ratio' || unit === '%') return `${(Number(value) * 100).toFixed(1)}%`
  if (unit === 'count') return Number(value).toLocaleString('zh-CN')
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

/** 坐标轴刻度：短、可读，不带货币符号（单位在轴标题上）。 */
export function formatAxis(value: number, unit?: string | null): string {
  if (unit === 'ratio' || unit === '%') return `${(value * 100).toFixed(0)}%`
  const abs = Math.abs(value)
  if (abs >= 1e8) return `${(value / 1e8).toFixed(1)}亿`
  if (abs >= 1e4) return `${(value / 1e4).toFixed(0)}万`
  if (abs >= 1000) return `${(value / 1000).toFixed(0)}k`
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return Number(value).toLocaleString('zh-CN')
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${Math.max(Math.round(ms), 1)}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const minutes = Math.floor(ms / 60_000)
  const seconds = Math.round((ms % 60_000) / 1000)
  return `${minutes}m ${String(seconds).padStart(2, '0')}s`
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN', { hour12: false })
}

export function formatClock(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleTimeString('zh-CN', { hour12: false })
}

export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const diff = Date.now() - then
  if (diff < 45_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.round(diff / 3_600_000)} 小时前`
  return `${Math.round(diff / 86_400_000)} 天前`
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function truncate(text: string, max = 80): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`
}
