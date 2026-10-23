import { cn } from '@/lib/cn'

/** 预算/覆盖率进度条：超过 80% 转琥珀（§7.7）。 */
export function Meter({
  label,
  used,
  limit,
  suffix,
  className,
}: {
  label: string
  used: number
  limit: number
  suffix?: string
  className?: string
}) {
  const ratio = limit > 0 ? Math.min(used / limit, 1) : 0
  const warning = ratio >= 0.8
  return (
    <div className={cn('space-y-1.5', className)}>
      <div className="flex items-baseline justify-between gap-2 text-caption">
        <span className="text-secondary">{label}</span>
        <span className="tabular text-micro text-muted">
          {used} / {limit}
          {suffix ? ` ${suffix}` : ''}
        </span>
      </div>
      <div
        className="h-1.5 w-full overflow-hidden rounded-pill bg-surface-3"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={limit}
        aria-valuenow={used}
      >
        <div
          className={cn('h-full rounded-pill transition-all duration-200', warning ? 'bg-warning-600' : 'bg-brand-600')}
          style={{ width: `${Math.round(ratio * 100)}%` }}
        />
      </div>
      {warning ? <p className="text-micro text-warning-600">接近上限</p> : null}
    </div>
  )
}

/** 覆盖率环形指标（SVG 自绘，不引图表库）。 */
export function CoverageRing({ coverage, size = 88 }: { coverage: number; size?: number }) {
  const radius = size / 2 - 8
  const circumference = 2 * Math.PI * radius
  const ratio = Math.max(0, Math.min(coverage, 1))
  const tone = ratio >= 0.9 ? 'var(--success-600)' : ratio >= 0.6 ? 'var(--warning-600)' : 'var(--danger-600)'
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="数字审计覆盖率">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--surface-3)" strokeWidth="8" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={tone}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${circumference * ratio} ${circumference}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span className="absolute tabular text-body-lg font-semibold text-ink">{Math.round(ratio * 100)}%</span>
    </div>
  )
}
