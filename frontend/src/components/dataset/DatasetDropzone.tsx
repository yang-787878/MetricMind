import { FileSpreadsheet, Upload } from 'lucide-react'
import { useRef, useState } from 'react'

import { InlineAlert } from '@/components/feedback/InlineAlert'
import { Button } from '@/components/ui/button'
import { useUploadDataset } from '@/hooks/useRuns'
import { cn } from '@/lib/cn'
import type { DatasetDetail } from '@/types/contract'

const ACCEPT = '.csv,.xlsx'
const ACCEPTED = ['csv', 'xlsx']
const PHASE_LABEL = {
  validating: '校验文件',
  parsing: '解析与建表',
  ready: '完成',
} as const

export function DatasetDropzone({
  onUploaded,
  maxUploadMb = 25,
}: {
  onUploaded: (dataset: DatasetDetail) => void
  maxUploadMb?: number
}) {
  const [dragging, setDragging] = useState(false)
  const [clientError, setClientError] = useState<string | null>(null)
  const [phase, setPhase] = useState<keyof typeof PHASE_LABEL | null>(null)
  const [ratio, setRatio] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const upload = useUploadDataset()

  const start = (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
    if (!ACCEPTED.includes(ext)) {
      setClientError(`不支持的文件类型 .${ext || '(无扩展名)'}，仅支持 CSV / XLSX`)
      return
    }
    if (file.size > maxUploadMb * 1024 * 1024) {
      setClientError(`文件 ${(file.size / 1024 / 1024).toFixed(1)} MB 超过 ${maxUploadMb} MB 限制`)
      return
    }
    setClientError(null)
    setPhase('validating')
    setRatio(0)
    upload.mutate(
      {
        file,
        onPhase: (next, value) => {
          setPhase(next)
          setRatio(value)
        },
      },
      {
        onSuccess: (dataset) => {
          window.setTimeout(() => setPhase(null), 600)
          onUploaded(dataset)
        },
        onError: () => setPhase(null),
      },
    )
  }

  const error = upload.error as { message?: string; hint?: string } | null

  return (
    <div>
      <div
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          const file = event.dataTransfer.files?.[0]
          if (file) start(file)
        }}
        onPaste={(event) => {
          const file = event.clipboardData?.files?.[0]
          if (file) start(file)
        }}
        className={cn(
          'flex min-h-[168px] flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-5 text-center transition-colors duration-150',
          dragging ? 'border-brand-500 bg-brand-50' : 'border-border-strong bg-surface-2',
        )}
      >
        <Upload size={18} className="text-muted" aria-hidden />
        <p className="text-body-lg font-medium text-ink">拖拽文件到这里，或点击选择</p>
        <p className="text-caption text-secondary">
          支持 CSV / XLSX，单文件 ≤ {maxUploadMb} MB，≤ 20 万行，≤ 60 列
        </p>
        <div className="mt-1 flex items-center gap-2">
          <Button
            size="sm"
            disabled={upload.isPending}
            onClick={() => inputRef.current?.click()}
            icon={<FileSpreadsheet size={14} aria-hidden />}
          >
            {upload.isPending ? '上传中…' : '选择文件'}
          </Button>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            className="sr-only"
            aria-label="选择数据文件"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) start(file)
              event.target.value = ''
            }}
          />
        </div>

        {phase ? (
          <div className="mt-1 w-full max-w-[280px]" role="status" aria-live="polite">
            <div className="flex items-center justify-between text-micro text-secondary">
              <span>{PHASE_LABEL[phase]}…</span>
              <span className="tabular">{Math.round(ratio * 100)}%</span>
            </div>
            <div className="mt-1 h-1 w-full overflow-hidden rounded-pill bg-surface-3">
              <div
                className="h-full rounded-pill bg-brand-600 transition-all duration-150"
                style={{ width: `${Math.max(Math.round(ratio * 100), 6)}%` }}
              />
            </div>
          </div>
        ) : null}

        {clientError ? <p className="text-micro text-danger-600">{clientError}</p> : null}
      </div>

      {upload.isError ? (
        <InlineAlert tone="danger" title="上传失败" className="mt-2">
          {error?.message ?? '未知错误'}
          {error?.hint ? <span className="mt-0.5 block text-secondary">{error.hint}</span> : null}
        </InlineAlert>
      ) : null}
    </div>
  )
}
