"""execute：一次执行一个计划步骤，产出工具调用记录与证据引用。"""

from __future__ import annotations

import time
from typing import Any

from ..run_context import BudgetExhausted, RunContext
from ..state import AgentState
from ._steps import now_iso, resolve_placeholders


def _summarise(data: Any) -> str:
    if isinstance(data, dict):
        if isinstance(data.get("rows"), list):
            return f"返回 {data.get('row_count', len(data['rows']))} 行"
        if isinstance(data.get("metrics"), list):
            names = [str(metric.get("name")) for metric in data["metrics"][:3]]
            return f"计算 {len(data['metrics'])} 个指标：{', '.join(names)}"
        if data.get("chart_id"):
            return f"生成图表 {data['chart_id']}（{data.get('type')}）"
        if data.get("issues") is not None:
            return f"发现 {len(data['issues'])} 个质量问题"
        if data.get("columns"):
            return f"探查 {len(data['columns'])} 个字段"
    return ""


def _tool_status(code: str | None) -> str:
    if code is None:
        return "ok"
    if code == "TOOL_TIMEOUT":
        return "timeout"
    if code == "SQL_REJECTED":
        return "rejected"
    return "error"


async def execute(state: AgentState, ctx: RunContext) -> dict[str, Any]:
    ctx.check_cancel()
    steps = [dict(step) for step in state.get("steps") or []]
    index = int(state.get("step_index") or 0)
    warnings = list(state.get("warnings") or [])

    if index >= len(steps):
        return {"routing": "verify"}

    if ctx.usage.steps_used >= ctx.budget.max_steps:
        await ctx.emit(
            "budget_warning",
            {"kind": "max_steps", "used": ctx.usage.steps_used, "limit": ctx.budget.max_steps},
        )
        return {
            "routing": "budget",
            "status": "partial",
            "warnings": warnings + ["因执行预算耗尽，分析未覆盖全部维度"],
        }

    ctx.usage.steps_used += 1
    step = dict(steps[index])
    step["status"] = "running"
    step["started_at"] = now_iso()
    steps[index] = step

    await ctx.emit(
        "step_started",
        {"step_id": step["step_id"], "title": step["title"], "tool": step["tool"]},
        step_id=step["step_id"],
    )

    arguments = resolve_placeholders(
        step.get("tool_args_hint") or {}, state, ctx.last_result_id
    )
    started = time.perf_counter()
    try:
        envelope = await ctx.call_tool(str(step["tool"]), arguments, step_id=step["step_id"])
    except BudgetExhausted as exc:
        step["status"] = "skipped"
        steps[index] = step
        return {
            "steps": steps,
            "routing": "budget",
            "status": "partial",
            "warnings": warnings
            + [f"工具调用预算耗尽（{exc.used}/{exc.limit}），剩余步骤未执行"],
        }

    duration_ms = int((time.perf_counter() - started) * 1000)
    error = envelope.error
    call_record = {
        "call_id": f"call_{step['step_id']}_{len(step.get('tool_calls') or []) + 1}",
        "step_id": step["step_id"],
        "tool": str(step["tool"]),
        "status": _tool_status(error.code if error else None),
        "arguments": arguments if isinstance(arguments, dict) else {"value": arguments},
        "result_id": envelope.result_id,
        "duration_ms": duration_ms,
        "result": envelope.data if envelope.ok else None,
        "error": error.model_dump(mode="json") if error else None,
        "warnings": list(envelope.meta.warnings),
        "created_at": now_iso(),
    }
    step["tool_calls"] = list(step.get("tool_calls") or []) + [call_record]

    results = list(state.get("step_results") or [])
    if envelope.ok:
        step["status"] = "succeeded"
        step["summary"] = _summarise(envelope.data)
        step["finished_at"] = now_iso()
        step["duration_ms"] = duration_ms
        if envelope.result_id:
            results.append(
                {
                    "step_id": step["step_id"],
                    "result_id": envelope.result_id,
                    "tool": step["tool"],
                }
            )
        failed_step = None
        next_index = index + 1
    else:
        step["status"] = "failed"
        step["finished_at"] = now_iso()
        step["duration_ms"] = duration_ms
        step["summary"] = f"调用失败：{error.code if error else 'UNKNOWN'}"
        # fields 必须保留：修复器（repair_step）只有看到"哪个字段错了"才能改对参数，
        # 早期只传 code+message 时模型只能盲猜，同一个步骤会反复失败。
        step["error"] = {
            "code": error.code if error else "INTERNAL_TOOL_ERROR",
            "message": error.message if error else "工具执行失败",
            "hint": error.hint if error else None,
            "fields": list(error.fields or []) if error else [],
        }
        failed_step = step["step_id"]
        next_index = index

    steps[index] = step
    await ctx.emit(
        "step_completed",
        {
            "step_id": step["step_id"],
            "status": step["status"],
            "summary": step.get("summary") or "",
        },
        step_id=step["step_id"],
    )

    fatal = error is not None and error.code == "DATASET_NOT_FOUND"
    if fatal:
        return {
            "steps": steps,
            "failed_step": failed_step,
            "step_results": results,
            "routing": "fail",
            "error": {
                "code": error.code,
                "message": error.message,
                "hint": error.hint,
            },
        }

    return {
        "steps": steps,
        "step_index": next_index,
        "failed_step": failed_step,
        "step_results": results,
        "evidence_pool": ctx.evidence.dump(),
        "routing": "continue",
    }
