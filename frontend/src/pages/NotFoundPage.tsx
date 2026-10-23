import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-6">
      <div className="max-w-[420px] text-center">
        <p className="font-mono text-micro uppercase tracking-widest text-muted">404</p>
        <h1 className="mt-2 text-h2 font-semibold text-ink">页面不存在</h1>
        <p className="mt-2 text-body-lg text-secondary">
          链接可能已失效，或者这个地址从未存在过。回到工作台重新开始一次分析。
        </p>
        <Link
          to="/"
          className="focus-ring mt-5 inline-flex h-9 items-center rounded-md bg-brand-600 px-4 text-body-lg font-medium text-ink-inverse hover:bg-brand-700"
        >
          返回工作台
        </Link>
      </div>
    </div>
  )
}
