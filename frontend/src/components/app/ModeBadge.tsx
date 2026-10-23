import { cn } from '@/lib/cn'
import type { RunMode } from '@/types/contract'

/** 模式徽标：live 与 demo 的视觉必须一眼可分（Demo 报告要带明显标识，§13.1）。 */
export function ModeBadge({ mode, className }: { mode?: RunMode; className?: string }) {
  if (!mode) {
    return (
      <span
        className={cn(
          'inline-flex h-6 items-center gap-1.5 rounded-pill border border-border bg-surface-2 px-2.5 text-micro text-muted',
          className,
        )}
      >
        模式未知
      </span>
    )
  }

  const live = mode === 'live'
  return (
    <span
      className={cn(
        'inline-flex h-6 items-center gap-1.5 rounded-pill px-2.5 text-micro font-medium',
        live ? 'bg-success-50 text-success-600' : 'bg-warning-50 text-warning-600',
        className,
      )}
      title={live ? '真实大模型生成叙述，数字来自工具执行' : '无模型脚本化模式：叙述来自模板，数字同样来自工具执行'}
    >
      <span
        className={cn('size-1.5 rounded-full', live ? 'bg-success-600' : 'bg-warning-600')}
        aria-hidden
      />
      {live ? 'Live model' : 'Demo mode'}
    </span>
  )
}
