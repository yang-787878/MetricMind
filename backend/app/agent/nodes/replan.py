"""replan：修正计划（Demo 移除失败步骤，Live 用修复提示词重写计划）。"""

from __future__ import annotations

import json
from typing import Any

from ...logging_conf import get_logger
from .. import demo_planner
from ..run_context import RunContext
from ..state import AgentState
from ._steps import step_records_from_plan, with_dataset_id
from .plan import llm_plan

logger = get_logger(__name__)


async def _demo_replan(state: AgentState) -> dict[str, Any]:
    plan = demo_planner.build_plan(
        question=state["question"], dataset_meta=state.get("dataset_meta") or {}
    )
    broken_tools = {
        str(step.get("tool"))
        for step in state.get("steps") or []
        if step.get("status") in {"failed", "skipped"}
    }
    plan["steps"] = [step for step in plan["steps"] if step["tool"] not in broken_tools]
    plan["plan_version"] = int(state.get("plan_version") or 1) + 1
    return plan


async def replan(state: AgentState, ctx: RunContext) -> dict[str, Any]:
    ctx.check_cancel()
    replan_count = int(state.get("replan_count") or 0)
    warnings = list(state.get("warnings") or [])
    problematic = [
        step for step in state.get("steps") or [] if step.get("status") in {"failed", "skipped"}
    ]

    if replan_count >= ctx.budget.max_replans:
        await ctx.emit(
            "budget_warning",
            {"kind": "max_replans", "used": replan_count, "limit": ctx.budget.max_replans},
        )
        warnings.append("重规划次数已用尽，直接生成部分结果报告")
        return {"routing": "report", "status": "partial", "warnings": warnings}

    feedback = json.dumps(
        [
            {
                "step_id": step.get("step_id"),
                "tool": step.get("tool"),
                "error": step.get("error"),
            }
            for step in problematic
        ],
        ensure_ascii=False,
    )
    if state.get("mode") == "demo":
        new_plan = await _demo_replan(state)
    else:
        structured = await llm_plan(
            state,
            ctx,
            feedback=(
                "上一版计划中以下步骤失败，请改写参数或换用其它工具："
                + feedback
                + "。失败步骤使用的工具请谨慎复用。"
            ),
        )
        new_plan = structured.model_dump(mode="json")

    if not new_plan.get("steps"):
        warnings.append("重规划没有产出可执行步骤，直接生成部分结果报告")
        return {"routing": "report", "status": "partial", "warnings": warnings}

    await ctx.emit(
        "replan_requested",
        {
            "reason": (
                f"{len(problematic)} 个步骤失败："
                + ", ".join(str(step.get("step_id")) for step in problematic)
                if problematic
                else "没有产生可用的证据"
            ),
            "replan_count": replan_count + 1,
            "failed_step_id": problematic[0].get("step_id") if problematic else None,
        },
    )
    ctx.usage.replans_used = replan_count + 1
    # 与 plan() 一致：dataset_id 由服务端注入。漏掉这一步时模型写的 "$dataset_id"
    # 会原样进入工具，被误判为跨数据集访问并触发不可恢复的 DATASET_NOT_FOUND。
    for step in new_plan.get("steps") or []:
        step["tool_args_hint"] = with_dataset_id(
            str(step.get("tool") or ""),
            dict(step.get("tool_args_hint") or {}),
            state["dataset_id"],
        )
    steps = step_records_from_plan(new_plan)
    logger.info(
        "run_replanned",
        extra={"run_id": ctx.run_id, "plan_version": new_plan.get("plan_version"), "steps": len(steps)},
    )
    return {
        "plan": new_plan,
        "plan_version": int(new_plan.get("plan_version") or 2),
        "steps": steps,
        "step_index": 0,
        "failed_step": None,
        "replan_count": replan_count + 1,
        "routing": "execute",
        "warnings": warnings,
    }
