"""plan：生成 StructuredPlan（Demo 用模板，Live 用 LLM + 一次修复重试）。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from ...errors import AppError, ErrorCode
from ...llm.prompt_loader import load_prompt
from ...models.plan import StructuredPlan
from .. import demo_planner
from ..registry import tool_schemas
from ..run_context import RunContext
from ..state import AgentState
from ._steps import step_records_from_plan, with_dataset_id

SYSTEM_PROMPT = load_prompt("plan")


def _plan_payload(state: AgentState, ctx: RunContext) -> str:
    meta = state.get("dataset_meta") or {}
    payload = {
        "question": state["question"],
        "dataset": {
            "row_count": meta.get("row_count"),
            "column_count": meta.get("column_count"),
            "columns": [
                {
                    "name": column.get("name"),
                    "dtype": column.get("dtype"),
                    "semantic_type": column.get("semantic_type"),
                    "null_rate": column.get("null_rate"),
                    "distinct_count": column.get("distinct_count"),
                    "sample_values": column.get("sample_values"),
                }
                for column in meta.get("columns", [])
            ],
        },
        "tools": tool_schemas(planner_only=True),
        "budget": ctx.budget.model_dump(mode="json"),
    }
    return json.dumps(payload, ensure_ascii=False)


def _parse_plan(text: str) -> StructuredPlan:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
    data = json.loads(cleaned)
    data.pop("plan_version", None)
    return StructuredPlan.model_validate(data)


async def llm_plan(
    state: AgentState, ctx: RunContext, feedback: str = ""
) -> StructuredPlan:
    base_prompt = _plan_payload(state, ctx)
    if feedback:
        base_prompt = base_prompt + "\n\n# 上一版计划的失败信息\n" + feedback
    last_error = ""
    truncated = False
    # 计划是最大的结构化输出：第一次用配置上限，若被截断则翻倍再试一次
    base_cap = ctx.settings.llm_max_output_tokens
    for attempt in range(2):
        user = base_prompt
        if attempt and last_error:
            user = (
                base_prompt
                + "\n\n# 上一次输出的问题\n"
                + last_error
                + "\n请严格按 schema 重新输出一个合法 JSON。"
            )
        cap = base_cap if attempt == 0 else base_cap * 2
        result = await ctx.llm_call(
            purpose="plan", system=SYSTEM_PROMPT, user=user, max_tokens=cap
        )
        if result.truncated:
            truncated = True
            last_error = (
                f"上一次输出被 max_tokens={cap} 截断（finish_reason=length），"
                "JSON 不完整。请减少步骤数量、缩短 steps 的 title/intent/expected_output，"
                "并确保只输出一个紧凑的 JSON 对象。"
            )
            continue
        try:
            plan = _parse_plan(result.text)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)[:800]
            continue
        if plan.narrative_source is None:
            plan.narrative_source = "llm"
        return plan
    raise AppError(
        ErrorCode.LLM_INVALID_OUTPUT,
        (
            "模型输出被截断，未能产出完整计划（max_tokens 已尝试翻倍）"
            if truncated
            else "模型连续两次未能产出合法的分析计划"
        ),
        details={"last_error": last_error[:800], "truncated": truncated},
        hint=(
            "可在 .env 增大 LLM_MAX_OUTPUT_TOKENS，或更换输出更简洁的模型"
            if truncated
            else "可切换到 Demo 模式，或更换模型后重试"
        ),
    )


def _validate_steps(plan: StructuredPlan, ctx: RunContext) -> list[str]:
    """校验工具名；步骤数超过预算时截断而不是整体失败（预算应由执行器兜底）。"""
    known_tools = {schema["name"] for schema in tool_schemas(planner_only=True)}
    unknown = [step.tool for step in plan.steps if step.tool not in known_tools]
    if unknown:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"计划引用了未知工具：{unknown}",
            details={"available": sorted(known_tools)},
        )
    warnings: list[str] = []
    if len(plan.steps) > ctx.budget.max_steps:
        dropped = len(plan.steps) - ctx.budget.max_steps
        plan.steps = plan.steps[: ctx.budget.max_steps]
        warnings.append(f"计划含 {len(plan.steps) + dropped} 步，超过预算，已截断 {dropped} 步")
    return warnings


async def plan(state: AgentState, ctx: RunContext) -> dict[str, Any]:
    ctx.check_cancel()
    if state.get("mode") == "demo":
        raw = demo_planner.build_plan(
            question=state["question"], dataset_meta=state.get("dataset_meta") or {}
        )
        structured = StructuredPlan.model_validate(raw)
        structured.narrative_source = "template"
    else:
        structured = await llm_plan(state, ctx)

    plan_warnings = _validate_steps(structured, ctx)
    for step in structured.steps:
        step.tool_args_hint = with_dataset_id(
            step.tool, dict(step.tool_args_hint or {}), state["dataset_id"]
        )
    plan_dict = structured.model_dump(mode="json")
    steps = step_records_from_plan(plan_dict)

    await ctx.emit(
        "plan_created",
        {
            "plan_version": int(plan_dict.get("plan_version", 1)),
            "objective": plan_dict["objective"],
            "steps": [
                {"step_id": step["step_id"], "title": step["title"], "tool": step["tool"]}
                for step in steps
            ],
        },
    )
    return {
        "plan": plan_dict,
        "plan_version": int(plan_dict.get("plan_version", 1)),
        "steps": steps,
        "step_index": 0,
        "failed_step": None,
        "warnings": list(state.get("warnings") or []) + plan_warnings,
    }
