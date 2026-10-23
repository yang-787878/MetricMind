import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { LeftRail } from '@/components/app/LeftRail'
import { TopBar } from '@/components/app/TopBar'
import { useAppStore } from '@/store/app'

function resolveTitle(pathname: string): string {
  if (pathname.startsWith('/workspace')) return '分析工作台'
  if (pathname.startsWith('/runs/')) return '分析报告'
  return '数据分析工作台'
}

/** 全站骨架：TopBar + LeftRail + 内容区；<768 时左栏折叠为抽屉（§7.3 / §7.5）。 */
export function AppShell() {
  const { pathname } = useLocation()
  const railOpen = useAppStore((state) => state.railOpen)
  const setRailOpen = useAppStore((state) => state.setRailOpen)

  useEffect(() => {
    if (!railOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setRailOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [railOpen, setRailOpen])

  useEffect(() => {
    setRailOpen(false)
  }, [pathname, setRailOpen])

  return (
    <div className="min-h-screen bg-bg">
      <TopBar pageTitle={resolveTitle(pathname)} />
      <div className="flex">
        <LeftRail />
        <main className="min-w-0 flex-1">
          <div className="mx-auto w-full max-w-content px-4 py-6 sm:px-6 lg:px-8">
            <Outlet />
          </div>
        </main>
      </div>

      {railOpen ? (
        <div className="fixed inset-0 z-30 md:hidden" role="dialog" aria-modal="true" aria-label="数据集与最近分析">
          <button
            type="button"
            aria-label="关闭侧栏"
            className="absolute inset-0 bg-ink/20"
            onClick={() => setRailOpen(false)}
          />
          <div className="relative h-full w-rail border-r border-border bg-surface shadow-md">
            <LeftRail inDrawer />
          </div>
        </div>
      ) : null}
    </div>
  )
}
