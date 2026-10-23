"""repair_step：单步失败后尝试修正参数（Demo 用模板，Live 用修复提示词）。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from ...llm.prompt_loader import load_prompt
from ...logging_conf import get_logger
from .. import demo_planner
from ..registry import tool_schemas
from ..run_context import RunContext
from ..state import AgentState
from ._steps import now_iso, with_dataset_id

logger = get_logger(__name__)

SYSTEM_PROMPT = load_prompt("repair")
MAX_REPAIRS = 2
REPAIRABLE_CODES = {
    "INVALID_COLUMN",
    "EMPTY_RESULT",
    "SQL_REJECTED",
    "VALIDATION_ERROR",
    "SQL_EXECUTION_ERROR",
}


def _dataset_view(state: AgentState) -> dict[str, Any]:
    meta = state.get("dataset_meta") or {}
    return {
        "columns": [
            {"name": column.get("name"), "semantic_type": column.get("semantic_type")}
            for column in meta.get("columns", [])
        ],
        "candidate_metrics": meta.get("candidate_metrics", []),
        "candidate_dimensions": meta.get("candidate_dimensions", []),
        "candidate_date_column": meta.get("candidate_date_column"),
    }


def _result_columns(ctx, result_ids: list[str]) -> list[dict[str, Any]]:
    """给修复器看"每个结果集有哪些列"，否则它只能猜列名（实测会一直引用 month）。"""
    columns: list[dict[str, Any]] = []
    for result_id in result_ids:
        payload = ctx.evidence.get(result_id)
        if not payload:
            continue
        data = payload.get("data") or {}
        names: list[str] = []
        if isinstance(data.get("columns"), list):
            names = [
                item.get("name") if isinstance(item, dict) else str(item)
                for item in data["columns"]
            ]
        elif isinstance(data.get("metrics"), list):
            for metric in data["metrics"]:
                names.append(str(metric.get("name")))
                for group in metric.get("groups") or []:
                    names.extend(str(key) for key in (group.get("key") or {}))
        columns.append(
            {
                "result_id": result_id,
                "tool": payload.get("tool"),
                "columns": sorted(set(name for name in names if name)),
            }
        )
    return columns


async def _llm_repair(
    state: AgentState, ctx: RunContext, step: dict[str, Any], error: dict[str, Any]
) -> dict[str, Any] | None:
    spec = next((schema for schema in tool_schemas() if schema["name"] == step["tool"]), None)
    result_ids = [str(item["result_id"]) for item in state.get("step_results") or []]
    user = json.dumps(
        {
            "step": {
                "step_id": step["step_id"],
                "title": step["title"],
                "tool": step["tool"],
                "tool_args_hint": step.get("tool_args_hint"),
            },
            "tool_schema": spec["parameters"] if spec else None,
            "error": error,
            "dataset": _dataset_view(state),
            "available_results": result_ids,
            "result_columns": _result_columns(ctx, result_ids),
        },
        ensure_ascii=False,
    )
    result = await ctx.llm_call(purpose="repair", system=SYSTEM_PROMPT, user=user, max_tokens=800)
    text = result.text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1] if "\n" in text else text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not payload.get("tool") or not isinstance(payload.get("tool_args_hint"), dict):
        return None
    return {
        "tool": str(payload["tool"]),
        "tool_args_hint": payload["tool_args_hint"],
        "reason": str(payload.get("reason", "")),
    }


async def repair_step(state: AgentState, ctx: RunContext) -> dict[str, Any]:
    ctx.check_cancel()
    steps = [dict(step) for step in state.get("steps") or []]
    warnings = list(state.get("warnings") or [])
    failed_id = state.get("failed_step")
    index = next(
        (i for i, step in enumerate(steps) if step.get("step_id") == failed_id), None
    )
    if index is None:
        return {"failed_step": None, "routing": "execute"}

    step = dict(steps[index])
    error = dict(step.get("error") or {})
    repair_count = int(state.get("repair_count") or 0)
    code = str(error.get("code") or "")

    fixed: dict[str, Any] | None = None
    if repair_count < MAX_REPAIRS and code in REPAIRABLE_CODES:
        try:
            if state.get("mode") == "demo":
                fixed = demo_planner.repair_step(
                    step=step, error=error, dataset_meta=state.get("dataset_meta") or {}
                )
            else:
                fixed = await _llm_repair(state, ctx, step, error)
        except Exception as exc:  # 修复本身失败不应让整个 run 崩溃
            logger.warning("repair_failed", extra={"run_id": ctx.run_id, "error": str(exc)[:200]})
            fixed = None

    if fixed:
        step["status"] = "pending"
        step["error"] = None
        step["summary"] = f"已修复：{fixed.get('reason') or '调整参数后重试'}"
        step["tool"] = fixed.get("tool") or step["tool"]
        step["tool_args_hint"] = with_dataset_id(
            str(step["tool"]),
            dict(fixed.get("tool_args_hint") or step.get("tool_args_hint") or {}),
            state["dataset_id"],
        )
        step["started_at"] = None
        step["finished_at"] = None
        steps[index] = step
        warnings.append(f"{step['step_id']} 首次失败（{code}），已修正参数重试")
        return {
            "steps": steps,
            "failed_step": None,
            "repair_count": repair_count + 1,
            "warnings": warnings,
            "routing": "execute",
        }

    step["status"] = "skipped"
    step["finished_at"] = now_iso()
    step["summary"] = f"无法修复，已跳过：{error.get('message', code)}"
    steps[index] = step
    warnings.append(
        f"步骤 {step['step_id']}（{step['tool']}）失败且无法修复，已跳过："
        f"{error.get('message', code)}"
    )
    return {
        "steps": steps,
        "failed_step": None,
        "step_index": index + 1,
        "repair_count": repair_count,
        "warnings": warnings,
        "routing": "execute",
    }
