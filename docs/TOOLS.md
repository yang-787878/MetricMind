# 工具契约

> 所有工具输入/输出都是 Pydantic v2 模型（`extra="forbid"`），统一信封：
> `{"ok", "result_id", "data", "error", "meta"}`。`result_id` 只对产出数据的工具存在。
> 示例来自 `data/sample_sales.csv` 的真实执行（截断展示，行内容未改写）。

## 0. 统一信封

```json
{
  "ok": true,
  "result_id": "res_16babdc7d8b0",
  "data": {},
  "error": null,
  "meta": {
    "tool": "query_data",
    "duration_ms": 69,
    "rows_returned": 3,
    "truncated": false,
    "sql_executed": "SELECT ...",
    "warnings": []
  }
}
```

失败时：`ok=false`、`data=null`、`error={"code","message","hint","retryable","fields"}`。

| 工具 | 超时 | 单 run 上限 | result_id |
|---|---|---|---|
| `inspect_dataset` | 20s | 2 | 有 |
| `profile_dataset` | 25s | 2 | 有 |
| `query_data` | 30s | 6 | 有 |
| `calculate_metrics` | 25s | 8 | 有 |
| `create_chart` | 15s | 5 | 有 |
| `verify_result` | 20s | 3 | 无 |
| `export_report` | 20s | 2 | 无 |

## 1. `inspect_dataset`

输入：`dataset_id: str`、`sample_rows: 0..5`（默认 3）。

输出：`columns[{name,dtype,semantic_type,null_rate,distinct_count,sample_values}]`、`row_count`、
`column_count`、`time_range{column,min,max}|null`、`candidate_metrics[]`、`candidate_dimensions[]`、
`candidate_date_column`。

真实返回（列截断）：

```json
{"ok": true, "result_id": "res_fe2db6dc44d2", "data": {
  "columns": [
    {"name": "order_id", "dtype": "str", "semantic_type": "identifier", "null_rate": 0.0, "distinct_count": 7165, "sample_values": ["ORD-002981"]},
    {"name": "order_date", "dtype": "str", "semantic_type": "temporal", "null_rate": 0.0, "distinct_count": 281, "sample_values": ["2024-11-04"]}
  ],
  "row_count": 7180, "column_count": 14,
  "time_range": {"column": "order_date", "min": "2024-11-04T00:00:00", "max": "2025-09-30T00:00:00"},
  "candidate_metrics": ["units", "unit_price", "discount_pct", "revenue", "cost", "gross_profit", "returns_flag"],
  "candidate_dimensions": ["region", "channel", "product_category", "product_name", "customer_segment"],
  "candidate_date_column": "order_date"
}}
```

注：`order_id.distinct_count = 7165 < row_count = 7180`，正是 15 个重复订单号的体现。

## 2. `profile_dataset`

输入：`dataset_id`、`columns: string[] | null`、`include_outliers: bool = true`。

输出：`row_count`、`duplicate_rows`、`columns[{name,null_count,null_rate,distinct_count,min,max,mean,median,p95,zero_count,negative_count,outlier_count}]`、
`issues[{code,column,severity,message,affected_rows}]`、`method="IQR 1.5"`。

问题码固定集合：`NULL_VALUES`、`DUPLICATE_ROWS`、`ZERO_OR_NEGATIVE`、`OUTLIERS_IQR`、
`CONSTANT_COLUMN`、`HIGH_CARDINALITY`、`DATE_UNPARSEABLE`、`TYPE_MIXED`。

真实返回（仅 `region` 列）：

```json
{"ok": true, "result_id": "res_0a33d3b93c29", "data": {
  "row_count": 7180, "duplicate_rows": 0,
  "columns": [{"name": "region", "null_count": 120, "null_rate": 0.016713, "distinct_count": 4,
               "min": "East", "max": "West", "mean": null, "median": null, "p95": null,
               "zero_count": 0, "negative_count": 0, "outlier_count": 0}],
  "issues": [{"code": "NULL_VALUES", "column": "region", "severity": "warning",
              "message": "region 有 120 个空值（1.7%）", "affected_rows": 120}],
  "method": "IQR 1.5"
}}
```

## 3. `query_data`

输入：`dataset_id`、`sql`（≤4000 字符）、`max_rows`（1..500，默认 200）。

守卫规则（`services/sql_guard.py`，39 个单测覆盖）：

1. `sqlglot.parse(sql, read="duckdb")` 必须恰好 1 条语句（纯注释/分号不算语句）；
2. 顶层必须是 `SELECT`（允许 `WITH`/`UNION`）；
3. 禁止节点：`Insert/Update/Delete/Create/Drop/Alter/Attach/Detach/Copy/Pragma/Set/Command/Export/Load/Install/Use/Grant/TruncateTable/Transaction/Commit/Rollback`；
4. 表名白名单：只允许 `data`（CTE 名放行；`main.data` 允许；其他 schema/库名拒绝）；
5. 函数黑名单：`read_csv`/`read_parquet`/`glob`/`parquet_scan`/`sqlite_scan`/`httpfs`/`install`/`load`/`copy` …
6. 禁止 `information_schema` / `pg_catalog` / `duckdb_` 引用；
7. 无论是否写 LIMIT，统一包装为 `SELECT * FROM ( <sql> ) AS _mm_sub LIMIT <max_rows+1>`，多出 1 行判 `truncated`。

真实请求/返回：

```json
// 入参
{"dataset_id": "ds_...", "sql": "SELECT channel, COUNT(*) AS orders, ROUND(SUM(revenue),2) AS revenue FROM data GROUP BY channel ORDER BY revenue DESC", "max_rows": 3}

// 返回
{"ok": true, "result_id": "res_16babdc7d8b0", "data": {
  "columns": [{"name": "channel", "type": "VARCHAR"}, {"name": "orders", "type": "BIGINT"}, {"name": "revenue", "type": "DOUBLE"}],
  "rows": [["DTC", 3194, 8836181.77], ["Wholesale", 2536, 6885299.72], ["Outlet", 1450, 3981397.5]],
  "row_count": 3, "truncated": false,
  "sql_executed": "SELECT * FROM ( SELECT channel, COUNT(*) AS orders, ROUND(SUM(revenue),2) AS revenue FROM data GROUP BY channel ORDER BY revenue DESC ) AS _mm_sub LIMIT 4"
}}
```

被拦截示例：`DROP TABLE data` → `SQL_REJECTED`，`message="出于安全限制，只允许对 data 视图的只读查询：包含被禁止的语句类型 Drop"`，
`details.hint="请只提交只读查询"`。

## 4. `calculate_metrics`

```json
{
  "dataset_id": "ds_...",
  "metrics": [{
    "name": "monthly_revenue",
    "kind": "sum | mean | median | count | count_distinct | min | max | ratio | share | rate | growth_rate",
    "column": "revenue",
    "numerator": "returns_flag", "denominator": "order_id",
    "value_when": "returns_flag = 1",
    "group_by": ["month"],
    "date_column": "order_date",
    "period": "day | week | month",
    "agg": "sum | mean | count",
    "filters": [{"column": "channel", "op": "= | != | > | >= | < | <= | in | not_in | between | is_null | is_not_null", "value": "DTC"}],
    "sort": {"by": "value | key | <列名>", "order": "asc | desc"},
    "limit": 20
  }]
}
```

输出：`metrics[{name,kind,unit,value,groups[{key,value}],formula,inputs{rows_used,filters_applied},warnings}]`。

约束：

- `ratio`/`rate` 需要 `numerator+denominator` 或 `value_when`；
- `share` **必须** 有 `group_by`（占比相对总体）；
- `growth_rate` 必须 `column + date_column + period + agg` 齐备，取最后两个周期，`formula` 写明具体两期；
- `group_by` 可用真实列名或 `month/week/day` 周期（周期需要 `date_column`，缺省自动推断时间列）；
- 除零返回 `value=null` + `warnings=["分母为 0，比率无法计算"]`。

真实返回：

```json
{"ok": true, "result_id": "res_160348b9383e", "data": {"metrics": [{
  "name": "revenue_growth", "kind": "growth_rate", "unit": "ratio", "value": -0.18935012246585586,
  "groups": [{"key": {"month": "2025-08"}, "value": 2268526.18}, {"key": {"month": "2025-09"}, "value": 1838980.47}],
  "formula": "(2025-09 - 2025-08) / 2025-08，口径 SUM(revenue) 按 month(order_date)",
  "inputs": {"rows_used": 7180, "filters_applied": []}, "warnings": []
}]}}
```

## 5. `create_chart`

输入：`from_result_id`、`type`（bar/stacked_bar/line/area/scatter）、`x`、`y`、`series?`、
`title`（≤80）、`subtitle?`、`unit?`、`sort_by?`（x_asc/x_desc/y_asc/y_desc）、`limit_points`（≤500）。

硬约束：

- `from_result_id` 必须存在于当前 run 的证据池，否则 `RESULT_NOT_FOUND`；
- `x/y/series` 必须是该结果集真实存在的列，否则 `INVALID_COLUMN` + `available`；
- **没有**任何接收数据数组的参数——这是“图表必须基于真实数据”的代码级保证。

真实返回（数据截断到 2 行）：

```json
{"ok": true, "result_id": "res_c881ca32b129", "data": {
  "chart_id": "ch_e5f42f04", "type": "bar", "title": "各渠道收入",
  "x": {"key": "channel", "label": "channel", "type": "categorical"},
  "y": {"key": "revenue", "label": "revenue", "type": "numeric"},
  "series": null,
  "data": [{"channel": "DTC", "orders": 3194, "revenue": 8836181.77},
            {"channel": "Wholesale", "orders": 2536, "revenue": 6885299.72}],
  "source": {"result_id": "res_16babdc7d8b0", "tool": "query_data", "step_id": null, "row_count": 3, "truncated": false},
  "notes": []
}}
```

## 6. `verify_result`

输入：`run_id`、`claims[{claim_id,text,numbers[{value,unit}],evidence_ids[]}]`。

输出：`coverage`、`items[{claim_id,status,matched_evidence_id,matched_value,claimed_value,relative_delta,reason}]`、
`supported`/`unsupported`/`unverifiable`。

判定：0.5% 容差判 `supported`；有候选但未命中 → `unsupported` 并给最接近值；
证据存在但无任何数值 → `unverifiable`；无证据 → `unsupported("未提供证据")`。
`%` 与小数互认（-18.4% ↔ -0.184）。

真实返回（故意写错一个数字）：

```json
{"ok": true, "result_id": null, "data": {
  "coverage": 0.0,
  "items": [{"claim_id": "c1", "status": "unsupported", "matched_evidence_id": "res_160348b9383e",
             "matched_value": 2268526.18, "claimed_value": 19702878.99, "relative_delta": 7.685321,
             "reason": "接近但超差，最接近值 2268526.18"}],
  "supported": 0, "unsupported": 1, "unverifiable": 0
}}
```

## 7. `export_report`

输入：`run_id`、`format ∈ {html, md}`。运行结束前调用返回 `REPORT_NOT_READY`。

输出：`{artifact_id, format, size_bytes, download_url, generated_at}`。

- HTML：完全自包含（内联 CSS + 内联 SVG，无 `script`/`src`/`href`/`@import`）；
- Markdown：GFM 表格，图表以数据表呈现；
- 幂等：同一 run 同一格式复用 `art_<run尾号>_<format>`，重复导出覆盖同一文件。

## 8. 错误码（工具层）

| code | 可重试 | 触发 |
|---|---|---|
| `VALIDATION_ERROR` | 否 | 参数不合法（`fields` 明细） |
| `DATASET_NOT_FOUND` | 否 | 数据集不存在 |
| `RESULT_NOT_FOUND` | 否 | `from_result_id` 不在证据池 |
| `INVALID_COLUMN` | 否 | 列名不存在（`available`） |
| `SQL_REJECTED` | 否 | 守卫拦截（`reason` + `hint`） |
| `SQL_EXECUTION_ERROR` | 是（语法类） | DuckDB 报错（原文裁剪） |
| `TOOL_TIMEOUT` | 是 | 超时并 `interrupt()` |
| `BUDGET_EXCEEDED` | 否 | 超过单 run 工具上限 |
| `EMPTY_RESULT` | 是 | 查询 0 行（`ok=true` + warning） |
| `INTERNAL_TOOL_ERROR` | 是 | 未预期异常（已记日志） |
| `REPORT_NOT_READY` | 否 | 导出时报告尚未生成 |
