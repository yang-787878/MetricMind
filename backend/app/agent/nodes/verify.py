"""verify：执行结束后的闸门——有失败步骤或没有证据时，先尝试重规划。"""

from __future__ import annotations

from typing import Any

from ..run_context import RunContext
from ..state import AgentState


async def verify(state: AgentState, ctx: RunContext) -> dict[str, Any]:
    ctx.check_cancel()
    steps = state.get("steps") or []
    problematic = [
        step for step in steps if step.get("status") in {"failed", "skipped"}
    ]
    evidence_ids = ctx.evidence.all_ids()
    replan_count = int(state.get("replan_count") or 0)
    warnings = list(state.get("warnings") or [])

    can_replan = replan_count < ctx.budget.max_replans
    if (problematic or not evidence_ids) and can_replan:
        if problematic:
            warnings.append(
                f"{len(problematic)} 个步骤未成功，触发重新规划（第 {replan_count + 1} 次）"
            )
        else:
            warnings.append("没有产生任何证据，触发重新规划")
        return {"routing": "replan", "warnings": warnings}

    if problematic:
        warnings.append("仍有步骤未成功，且重规划次数已用尽")
        return {"routing": "report", "warnings": warnings, "status": "partial"}

    return {"routing": "report"}
