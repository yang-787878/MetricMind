"""finalize：装配报告模型、落库、发终态事件（§6.2）。"""

from __future__ import annotations

import json
import time
from typing import Any

from ...logging_conf import get_logger
from ...models.enums import RunMode, RunStatus
from ...services.report_builder import build_report
from ..run_context import RunContext
from ..state import AgentState
from ._steps import now_iso

logger = get_logger(__name__)

TERMINAL_EVENT = {
    RunStatus.SUCCEEDED: "run_succeeded",
    RunStatus.PARTIAL: "run_succeeded",
    RunStatus.FAILED: "run_failed",
    RunStatus.CANCELLED: "run_cancelled",
}


async def finalize(state: AgentState, ctx: RunContext) -> dict[str, Any]:
    steps = state.get("steps") or []
    warnings = list(state.get("warnings") or [])
    raw_status = str(state.get("status") or "succeeded")
    try:
        status = RunStatus(raw_status)
    except ValueError:
        status = RunStatus.PARTIAL

    if status is RunStatus.SUCCEEDED and any(
        step.get("status") == "skipped" for step in steps
    ):
        status = RunStatus.PARTIAL
        warnings.append("存在被跳过的步骤，报告标记为部分结果")
    if state.get("error"):
        status = RunStatus.FAILED

    evidence: dict[str, Any] = {}
    for result_id in ctx.evidence.all_ids():
        payload = ctx.evidence.get(result_id)
        if payload:
            evidence[result_id] = payload

    draft = state.get("draft") or {
        "title": f"{state.get('question', '')} 分析报告",
        "headline": "分析未能产出可核验的结论。",
        "sections": [],
        "claims": [],
        "limitations": warnings,
        "next_steps": [],
    }
    report = build_report(
        run_id=ctx.run_id,
        question=state.get("question", ""),
        mode=RunMode(state.get("mode", "demo")),
        status=status,
        plan=state.get("plan"),
        steps=steps,
        evidence=evidence,
        dataset_meta=state.get("dataset_meta") or {},
        draft=draft,
        verification=state.get("verification"),
        warnings=warnings,
        narrative_source=str(draft.get("narrative_source") or "template"),
    )

    duration_ms = int((time.monotonic() - ctx.started_monotonic) * 1000)
    finished_at = now_iso()
    state_snapshot = {
        "plan_version": state.get("plan_version"),
        "steps": steps,
        "warnings": warnings,
        "evidence_ids": list(evidence.keys()),
        "replan_count": state.get("replan_count"),
        "audit_attempts": state.get("audit_attempts"),
    }

    ctx.store.update_run(
        ctx.run_id,
        status=status.value,
        plan_json=json.dumps(state.get("plan"), ensure_ascii=False),
        state_json=json.dumps(state_snapshot, ensure_ascii=False),
        report_json=report.model_dump_json(),
        verification_json=json.dumps(state.get("verification"), ensure_ascii=False),
        usage_json=json.dumps(ctx.usage.model_dump(mode="json"), ensure_ascii=False),
        error_json=json.dumps(state.get("error"), ensure_ascii=False) if state.get("error") else None,
        finished_at=finished_at,
    )

    await ctx.emit(
        "report_created",
        {
            "report_id": report.run_id,
            "kpi_count": len(report.kpis),
            "chart_count": len(report.charts),
            "status": status.value,
        },
    )
    terminal = TERMINAL_EVENT.get(status, "run_succeeded")
    await ctx.emit(
        terminal,
        {
            "status": status.value,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "error": state.get("error"),
        },
    )
    logger.info(
        "run_finalized",
        extra={
            "run_id": ctx.run_id,
            "status": status.value,
            "duration_ms": duration_ms,
            "kpis": len(report.kpis),
            "claims": len(report.claims),
            "coverage": (state.get("verification") or {}).get("coverage"),
        },
    )
    return {
        "report": report.model_dump(mode="json"),
        "status": status.value,
        "routing": "end",
    }
