"""intake：校验 question / dataset 存在，发 run_started。"""

from __future__ import annotations

from typing import Any

from ...errors import AppError, ErrorCode, dataset_not_found
from ..run_context import RunContext
from ..state import AgentState


async def intake(state: AgentState, ctx: RunContext) -> dict[str, Any]:
    ctx.check_cancel()
    dataset_id = state["dataset_id"]
    row = ctx.store.get_dataset(dataset_id)
    if row is None:
        raise dataset_not_found(dataset_id)

    question = (state.get("question") or "").strip()
    if len(question) < 3:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "问题至少 3 个字符",
            details={"question": question},
        )

    meta = {
        "dataset_id": dataset_id,
        "name": row["name"],
        "row_count": row["row_count"],
        "column_count": row["column_count"],
        "quality": [],
    }
    await ctx.emit(
        "run_started",
        {"model": ctx.model_name, "budget": ctx.budget.model_dump(mode="json")},
    )
    return {"dataset_meta": meta, "status": "running"}
