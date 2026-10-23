import type {
  ApiErrorBody,
  ArtifactInfo,
  ConfigResponse,
  CreateRunResponse,
  DatasetDetail,
  DatasetListResponse,
  DatasetPreview,
  HealthResponse,
  ReportModel,
  RequestedMode,
  RunDetail,
  RunListResponse,
} from '@/types/contract'
import type { EventsResponse } from '@/types/events'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

/** 后端统一错误信封的客户端形态：UI 按 code 与人话 message 渲染，hint 用于修复建议。 */
export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly details: ApiErrorBody['details']
  readonly requestId: string | null
  readonly retryable: boolean

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.details = body.details ?? {}
    this.requestId = body.request_id
    this.retryable = status >= 500 || status === 429 || status === 0
  }

  get hint(): string | null {
    const hint = this.details?.hint
    return typeof hint === 'string' ? hint : null
  }

  get available(): string[] {
    const available = this.details?.available
    return Array.isArray(available) ? available.map(String) : []
  }
}

function extractErrorBody(value: unknown): ApiErrorBody | null {
  if (typeof value !== 'object' || value === null) return null
  const candidate = (value as { error?: unknown }).error
  if (typeof candidate !== 'object' || candidate === null) return null
  return candidate as ApiErrorBody
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody = {
    code: `HTTP_${response.status}`,
    message: response.statusText || '请求失败',
    details: {},
    request_id: response.headers.get('X-Request-ID'),
  }
  try {
    const parsed: unknown = await response.json()
    const extracted = extractErrorBody(parsed)
    if (extracted) body = extracted
  } catch {
    // 响应不是 JSON（例如代理返回的 HTML 错误页）时保留状态码信息
  }
  return new ApiError(response.status, body)
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { Accept: 'application/json', ...(init?.headers ?? {}) },
      ...init,
    })
  } catch (error) {
    throw new ApiError(0, {
      code: 'NETWORK_ERROR',
      message: '无法连接后端服务，请确认 API 已启动',
      details: { hint: String(error) },
      request_id: null,
    })
  }

  if (!response.ok) throw await toApiError(response)
  if (response.status === 204) return undefined as T

  const contentType = response.headers.get('Content-Type') ?? ''
  if (contentType.includes('application/json')) return (await response.json()) as T
  return (await response.text()) as T
}

export type UploadPhase = 'validating' | 'parsing' | 'ready'

/** 上传必须给出真实阶段（校验 → 上传/解析 → 建表完成），不能用假进度条。 */
export function uploadDataset(
  file: File,
  handlers: { onPhase?: (phase: UploadPhase, ratio: number) => void } = {},
): Promise<DatasetDetail> {
  return new Promise((resolve, reject) => {
    handlers.onPhase?.('validating', 0)
    const form = new FormData()
    form.append('file', file)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}/datasets`)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        handlers.onPhase?.('parsing', Math.min(event.loaded / event.total, 1))
      }
    }
    xhr.onload = () => {
      try {
        const payload: unknown = JSON.parse(xhr.responseText || '{}')
        if (xhr.status >= 200 && xhr.status < 300) {
          handlers.onPhase?.('ready', 1)
          resolve(payload as DatasetDetail)
          return
        }
        const body = extractErrorBody(payload) ?? {
          code: `HTTP_${xhr.status}`,
          message: '上传失败',
          details: {},
          request_id: null,
        }
        reject(new ApiError(xhr.status, body))
      } catch {
        reject(
          new ApiError(xhr.status, {
            code: 'INVALID_RESPONSE',
            message: '服务端返回了无法解析的响应',
            details: {},
            request_id: null,
          }),
        )
      }
    }
    xhr.onerror = () =>
      reject(
        new ApiError(0, {
          code: 'NETWORK_ERROR',
          message: '网络中断，上传失败',
          details: {},
          request_id: null,
        }),
      )
    xhr.send(form)
  })
}

export const api = {
  health: () => apiFetch<HealthResponse>('/health'),
  config: () => apiFetch<ConfigResponse>('/config'),

  listDatasets: (limit = 20) => apiFetch<DatasetListResponse>(`/datasets?limit=${limit}`),
  getDataset: (id: string) => apiFetch<DatasetDetail>(`/datasets/${id}`),
  previewDataset: (id: string, limit = 20) =>
    apiFetch<DatasetPreview>(`/datasets/${id}/preview?limit=${limit}`),
  loadSample: (key: string) =>
    apiFetch<DatasetDetail & { reused: boolean }>(`/datasets/samples/${key}`, { method: 'POST' }),
  deleteDataset: (id: string) => apiFetch<void>(`/datasets/${id}`, { method: 'DELETE' }),

  createRun: (body: { dataset_id: string; question: string; mode?: RequestedMode }) =>
    apiFetch<CreateRunResponse>('/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  listRuns: (limit = 8) => apiFetch<RunListResponse>(`/runs?limit=${limit}`),
  getRun: (id: string) => apiFetch<RunDetail>(`/runs/${id}`),
  cancelRun: (id: string) => apiFetch<{ status: string; run_id: string }>(`/runs/${id}/cancel`, { method: 'POST' }),
  listEvents: (id: string, afterSeq = 0) =>
    apiFetch<EventsResponse>(`/runs/${id}/events?after_seq=${afterSeq}&limit=500`),
  getReport: (id: string) => apiFetch<ReportModel>(`/runs/${id}/report`),
  listArtifacts: (id: string) =>
    apiFetch<{ items: ArtifactInfo[]; total: number }>(`/runs/${id}/artifacts`),

  streamUrl: (id: string, afterSeq = 0) => `${API_BASE}/runs/${id}/stream?after_seq=${afterSeq}`,
  exportUrl: (id: string, format: 'html' | 'md') => `${API_BASE}/runs/${id}/export?format=${format}`,
}
