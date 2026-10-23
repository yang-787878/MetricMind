import { cn } from '@/lib/cn'

export interface TabItem<T extends string> {
  key: T
  label: string
  count?: number
}

export function Tabs<T extends string>({
  items,
  value,
  onChange,
  className,
  ariaLabel,
}: {
  items: TabItem<T>[]
  value: T
  onChange: (key: T) => void
  className?: string
  ariaLabel: string
}) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cn('flex items-center gap-1 border-b border-border px-2 py-1.5', className)}
    >
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          role="tab"
          aria-selected={value === item.key}
          onClick={() => onChange(item.key)}
          className={cn(
            'focus-ring inline-flex h-7 items-center gap-1.5 rounded-sm px-2 text-caption transition-colors',
            value === item.key
              ? 'bg-surface font-medium text-ink shadow-xs'
              : 'text-secondary hover:bg-surface-3',
          )}
        >
          {item.label}
          {item.count !== undefined ? <span className="tabular text-micro text-muted">{item.count}</span> : null}
        </button>
      ))}
    </div>
  )
}
