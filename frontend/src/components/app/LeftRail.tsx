import { Columns3, Database, History, PanelLeftClose, PanelLeftOpen, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { DatasetCard } from '@/components/dataset/DatasetCard'
import { FieldList } from '@/components/dataset/FieldList'
import { StatusPill } from '@/components/ui/status-pill'
import { useConfig } from '@/hooks/useSystem'
import { useDatasets, useRuns } from '@/hooks/useRuns'
import { api } from '@/lib/api'
import { cn } from '@/lib/cn'
import { formatRelativeTime } from '@/lib/format'
import { useAppStore } from '@/store/app'

const STORAGE_KEY = 'mm.rail.collapsed'

function useCollapsed() {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(STORAGE_KEY) === '1'
    } catch {
      return false
    }
  })
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0')
    } catch {
      // 隐私模式下 localStorage 不可写，折叠状态退化为仅当前会话有效
    }
  }, [collapsed])
  return { collapsed, toggle: () => setCollapsed((value) => !value) }
}

function SectionTitle({ icon, children, collapsed }: { icon: React.ReactNode; children: React.ReactNode; collapsed: boolean }) {
  return (
    <div className={cn('flex items-center gap-2 px-3 pb-1 pt-4', collapsed && 'justify-center px-0')}>
      <span className="text-muted" aria-hidden>
        {icon}
      </span>
      {collapsed ? null : (
        <span className="text-micro font-medium uppercase tracking-wide text-muted">{children}</span>
      )}
    </div>
  )
}

export function LeftRail({ inDrawer = false }: { inDrawer?: boolean }) {
  const { collapsed: collapsedState, toggle } = useCollapsed()
  const collapsed = collapsedState && !inDrawer
  const { data: config } = useConfig()
  const { data: datasets } = useDatasets()
  const { data: runs } = useRuns(8)
  const selectedId = useAppStore((state) => state.selectedDatasetId)
  const selectDataset = useAppStore((state) => state.selectDataset)
  const setRailOpen = useAppStore((state) => state.setRailOpen)
  const navigate = useNavigate()

  const { data: selected } = useQuery({
    queryKey: ['dataset', selectedId],
    queryFn: () => api.getDataset(selectedId as string),
    enabled: Boolean(selectedId),
  })

  return (
    <aside
      className={cn(
        inDrawer
          ? 'flex h-full w-rail flex-col bg-surface'
          : 'sticky top-14 hidden h-[calc(100vh-56px)] shrink-0 flex-col border-r border-border bg-surface md:flex',
        !inDrawer && (collapsed ? 'w-rail-collapsed' : 'w-rail'),
      )}
      aria-label="数据集与最近分析"
    >
      <div className="flex items-center justify-between px-3 pt-3">
        {collapsed && !inDrawer ? null : <span className="text-caption font-medium text-ink">工作区</span>}
        <button
          type="button"
          onClick={() => (inDrawer ? setRailOpen(false) : toggle())}
          className="focus-ring inline-flex size-7 items-center justify-center rounded-sm text-muted transition-colors hover:bg-surface-3 hover:text-ink"
          aria-label={inDrawer ? '关闭侧栏' : collapsedState ? '展开侧栏' : '折叠侧栏'}
          title={inDrawer ? '关闭侧栏' : collapsedState ? '展开侧栏' : '折叠侧栏'}
        >
          {inDrawer ? <X size={16} /> : collapsedState ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto pb-2">
        <SectionTitle icon={<Database size={14} />} collapsed={collapsed}>
          Datasets
        </SectionTitle>
        {collapsed ? null : (
          <div className="space-y-1 px-2">
            {datasets && datasets.items.length > 0 ? (
              datasets.items.map((dataset) => (
                <DatasetCard
                  key={dataset.dataset_id}
                  dataset={dataset}
                  selected={dataset.dataset_id === selectedId}
                  onSelect={() => selectDataset(dataset.dataset_id)}
                />
              ))
            ) : (
              <p className="px-1 py-2 text-caption text-muted">还没有数据集</p>
            )}
          </div>
        )}

        <SectionTitle icon={<Columns3 size={14} />} collapsed={collapsed}>
          Fields
        </SectionTitle>
        {collapsed ? null : <FieldList columns={selected?.columns ?? []} />}

        <SectionTitle icon={<History size={14} />} collapsed={collapsed}>
          Recent runs
        </SectionTitle>
        {collapsed ? null : (
          <ul className="space-y-0.5 px-2">
            {runs && runs.items.length > 0 ? (
              runs.items.map((run) => (
                <li key={run.run_id}>
                  <button
                    type="button"
                    onClick={() => navigate(`/workspace/${run.run_id}`)}
                    className="focus-ring flex w-full items-center gap-2 rounded-sm px-1.5 py-1 text-left hover:bg-surface-2"
                  >
                    <StatusPill status={run.status} />
                    <span className="min-w-0 flex-1 truncate text-caption text-secondary" title={run.question}>
                      {run.question}
                    </span>
                    <span className="shrink-0 text-micro text-muted">{formatRelativeTime(run.created_at)}</span>
                  </button>
                </li>
              ))
            ) : (
              <li className="px-1.5 py-2 text-caption text-muted">还没有分析记录</li>
            )}
          </ul>
        )}
      </nav>

      <div className="border-t border-border p-3">
        {collapsed ? (
          <span className="block text-center text-micro text-muted" title="v1.0.0">
            v1
          </span>
        ) : (
          <details className="group">
            <summary className="focus-ring cursor-pointer list-none rounded-sm text-micro text-muted hover:text-ink">
              限额与版本
            </summary>
            <dl className="mt-2 space-y-1 text-micro text-secondary">
              <div className="flex justify-between gap-2">
                <dt>单文件</dt>
                <dd className="tabular">{config ? `≤ ${config.limits.max_upload_mb} MB` : '—'}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt>行数</dt>
                <dd className="tabular">{config ? `≤ ${config.limits.max_rows.toLocaleString()}` : '—'}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt>步数 / 工具</dt>
                <dd className="tabular">{config ? `${config.limits.max_steps} / ${config.limits.max_tool_calls}` : '—'}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt>版本</dt>
                <dd className="font-mono">v1.0.0</dd>
              </div>
            </dl>
          </details>
        )}
      </div>
    </aside>
  )
}

