import { AlertTriangle } from 'lucide-react'

export function LimitationList({ limitations }: { limitations: string[] }) {
  if (limitations.length === 0) {
    return <p className="text-caption text-muted">本次分析没有记录额外限制。</p>
  }
  return (
    <ul className="space-y-2">
      {limitations.map((item, index) => (
        <li
          key={`${index}-${item.slice(0, 12)}`}
          className="flex gap-2 border-l-2 border-warning-600 py-0.5 pl-2.5 text-caption text-secondary"
        >
          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-warning-600" aria-hidden />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}
