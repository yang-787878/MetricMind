"""inspect：固定前置，必跑 inspect_dataset + profile_dataset（不由模型决定）。"""

from __future__ import annotations

from typing import Any

from ...errors import AppError, ErrorCode
from ..run_context import RunContext
from ..state import AgentState


async def inspect(state: AgentState, ctx: RunContext) -> dict[str, Any]:
    ctx.check_cancel()
    dataset_id = state["dataset_id"]

    inspected = await ctx.call_tool(
        "inspect_dataset", {"dataset_id": dataset_id, "sample_rows": 3}, step_id="inspect"
    )
    if not inspected.ok or not isinstance(inspected.data, dict):
        error = inspected.error
        raise AppError(
            error.code if error else ErrorCode.INTERNAL_TOOL_ERROR,
            error.message if error else "字段探查失败",
            details={"hint": error.hint if error else None},
        )

    profiled = await ctx.call_tool(
        "profile_dataset",
        {"dataset_id": dataset_id, "include_outliers": True},
        step_id="inspect",
    )
    issues: list[dict[str, Any]] = []
    if profiled.ok and isinstance(profiled.data, dict):
        issues = list(profiled.data.get("issues") or [])
    else:
        error = profiled.error
        if error and error.code == ErrorCode.INVALID_COLUMN.value:
            raise AppError(
                ErrorCode.INVALID_COLUMN,
                error.message,
                details={"fields": error.fields or []},
            )
        # 剖析失败不阻断分析，但必须留下痕迹
        issues = []

    columns = inspected.data.get("columns") or []
    meta = {
        **state["dataset_meta"],
        "columns": columns,
        "candidate_metrics": inspected.data.get("candidate_metrics") or [],
        "candidate_dimensions": inspected.data.get("candidate_dimensions") or [],
        "candidate_date_column": inspected.data.get("candidate_date_column"),
        "time_range": inspected.data.get("time_range"),
        "quality": issues,
    }
    field_summary = {
        "row_count": inspected.data.get("row_count"),
        "column_count": inspected.data.get("column_count"),
        "columns": columns,
        "candidate_metrics": meta["candidate_metrics"],
        "candidate_dimensions": meta["candidate_dimensions"],
        "candidate_date_column": meta["candidate_date_column"],
        "time_range": meta["time_range"],
        "quality_issue_count": len(issues),
    }

    await ctx.emit(
        "dataset_inspected",
        {
            "row_count": int(meta.get("row_count") or 0),
            "column_count": int(meta.get("column_count") or 0),
            "quality_issue_count": len(issues),
        },
        step_id="inspect",
    )
    return {"dataset_meta": meta, "field_summary": field_summary, "quality": issues}
