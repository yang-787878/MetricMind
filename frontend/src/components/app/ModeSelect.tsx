import { cn } from '@/lib/cn'
import type { RequestedMode } from '@/types/contract'

const OPTIONS: { key: RequestedMode; label: string; hint: string }[] = [
  { key: 'auto', label: '自动', hint: '有 API Key 走 Live，否则用 Demo' },
  { key: 'live', label: 'Live', hint: '真实大模型生成计划与叙述' },
  { key: 'demo', label: 'Demo', hint: '无模型，模板计划，数字同样来自工具' },
]

/**
 * 运行模式选择。`liveAvailable=false` 时给 Live 加一个琥珀点：
 * 后端 /api/config 已经告诉我们当前是 demo（没配 Key），不需要等用户提交才知道。
 */
export function ModeSelect({
  value,
  onChange,
  disabled,
  liveAvailable = true,
}: {
  value: RequestedMode
  onChange: (mode: RequestedMode) => void
  disabled?: boolean
  liveAvailable?: boolean
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-micro text-muted">模式</span>
      <div
        role="radiogroup"
        aria-label="运行模式"
        className="inline-flex rounded-md border border-border bg-surface p-0.5"
      >
        {OPTIONS.map((option) => {
          const unavailable = option.key === 'live' && !liveAvailable
          return (
            <button
              key={option.key}
              type="button"
              role="radio"
              aria-checked={value === option.key}
              aria-label={`${option.label}：${option.hint}`}
              title={unavailable ? `${option.hint}（当前后端未配置 API Key）` : option.hint}
              disabled={disabled}
              onClick={() => onChange(option.key)}
              className={cn(
                'focus-ring inline-flex h-6 items-center gap-1 rounded-sm px-2 text-micro transition-colors',
                value === option.key ? 'bg-surface-3 font-medium text-ink' : 'text-secondary hover:text-ink',
                disabled && 'cursor-not-allowed opacity-60',
              )}
            >
              {option.label}
              {unavailable ? (
                <span className="size-1 rounded-full bg-warning-600" aria-hidden title="未配置 API Key" />
              ) : null}
            </button>
          )
        })}
      </div>
    </div>
  )
}
