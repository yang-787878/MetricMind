import { AlertCircle, CircleAlert, Info } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/cn'

type Tone = 'info' | 'warning' | 'danger'

const TONES: Record<Tone, { box: string; icon: string; Icon: typeof Info }> = {
  info: { box: 'border-border bg-surface-2 text-secondary', icon: 'text-brand-600', Icon: Info },
  warning: {
    box: 'border-warning-600/30 bg-warning-50 text-warning-600',
    icon: 'text-warning-600',
    Icon: AlertCircle,
  },
  danger: {
    box: 'border-danger-600/30 bg-danger-50 text-danger-600',
    icon: 'text-danger-600',
    Icon: CircleAlert,
  },
}

interface InlineAlertProps {
  tone?: Tone
  title?: string
  children: ReactNode
  action?: ReactNode
  className?: string
}

/** 错误与告警就地展示（不使用 toast），保证用户能读到正文与修复建议（§7.8）。 */
export function InlineAlert({ tone = 'info', title, children, action, className }: InlineAlertProps) {
  const config = TONES[tone]
  const Icon = config.Icon
  return (
    <div
      role={tone === 'info' ? 'status' : 'alert'}
      className={cn('flex items-start gap-2 rounded-md border px-3 py-2', config.box, className)}
    >
      <Icon className={cn('mt-0.5 shrink-0', config.icon)} size={16} aria-hidden />
      <div className="min-w-0 flex-1 text-caption">
        {title ? <p className="font-medium">{title}</p> : null}
        <div className={cn('break-words', title ? 'mt-0.5' : '')}>{children}</div>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  )
}
