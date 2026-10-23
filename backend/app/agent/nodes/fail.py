"""fail：不可恢复的步骤错误 → 直接进入 finalize(failed)，并保留可读原因。"""

from __future__ import annotations

from typing import Any

from ..run_context import RunContext
from ..state import AgentState


async def fail(state: AgentState, ctx: RunContext) -> dict[str, Any]:
    warnings = list(state.get("warnings") or [])
    error = state.get("error") or {
        "code": "RUN_FAILED",
        "message": "分析未能完成",
        "hint": "可重试一次或换一个问题",
    }
    messages = [f"步骤 {step.get('step_id')} 失败：{(step.get('error') or {}).get('message')}" for step in state.get("steps") or [] if step.get("status") == "failed"]
    warnings.extend(messages)
    return {"status": "failed", "error": error, "warnings": warnings, "routing": "finalize"}
