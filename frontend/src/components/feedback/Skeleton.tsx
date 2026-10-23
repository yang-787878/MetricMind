import { cn } from '@/lib/cn'

/** 骨架块：尺寸与最终布局一致，运行提交后 300ms 内替换白屏（§7.8）。 */
export function SkeletonBlock({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-surface-3', className)} aria-hidden />
}

export function SkeletonLines({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('space-y-2', className)} role="status" aria-label="加载中">
      {Array.from({ length: rows }, (_, index) => (
        <SkeletonBlock
          key={index}
          className={cn('h-3', index === rows - 1 ? 'w-2/3' : 'w-full')}
        />
      ))}
    </div>
  )
}
