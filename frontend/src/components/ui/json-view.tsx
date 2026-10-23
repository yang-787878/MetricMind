import { cn } from '@/lib/cn'

/**
 * 40 行级别的 JSON 着色：只区分 key / string / number / boolean / null，
 * 不引入 highlight.js 这类整包依赖（§7.5 明确要求自写）。
 */
function tokenize(value: unknown): { text: string; kind: string }[] {
  const json = JSON.stringify(value, null, 2) ?? 'null'
  const pattern =
    /("(?:\\.|[^"\\])*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false)\b|\b(null)\b/g
  const tokens: { text: string; kind: string }[] = []
  let cursor = 0
  for (const match of json.matchAll(pattern)) {
    const index = match.index ?? 0
    if (index > cursor) tokens.push({ text: json.slice(cursor, index), kind: 'plain' })
    if (match[1]) {
      tokens.push({ text: match[1], kind: match[2] ? 'key' : 'string' })
      if (match[2]) tokens.push({ text: match[2], kind: 'plain' })
    } else if (match[3]) {
      tokens.push({ text: match[3], kind: 'number' })
    } else if (match[4]) {
      tokens.push({ text: match[4], kind: 'boolean' })
    } else if (match[5]) {
      tokens.push({ text: match[5], kind: 'null' })
    }
    cursor = index + match[0].length
  }
  if (cursor < json.length) tokens.push({ text: json.slice(cursor), kind: 'plain' })
  return tokens
}

const COLORS: Record<string, string> = {
  key: 'text-brand-700',
  string: 'text-success-600',
  number: 'text-chart-4',
  boolean: 'text-warning-600',
  null: 'text-muted',
  plain: 'text-secondary',
}

export function JsonView({ value, className }: { value: unknown; className?: string }) {
  const tokens = tokenize(value)
  return (
    <pre
      className={cn(
        'max-h-[320px] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-surface-2 p-3 font-mono text-micro leading-[18px]',
        className,
      )}
    >
      {tokens.map((token, index) => (
        <span key={index} className={COLORS[token.kind]}>
          {token.text}
        </span>
      ))}
    </pre>
  )
}
