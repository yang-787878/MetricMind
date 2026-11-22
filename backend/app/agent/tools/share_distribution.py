"""share_distribution（§5.2）：把"占比变化分布"的口径写死在代码里。

为什么单独成一个工具：分布结论要求同一问题多次运行给出同一组数字。
如果交给模型现场写 SQL，过滤条件、分母、期间范围每次都可能被"等价改写"，
升降计数就会在 37/35 与 38/34 之间漂移。这里只接受结构化参数，SQL 由服务端拼装，
状态过滤按固定规则自动选择，保证同参数必然同结果。

返回的 `data` 里：
- `summary`：一行分布摘要（分组数、升/降/持平计数、min/中位数/max、前 N 名占比）；
- `rows`：逐分组明细（分组、两期值、两期占比、share_change），可直接给 create_chart。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ...errors import AppError, ErrorCode
from ...models.tool import ToolEnvelope, ToolMeta
from ...services import sql_guard
from ...services.jsonable import to_jsonable
from ..context import ToolContext

NAME = "share_distribution"
DESCRIPTION = (
    "计算两个期间（如 2017-08 vs 2018-08）各分组的销售额占比变化："
    "返回逐分组明细（两期销售额、两期占比、占比变化）+ 一行分布摘要"
    "（分组数、上升/下降/持平计数、最小值/中位数/最大值、前 N 名合计占比）。"
    "口径固定：两期分组并集、缺失一期按 0 计、占比=组销售额/当期合计；"
    "存在 order_status/status 列时自动排除 canceled/cancelled/unavailable。"
    "回答“分布/占比变化”类问题必须用本工具，不要手写等价 SQL。"
)
TIMEOUT_S = 30.0
MAX_CALLS = 2

STATUS_COLUMNS = ("order_status", "status")
EXCLUDED_STATUSES = ("canceled", "cancelled", "unavailable")


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    dimension: str = Field(min_length=1, description="分组列，如 product_category")
    metric: str = Field(min_length=1, description="求和指标列，如 item_total")
    period_column: str = Field(min_length=1, description="期间列，如 order_month")
    base_period: str = Field(min_length=1, description="基期取值，如 2017-08")
    current_period: str = Field(min_length=1, description="当期取值，如 2018-08")
    top_n: int = Field(default=5, ge=1, le=20, description="集中度取前 N 名")


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _status_filter(columns: list[str]) -> str:
    """固定规则：有状态列就排除常见的无效状态，不由模型决定。"""
    for name in STATUS_COLUMNS:
        if name in columns:
            statuses = ", ".join(_literal(status) for status in EXCLUDED_STATUSES)
            return f" AND {_quote(name)} NOT IN ({statuses})"
    return ""


def _detail_sql(args: Input, status: str) -> str:
    dim = _quote(args.dimension)
    metric = _quote(args.metric)
    period = _quote(args.period_column)
    base, current = _literal(args.base_period), _literal(args.current_period)
    return f"""WITH base AS (
  SELECT {dim} AS grp, {period} AS period, SUM({metric}) AS v
  FROM data
  WHERE {period} IN ({base}, {current}){status}
  GROUP BY 1, 2
), piv AS (
  SELECT grp,
         COALESCE(MAX(CASE WHEN period = {base} THEN v END), 0) AS base_v,
         COALESCE(MAX(CASE WHEN period = {current} THEN v END), 0) AS cur_v
  FROM base GROUP BY grp
), tot AS (
  SELECT SUM(base_v) AS base_total, SUM(cur_v) AS cur_total FROM piv
)
SELECT grp AS {dim}, base_v, cur_v,
       CASE WHEN base_total > 0 THEN base_v / base_total ELSE 0 END AS base_share,
       CASE WHEN cur_total > 0 THEN cur_v / cur_total ELSE 0 END AS cur_share,
       (CASE WHEN cur_total > 0 THEN cur_v / cur_total ELSE 0 END)
     - (CASE WHEN base_total > 0 THEN base_v / base_total ELSE 0 END) AS share_change
FROM piv CROSS JOIN tot
ORDER BY share_change DESC"""


def _summary_sql(args: Input, status: str) -> str:
    top_n = int(args.top_n)
    return f"""WITH detail AS (
  {_detail_sql(args, status)}
), r AS (
  SELECT share_change, base_v, cur_v,
         ROW_NUMBER() OVER (ORDER BY share_change DESC) AS rk
  FROM detail
)
SELECT COUNT(*) AS group_count,
       SUM(CASE WHEN share_change > 0 THEN 1 ELSE 0 END) AS up_count,
       SUM(CASE WHEN share_change < 0 THEN 1 ELSE 0 END) AS down_count,
       SUM(CASE WHEN share_change = 0 THEN 1 ELSE 0 END) AS flat_count,
       SUM(CASE WHEN base_v = 0 THEN 1 ELSE 0 END) AS only_in_current,
       SUM(CASE WHEN cur_v = 0 THEN 1 ELSE 0 END) AS only_in_base,
       MIN(share_change) AS min_share_change,
       MEDIAN(share_change) AS median_share_change,
       MAX(share_change) AS max_share_change,
       SUM(CASE WHEN share_change > 0 THEN share_change ELSE 0 END) AS positive_sum,
       SUM(CASE WHEN rk <= {top_n} AND share_change > 0 THEN share_change ELSE 0 END)
           AS top_n_positive,
       CASE WHEN SUM(CASE WHEN share_change > 0 THEN share_change ELSE 0 END) > 0
            THEN SUM(CASE WHEN rk <= {top_n} AND share_change > 0 THEN share_change ELSE 0 END)
                 / SUM(CASE WHEN share_change > 0 THEN share_change ELSE 0 END)
       END AS top_n_share
FROM r"""


async def run(ctx: ToolContext, args: Input) -> ToolEnvelope:
    frame = await ctx.frame(args.dataset_id)
    columns = [str(name) for name in frame.columns]
    for role, name in (
        ("dimension", args.dimension),
        ("metric", args.metric),
        ("period_column", args.period_column),
    ):
        if name not in columns:
            raise AppError(
                ErrorCode.INVALID_COLUMN,
                f"{role} 列 {name} 不在数据集 {args.dataset_id} 中",
                details={"column": name, "role": role, "available": columns},
                hint="请从 available 中选择真实存在的列名",
            )

    status = _status_filter(columns)
    detail_sql = sql_guard.validate_sql(_detail_sql(args, status))
    summary_sql = sql_guard.validate_sql(_summary_sql(args, status))

    detail = await ctx.engine.execute(
        run_id=ctx.run_id,
        dataset_id=args.dataset_id,
        frame_factory=lambda: frame,
        sql=detail_sql,
        max_rows=500,
        timeout_s=TIMEOUT_S,
    )
    summary_outcome = await ctx.engine.execute(
        run_id=ctx.run_id,
        dataset_id=args.dataset_id,
        frame_factory=lambda: frame,
        sql=summary_sql,
        max_rows=5,
        timeout_s=TIMEOUT_S,
    )

    summary_names = [str(column.get("name")) for column in summary_outcome.columns]
    summary_rows = summary_outcome.rows or []
    summary: dict[str, Any] = (
        {name: to_jsonable(value) for name, value in zip(summary_names, summary_rows[0])}
        if summary_rows
        else {}
    )

    data: dict[str, Any] = {
        # summary 放最前：evidence 提取数值时按遍历顺序，避免被明细行挤出截断窗口
        "summary": summary,
        "dimension": args.dimension,
        "metric": args.metric,
        "period_column": args.period_column,
        "base_period": args.base_period,
        "current_period": args.current_period,
        "definition": (
            "并集分组、缺失一期按 0 计；占比=组销售额/当期合计；"
            "share_change=当期占比−基期占比"
        ),
        "status_filter": status.strip(" AND") or None,
        "columns": detail.columns,
        "rows": [[to_jsonable(value) for value in row] for row in (detail.rows or [])],
        "row_count": detail.row_count,
        "truncated": detail.truncated,
    }

    warnings: list[str] = []
    if detail.row_count == 0:
        warnings.append("两个期间没有可比较的分组，请检查期间取值")
    if summary.get("group_count", 0) and summary.get("positive_sum") in (0, 0.0, None):
        warnings.append("所有分组占比变化均不为正，集中度指标为空")

    return ToolEnvelope.success(
        tool=NAME,
        data=data,
        meta=ToolMeta(
            tool=NAME,
            duration_ms=max(detail.duration_ms, summary_outcome.duration_ms),
            rows_returned=detail.row_count,
            truncated=detail.truncated,
            sql_executed=detail_sql,
            warnings=warnings,
        ),
    )
