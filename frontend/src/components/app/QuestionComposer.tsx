import { ArrowRight } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { InlineAlert } from '@/components/feedback/InlineAlert'

interface QuestionComposerProps {
  examples: string[]
  onSubmit: (question: string) => void
  disabled?: boolean
  disabledReason?: string
}

const MAX_LENGTH = 500

/** 问题输入：Enter 提交、`/` 聚焦、超长即时提示，校验与后端 3..500 保持一致。 */
export function QuestionComposer({ examples, onSubmit, disabled, disabledReason }: QuestionComposerProps) {
  const [value, setValue] = useState('')
  const [placeholderIndex, setPlaceholderIndex] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (examples.length <= 1) return
    const timer = window.setInterval(
      () => setPlaceholderIndex((index) => (index + 1) % examples.length),
      4000,
    )
    return () => window.clearInterval(timer)
  }, [examples.length])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable
      if (event.key === '/' && !typing) {
        event.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const submit = () => {
    const question = value.trim()
    if (question.length < 3) {
      setError('请至少输入 3 个字符的问题')
      return
    }
    if (question.length > MAX_LENGTH) {
      setError(`问题最多 ${MAX_LENGTH} 个字符`)
      return
    }
    setError(null)
    onSubmit(question)
  }

  const placeholder = examples[placeholderIndex] ?? '例如：为什么 9 月销售额下降了？'

  return (
    <div className="mt-5">
      <div className="flex items-stretch gap-2">
        <div className="relative min-w-0 flex-1">
          <input
            ref={inputRef}
            value={value}
            disabled={disabled}
            onChange={(event) => {
              setValue(event.target.value)
              if (error) setError(null)
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                if (!disabled) submit()
              }
            }}
            placeholder={placeholder}
            aria-label="分析问题"
            maxLength={MAX_LENGTH + 50}
            className="focus-ring h-11 w-full rounded-md border border-border-strong bg-surface px-3 text-body-lg text-ink placeholder:text-muted disabled:bg-surface-3 disabled:text-muted"
          />
        </div>
        <Button
          variant="primary"
          disabled={disabled}
          onClick={submit}
          title={disabled ? disabledReason : '提交分析问题'}
          icon={<ArrowRight size={15} aria-hidden />}
        >
          开始分析
        </Button>
      </div>
      <div className="mt-1.5 flex items-center justify-between text-micro text-muted">
        <span>{disabled ? disabledReason : '按 / 聚焦输入框，Enter 提交'}</span>
        <span className="tabular">
          {value.length}/{MAX_LENGTH}
        </span>
      </div>
      {error ? (
        <InlineAlert tone="danger" className="mt-2">
          {error}
        </InlineAlert>
      ) : null}
    </div>
  )
}
