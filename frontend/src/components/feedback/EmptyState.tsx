import type { ReactNode } from 'react'

import { cn } from '@/lib/cn'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  description?: string
  action?: ReactNode
  className?: string
  compact?: boolean
}

/** 所有空态共用同一种结构与留白，避免每个区块各写一套"暂无数据"。 */
export function EmptyState({ icon, title, description, action, className, compact }: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface-2 text-center',
        compact ? 'gap-2 px-4 py-6' : 'gap-3 px-6 py-12',
        className,
      )}
    >
      <div className="text-muted" aria-hidden>
        {icon}
      </div>
      <p className="text-body-lg font-medium text-ink">{title}</p>
      {description ? (
        <p className="max-w-[46ch] text-caption leading-[18px] text-secondary">{description}</p>
      ) : null}
      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  )
}
