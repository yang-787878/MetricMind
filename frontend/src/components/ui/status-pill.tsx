import { cn } from '@/lib/cn'

type Kind = 'run' | 'step' | 'tool' | 'verification'

const RUN_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '运行中',
  succeeded: '成功',
  partial: '部分结果',
  failed: '失败',
  cancelled: '已取消',
}

const STEP_LABELS: Record<string, string> = {
  pending: '待执行',
  running: '执行中',
  succeeded: '完成',
  failed: '失败',
  skipped: '已跳过',
}

const TOOL_LABELS: Record<string, string> = {
  ok: '成功',
  error: '失败',
  timeout: '超时',
  rejected: '被拦截',
}

const VERIFICATION_LABELS: Record<string, string> = {
  supported: '已证实',
  unsupported: '未通过',
  unverifiable: '无法验证',
}

const TONES: Record<string, string> = {
  queued: 'bg-surface-3 text-secondary border-border',
  pending: 'bg-surface-3 text-secondary border-border',
  running: 'bg-brand-50 text-brand-600 border-brand-100',
  succeeded: 'bg-success-50 text-success-600 border-success-50',
  ok: 'bg-success-50 text-success-600 border-success-50',
  supported: 'bg-success-50 text-success-600 border-success-50',
  partial: 'bg-warning-50 text-warning-600 border-warning-50',
  unverifiable: 'bg-warning-50 text-warning-600 border-warning-50',
  timeout: 'bg-warning-50 text-warning-600 border-warning-50',
  failed: 'bg-danger-50 text-danger-600 border-danger-50',
  error: 'bg-danger-50 text-danger-600 border-danger-50',
  rejected: 'bg-danger-50 text-danger-600 border-danger-50',
  unsupported: 'bg-danger-50 text-danger-600 border-danger-50',
  cancelled: 'bg-surface-3 text-muted border-border',
  skipped: 'bg-surface-3 text-muted border-border',
}

function labelsFor(kind: Kind): Record<string, string> {
  if (kind === 'step') return STEP_LABELS
  if (kind === 'tool') return TOOL_LABELS
  if (kind === 'verification') return VERIFICATION_LABELS
  return RUN_LABELS
}

export function StatusPill({
  status,
  kind = 'run',
  className,
}: {
  status: string
  kind?: Kind
  className?: string
}) {
  const labels = labelsFor(kind)
  const label = labels[status] ?? status
  const tone = TONES[status] ?? 'bg-surface-3 text-secondary border-border'
  const running = status === 'running' || status === 'pending'

  return (
    <span
      className={cn(
        'inline-flex h-6 items-center gap-1.5 rounded-pill border px-2.5 text-micro font-medium',
        tone,
        className,
      )}
      title={label}
    >
      <span
        className={cn(
          'size-1.5 rounded-full bg-current',
          running && status === 'running' && 'animate-pulse',
          running && status === 'pending' && 'opacity-40',
        )}
        aria-hidden
      />
      {label}
    </span>
  )
}
