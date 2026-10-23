/**
 * 与后端 Pydantic 模型一一对应的类型契约（§4 / §8）。
 * 字段名必须与 backend/app/models/*.py 完全一致，禁止前端自造字段。
 */

export type RunStatus = 'queued' | 'running' | 'succeeded' | 'partial' | 'failed' | 'cancelled'
export type RunMode = 'live' | 'demo'
export type RequestedMode = 'auto' | 'live' | 'demo'
export type StepStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped'
export type ToolStatus = 'ok' | 'error' | 'timeout' | 'rejected'
export type VerificationStatus = 'supported' | 'unsupported' | 'unverifiable'
export type SemanticType = 'numeric' | 'temporal' | 'categorical' | 'identifier' | 'text' | 'boolean'
export type ChartType = 'bar' | 'stacked_bar' | 'line' | 'area' | 'scatter'
export type SourceKind = 'upload' | 'sample'
export type IssueSeverity = 'info' | 'warning' | 'error'

export interface ColumnStats {
  min: number | null
  max: number | null
  mean: number | null
  median: number | null
}

export interface ColumnProfile {
  name: string
  original_name: string | null
  dtype: string
  semantic_type: SemanticType
  null_rate: number
  distinct_count: number
  sample_values: unknown[]
  stats: ColumnStats | null
}

export interface QualityIssue {
  code: string
  column: string | null
  severity: IssueSeverity
  message: string
  affected_rows: number | null
}

export interface DatasetQuality {
  duplicate_row_count: number
  row_count_after_dedup: number
  issues: QualityIssue[]
}

export interface DatasetSummary {
  dataset_id: string
  name: string
  original_filename: string
  source: SourceKind
  row_count: number
  column_count: number
  size_bytes: number
  created_at: string
  checksum: string | null
}

export interface DatasetDetail extends DatasetSummary {
  columns: ColumnProfile[]
  quality: DatasetQuality
  encoding: string | null
}

export interface DatasetPreview {
  columns: { name: string; type: string }[]
  rows: unknown[][]
  total_rows: number
}

export interface SampleDataset {
  key: string
  name: string
  description: string
  filename: string
  row_count: number | null
  recommended_questions: string[]
}

export interface PlanStep {
  step_id: string
  title: string
  intent: string
  tool: string
  tool_args_hint: Record<string, unknown>
  expected_output: string
  validation: string
}

export interface StructuredPlan {
  objective: string
  required_fields: string[]
  assumptions: string[]
  steps: PlanStep[]
  risks: string[]
  out_of_scope: string[]
  plan_version: number
  narrative_source: string | null
}

export interface ToolErrorInfo {
  code: string
  message: string
  hint: string | null
  retryable: boolean
  fields: { loc?: string; msg?: string; type?: string }[] | null
}

export interface ToolMeta {
  tool: string
  duration_ms: number
  rows_returned: number | null
  truncated: boolean
  sql_executed: string | null
  warnings: string[]
}

export interface ToolEnvelope<T = unknown> {
  ok: boolean
  result_id: string | null
  data: T | null
  error: ToolErrorInfo | null
  meta: ToolMeta
}

export interface ToolCallRecord {
  call_id: string
  step_id: string | null
  tool: string
  status: ToolStatus
  arguments: Record<string, unknown>
  result_id: string | null
  duration_ms: number
  result: Record<string, unknown> | null
  error: ToolErrorInfo | null
  warnings: string[]
  created_at: string
}

export interface VerificationItem {
  claim_id: string
  status: VerificationStatus
  matched_evidence_id: string | null
  matched_value: number | null
  claimed_value: number | null
  relative_delta: number | null
  reason: string
}

export interface VerificationResult {
  coverage: number
  items: VerificationItem[]
  supported: number
  unsupported: number
  unverifiable: number
}

export interface ChartAxis {
  key: string
  label: string
  type: SemanticType
}

export interface ChartSeriesRef {
  key: string
  label: string
}

export interface ChartSource {
  result_id: string
  tool: string
  step_id: string | null
  row_count: number
  truncated: boolean
}

export interface ChartSpec {
  chart_id: string
  type: ChartType
  title: string
  subtitle: string | null
  unit: string | null
  x: ChartAxis
  y: ChartAxis
  series: ChartSeriesRef | null
  data: Record<string, unknown>[]
  source: ChartSource
  notes: string[]
}

export interface Kpi {
  label: string
  value: number | null
  unit: string | null
  delta: number | null
  delta_label: string | null
  evidence_ids: string[]
  display_value: string | null
}

export interface ReportSection {
  id: string
  heading: string
  body: string
  evidence_ids: string[]
  degraded: boolean
}

export interface ClaimNumber {
  value: number
  unit: string
}

export interface Claim {
  claim_id: string
  text: string
  numbers: ClaimNumber[]
  display_numbers: string[]
  evidence_ids: string[]
  status: VerificationStatus
  reason: string | null
  matched_value: number | null
}

export interface MethodologyItem {
  step_id: string
  description: string
  tool: string
  result_id: string | null
  sql: string | null
  formula: string | null
}

export interface DataQualityNote {
  code: string
  severity: IssueSeverity
  message: string
  column: string | null
}

export interface VerificationSummary {
  coverage: number
  supported: number
  unsupported: number
  unverifiable: number
}

export interface ReportModel {
  run_id: string
  title: string
  generated_at: string
  mode: RunMode
  status: RunStatus
  headline: string
  kpis: Kpi[]
  sections: ReportSection[]
  charts: string[]
  claims: Claim[]
  methodology: MethodologyItem[]
  data_quality: DataQualityNote[]
  limitations: string[]
  next_steps: string[]
  verification: VerificationSummary | null
  narrative_source: string
}

export interface Budget {
  max_steps: number
  max_tool_calls: number
  max_replans: number
  timeout_seconds: number
}

export interface Usage {
  llm_calls: number
  prompt_tokens: number
  completion_tokens: number
  steps_used: number
  tool_calls_used: number
  replans_used: number
}

export interface StepRecord {
  step_id: string
  title: string
  intent: string
  tool: string
  tool_args_hint: Record<string, unknown>
  status: StepStatus
  expected_output: string
  validation: string
  summary: string
  tool_calls: ToolCallRecord[]
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  error: Record<string, unknown> | null
}

export interface RunError {
  code: string
  message: string
  hint: string | null
}

export interface RunSummary {
  run_id: string
  dataset_id: string
  dataset_name: string | null
  question: string
  status: RunStatus
  mode: RunMode
  model: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
}

export interface RunDetail extends RunSummary {
  usage: Usage
  budget: Budget
  plan: StructuredPlan | null
  steps: StepRecord[]
  verification: VerificationResult | null
  report: ReportModel | null
  error: RunError | null
  warnings: string[]
}

export interface RunListResponse {
  items: RunSummary[]
  total: number
}

export interface DatasetListResponse {
  items: DatasetSummary[]
  total: number
}

export interface CreateRunResponse {
  run_id: string
  status: RunStatus
  mode: RunMode
  stream_url: string
}

export interface HealthResponse {
  status: string
  version: string
  db: string
  llm_mode: RunMode
  model: string
}

export interface Limits {
  max_upload_mb: number
  max_rows: number
  max_steps: number
  max_tool_calls: number
  max_replans: number
  run_timeout_s: number
}

export interface ConfigResponse {
  llm_mode: RunMode
  model: string
  limits: Limits
  samples: SampleDataset[]
}

export interface ArtifactInfo {
  artifact_id: string
  run_id: string
  kind: string
  format: string
  size_bytes: number
  download_url: string
  created_at: string
}

export interface ApiErrorBody {
  code: string
  message: string
  details: Record<string, unknown> & {
    hint?: string
    available?: string[]
    fields?: { loc?: string; msg?: string; type?: string }[]
  }
  request_id: string | null
}
