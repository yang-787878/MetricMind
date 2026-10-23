# API 契约

Base URL：`http://127.0.0.1:8000/api`　·　交互式文档：`http://127.0.0.1:8000/docs`

所有响应均为 JSON（导出接口除外）。错误统一信封：

```json
{"error": {"code": "INVALID_COLUMN", "message": "列 nope 不存在",
           "details": {"column": "nope", "available": ["revenue", "cost"]}, "request_id": "req_ab12cd34ef56"}}
```

每个响应都带 `X-Request-ID` 头，可用于对照服务端 JSON 日志排查。

## 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 自检：`{status, version, db, llm_mode, model}` |
| GET | `/config` | 限额与示例入口：`{llm_mode, model, limits, samples[]}`（不含任何密钥） |
| POST | `/datasets` | multipart `file` → `201 DatasetDetail` |
| POST | `/datasets/samples/{key}` | 载入示例（幂等，`reused=true`） |
| GET | `/datasets?limit&offset` | 列表 `{items, total}` |
| GET | `/datasets/{id}` | 详情（含 columns 与 quality） |
| GET | `/datasets/{id}/preview?limit=50` | 预览 `{columns, rows, total_rows}` |
| DELETE | `/datasets/{id}` | 被 run 引用时 `409 DATASET_IN_USE` |
| POST | `/runs` | `{dataset_id, question(3..500), mode?}` → `201 {run_id,status,mode,stream_url}` |
| GET | `/runs?dataset_id&status&limit` | 列表 `{items,total}` |
| GET | `/runs/{id}` | 详情（plan/steps/tool_calls/verification/report/usage/budget） |
| POST | `/runs/{id}/cancel` | `202 {status:"cancelling"}`；已结束 → `409` |
| GET | `/runs/{id}/events?after_seq&limit` | 轮询 `{events[], run_id, status, is_terminal}` |
| GET | `/runs/{id}/stream?after_seq` | SSE（`Last-Event-ID` 或 `?after_seq=` 续播） |
| GET | `/runs/{id}/report` | `ReportModel`；未完成 → `409 REPORT_NOT_READY` |
| GET | `/runs/{id}/export?format=html\|md` | 文件流（`Content-Disposition: attachment`），不存在则实时生成 |
| GET | `/runs/{id}/artifacts` | `{items: ArtifactInfo[], total}` |

**并发与限流**：全局 `Semaphore(2)` 限制同时运行的 run（超出进 `queued`）；`POST /runs` 按 IP 6 次/分钟，
超限返回 `429` + `details.retry_after_s`。

## curl 示例

```bash
# 健康检查
curl -s http://127.0.0.1:8000/api/health

# 上传 CSV
curl -s -X POST http://127.0.0.1:8000/api/datasets \
  -F "file=@data/sample_sales.csv"

# 载入示例（幂等）
curl -s -X POST http://127.0.0.1:8000/api/datasets/samples/sales

# 发起分析（demo 模式无需 Key）
curl -s -X POST http://127.0.0.1:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{"dataset_id":"ds_xxx","question":"为什么 2025 年 9 月销售额相比 6–8 月下降了？","mode":"demo"}'

# 轮询事件（SSE 不可用时）
curl -s "http://127.0.0.1:8000/api/runs/run_xxx/events?after_seq=0"

# 实时流（-N 关闭缓冲）
curl -N "http://127.0.0.1:8000/api/runs/run_xxx/stream?after_seq=0"

# 报告与导出
curl -s http://127.0.0.1:8000/api/runs/run_xxx/report
curl -s -OJ "http://127.0.0.1:8000/api/runs/run_xxx/export?format=html"

# 取消
curl -s -X POST http://127.0.0.1:8000/api/runs/run_xxx/cancel
```

## SSE 帧

```text
id: 12
event: tool_call_succeeded
data: {"seq":12,"run_id":"run_x","ts":"2026-10-22T10:00:03.120Z","type":"tool_call_succeeded","step_id":"s2","payload":{"call_id":"call_s2_1","tool":"calculate_metrics","result_id":"res_16babdc7d8b0","duration_ms":36,"rows_returned":10,"data_preview":{"metrics":[{"name":"revenue_growth","value":-0.1893,"groups":[…]}]}}}

: ping
```

- 每 15s 一条注释心跳 `: ping`；
- 事件类型共 16 种（见 `backend/app/models/events.py` 与 `frontend/src/types/events.ts`）；
- 终态（`run_succeeded` / `run_failed` / `run_cancelled`）后服务端主动关闭；
- 断线重连带上 `Last-Event-ID` 即可续播，服务端会用 `after_seq` 补齐。

## 关键响应字段

`RunDetail`：

```json
{
  "run_id": "run_x", "dataset_id": "ds_x", "question": "...", "status": "succeeded", "mode": "demo",
  "plan": {"objective": "...", "steps": [...]},
  "steps": [{"step_id": "s1", "tool": "calculate_metrics", "status": "succeeded",
             "tool_calls": [{"call_id": "call_s1_1", "result_id": "res_x", "duration_ms": 43, "arguments": {}, "result": {}}]}],
  "verification": {"coverage": 1.0, "supported": 3, "unsupported": 0, "unverifiable": 0, "items": [...]},
  "report": {"title": "...", "kpis": [...], "claims": [...], "methodology": [...], "limitations": [...]},
  "usage": {"llm_calls": 0, "steps_used": 5, "tool_calls_used": 8, "replans_used": 0},
  "budget": {"max_steps": 10, "max_tool_calls": 16, "max_replans": 2, "timeout_seconds": 240},
  "warnings": []
}
```

`ReportModel`：`title / generated_at / mode / status / headline / kpis[] / sections[] / charts[] /
claims[] / methodology[] / data_quality[] / limitations[] / next_steps[] / verification / narrative_source`。

`DatasetDetail`：`row_count / column_count / size_bytes / checksum / encoding / columns[ColumnProfile] /
quality{duplicate_row_count, row_count_after_dedup, issues[]}`。
