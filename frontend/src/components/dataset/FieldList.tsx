import { cn } from '@/lib/cn'
import type { ColumnProfile, SemanticType } from '@/types/contract'

const GROUPS: { type: SemanticType; label: string }[] = [
  { type: 'numeric', label: '数值' },
  { type: 'temporal', label: '时间' },
  { type: 'categorical', label: '分类' },
  { type: 'identifier', label: '标识' },
  { type: 'boolean', label: '布尔' },
  { type: 'text', label: '文本' },
]

/** 字段列表：按语义类型分组，缺失率 > 0 的字段右侧显示琥珀点（§7.3）。 */
export function FieldList({ columns }: { columns: ColumnProfile[] }) {
  if (columns.length === 0) {
    return <p className="px-3 py-2 text-caption text-muted">选择数据集后显示字段</p>
  }

  return (
    <div className="space-y-3 px-3 pb-2">
      {GROUPS.map((group) => {
        const items = columns.filter((column) => column.semantic_type === group.type)
        if (items.length === 0) return null
        return (
          <div key={group.type}>
            <p className="mb-1 text-micro uppercase tracking-wide text-muted">{group.label}</p>
            <ul className="space-y-0.5">
              {items.map((column) => (
                <li key={column.name} className="flex items-center gap-1.5 text-caption">
                  <span className="min-w-0 flex-1 truncate text-secondary" title={`${column.name} · ${column.dtype}`}>
                    {column.name}
                  </span>
                  {column.null_rate > 0 ? (
                    <span
                      className={cn('size-1.5 shrink-0 rounded-full', column.null_rate >= 0.01 ? 'bg-warning-600' : 'bg-warning-600/50')}
                      title={`缺失 ${(column.null_rate * 100).toFixed(1)}%`}
                      aria-label={`缺失率 ${(column.null_rate * 100).toFixed(1)}%`}
                    />
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}
