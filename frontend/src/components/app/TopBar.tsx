import { Download, HelpCircle, Menu, X } from 'lucide-react'
import { useState } from 'react'
import { Link, useMatch } from 'react-router-dom'

import { ModeBadge } from '@/components/app/ModeBadge'
import { ExportMenu } from '@/components/report/ExportMenu'
import { StatusPill } from '@/components/ui/status-pill'
import { useConfig } from '@/hooks/useSystem'
import { useRun } from '@/hooks/useRuns'
import { cn } from '@/lib/cn'
import { useAppStore } from '@/store/app'

function BrandMark() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden className="shrink-0">
      <rect x="1" y="12" width="3" height="6" rx="1" fill="var(--brand-600)" />
      <rect x="6" y="9" width="3" height="9" rx="1" fill="var(--brand-600)" />
      <rect x="11" y="6" width="3" height="12" rx="1" fill="var(--brand-600)" />
      <path d="M2 8.5 8 5.5 13 3.5 18 1.8" fill="none" stroke="var(--brand-500)" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

const TERMINAL = new Set(['succeeded', 'partial', 'failed', 'cancelled'])

export function TopBar({ pageTitle }: { pageTitle: string }) {
  const { data: config } = useConfig()
  const [helpOpen, setHelpOpen] = useState(false)
  const workspaceMatch = useMatch('/workspace/:runId')
  const reportMatch = useMatch('/runs/:runId/report')
  const runId = workspaceMatch?.params.runId ?? reportMatch?.params.runId
  const { data: run } = useRun(runId)
  const terminal = Boolean(run && TERMINAL.has(run.status))
  const setRailOpen = useAppStore((state) => state.setRailOpen)

  return (
    <header className="sticky top-0 z-20 h-14 border-b border-border bg-surface/95 backdrop-blur-sm">
      <div className="flex h-full items-center gap-3 px-4 lg:px-6">
        <button
          type="button"
          onClick={() => setRailOpen(true)}
          aria-label="打开侧栏"
          className="focus-ring -ml-1 inline-flex size-8 items-center justify-center rounded-md text-muted hover:bg-surface-3 hover:text-ink md:hidden"
        >
          <Menu size={18} aria-hidden />
        </button>
        <Link to="/" className="focus-ring flex shrink-0 items-center gap-2 rounded-sm" aria-label="回到首页">
          <BrandMark />
          <span className="text-body-lg font-semibold tracking-[-0.01em] text-ink">MetricMind</span>
        </Link>
        <span className="hidden h-5 w-px bg-border lg:block" aria-hidden />
        <span className="hidden min-w-0 truncate text-body text-secondary lg:block">{pageTitle}</span>

        <div className="ml-auto flex shrink-0 items-center gap-2">
          {run ? (
            <span className="hidden sm:inline-flex">
              <StatusPill status={run.status} />
            </span>
          ) : null}
          <span className="hidden sm:inline-flex">
            <ModeBadge mode={config?.llm_mode} />
          </span>
          {runId ? (
            <ExportMenu
              runId={runId}
              disabled={!terminal}
              disabledReason="分析完成后可导出报告"
              onError={(message) => window.alert(message)}
            />
          ) : (
            <button
              type="button"
              disabled
              title="分析完成后可导出报告"
              className="hidden h-8 cursor-not-allowed items-center gap-1.5 rounded-md border border-border-strong bg-surface px-3 text-caption text-muted sm:inline-flex"
            >
              <Download size={14} aria-hidden />
              导出报告
            </button>
          )}
          <div className="relative">
            <button
              type="button"
              className="focus-ring inline-flex size-8 items-center justify-center rounded-md text-muted transition-colors hover:bg-surface-3 hover:text-ink"
              aria-label="键盘快捷键"
              aria-expanded={helpOpen}
              onClick={() => setHelpOpen((open) => !open)}
            >
              {helpOpen ? <X size={16} aria-hidden /> : <HelpCircle size={16} aria-hidden />}
            </button>
            {helpOpen ? (
              <div
                className={cn('absolute right-0 top-9 z-30 w-64 rounded-lg border border-border bg-surface p-3 shadow-md')}
                role="dialog"
                aria-label="键盘快捷键"
              >
                <p className="mb-2 text-caption font-medium text-ink">键盘快捷键</p>
                <dl className="space-y-1 text-caption text-secondary">
                  <div className="flex items-center justify-between gap-3">
                    <dt>聚焦问题输入</dt>
                    <dd className="font-mono text-micro text-ink">/</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt>关闭抽屉 / 弹层</dt>
                    <dd className="font-mono text-micro text-ink">Esc</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt>提交问题</dt>
                    <dd className="font-mono text-micro text-ink">Enter</dd>
                  </div>
                </dl>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </header>
  )
}
