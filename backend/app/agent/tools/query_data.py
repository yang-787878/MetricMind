"""query_data（§5.2(3)）：受控只读 SQL，守卫在进 DuckDB 之前执行。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ...models.tool import ToolEnvelope, ToolMeta
from ...services import sql_guard
from ..context import ToolContext

NAME = "query_data"
DESCRIPTION = (
    "对当前数据集执行一条只读 SELECT（视图名 data）。支持 WHERE/GROUP BY/ORDER BY/窗口函数/CTE。"
    "禁止多语句与任何写操作，禁止读取外部文件；结果最多 max_rows 行并自动标记 truncated。"
)
TIMEOUT_S = 30.0
MAX_CALLS = 6


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    sql: str = Field(min_length=1, max_length=sql_guard.MAX_SQL_CHARS)
    max_rows: int = Field(default=200, ge=1, le=500)


async def run(ctx: ToolContext, args: Input) -> ToolEnvelope:
    sql = sql_guard.validate_sql(args.sql)
    frame = await ctx.frame(args.dataset_id)
    outcome = await ctx.engine.execute(
        run_id=ctx.run_id,
        dataset_id=args.dataset_id,
        frame_factory=lambda: frame,
        sql=sql,
        max_rows=args.max_rows,
        timeout_s=TIMEOUT_S,
    )
    data = {
        "columns": outcome.columns,
        "rows": outcome.rows,
        "row_count": outcome.row_count,
        "truncated": outcome.truncated,
        "sql_executed": outcome.sql_executed,
    }
    warnings = list(outcome.warnings)
    if outcome.row_count == 0:
        warnings.append("查询返回 0 行，请检查筛选条件")
    return ToolEnvelope.success(
        tool=NAME,
        data=data,
        meta=ToolMeta(
            tool=NAME,
            duration_ms=outcome.duration_ms,
            rows_returned=outcome.row_count,
            truncated=outcome.truncated,
            sql_executed=outcome.sql_executed,
            warnings=warnings,
        ),
    )
