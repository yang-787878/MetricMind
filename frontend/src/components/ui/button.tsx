import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { cn } from '@/lib/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-brand-600 text-ink-inverse hover:bg-brand-700 disabled:bg-brand-600/40 disabled:cursor-not-allowed',
  secondary:
    'border border-border-strong bg-surface text-ink hover:bg-surface-3 disabled:text-muted disabled:cursor-not-allowed',
  ghost: 'text-secondary hover:bg-surface-3 hover:text-ink disabled:text-muted disabled:cursor-not-allowed',
  danger: 'bg-danger-600 text-ink-inverse hover:bg-danger-600/90 disabled:opacity-50',
}

const SIZES: Record<Size, string> = {
  sm: 'h-8 gap-1.5 px-3 text-caption',
  md: 'h-9 gap-2 px-4 text-body-lg',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  icon?: ReactNode
}

export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  className,
  children,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        'focus-ring inline-flex select-none items-center justify-center rounded-md font-medium',
        'transition-colors duration-150',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {icon ? <span className="shrink-0">{icon}</span> : null}
      {children}
    </button>
  )
}
