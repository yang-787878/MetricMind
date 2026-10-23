import { RotateCcw, ServerCrash } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ApiError } from '@/lib/api'

/** 错误态：必须给出错误码、人话解释、修复建议和重试入口，不能只显示"加载失败"。 */
export function ErrorState({
  error,
  onRetry,
  title = '加载失败',
  compact,
}: {
  error: unknown
  onRetry?: () => void
  title?: string
  compact?: boolean
}) {
  const apiError = error instanceof ApiError ? error : null
  const message = apiError?.message ?? (error instanceof Error ? error.message : '未知错误')
  const hint = apiError?.hint

  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-2 rounded-lg border border-danger-600/30 bg-danger-50 px-4 py-3"
    >
      <div className="flex items-center gap-2 text-danger-600">
        <ServerCrash size={16} aria-hidden />
        <p className="text-body-lg font-medium">{title}</p>
        {apiError ? <span className="rounded-sm bg-surface px-1.5 font-mono text-micro">{apiError.code}</span> : null}
      </div>
      <p className="text-caption text-danger-600">{message}</p>
      {hint ? <p className="text-caption text-secondary">{hint}</p> : null}
      {!compact && onRetry ? (
        <Button size="sm" variant="secondary" icon={<RotateCcw size={14} aria-hidden />} onClick={onRetry}>
          重试
        </Button>
      ) : null}
    </div>
  )
}
