"""report：基于证据池生成叙述草稿（Live 用模型，失败时退回确定性模板）。"""

from __future__ import annotations

import json
from typing import Any

from ...llm.prompt_loader import load_prompt
from ...logging_conf import get_logger
from .. import demo_planner
from ..run_context import RunContext
from ..state import AgentState

logger = get_logger(__name__)

SYSTEM_PROMPT = load_prompt("report")


def _evidence_items(ctx: RunContext, state: AgentState) -> list[dict[str, Any]]:
    from ...services.evidence import extract_numbers, extract_tables

    items: list[dict[str, Any]] = []
    for result_id in ctx.evidence.all_ids():
        payload = ctx.evidence.get(result_id)
        if not payload:
            continue
        items.append(
            {
                "result_id": result_id,
                "tool": payload.get("tool"),
                "step_id": payload.get("step_id"),
                "data": payload.get("data"),
                "numbers": extract_numbers(payload.get("data")),
                "tables": extract_tables({"data": payload.get("data")}),
            }
        )
    return items


def _validate_draft(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("草稿不是 JSON 对象")
    for key in ("title", "headline", "sections", "claims"):
        if key not in payload:
            raise ValueError(f"草稿缺少字段 {key}")
    if not isinstance(payload.get("claims"), list):
        raise ValueError("claims 必须是数组")
    return payload


async def _llm_report(
    state: AgentState, ctx: RunContext, items: list[dict[str, Any]]
) -> dict[str, Any]:
    user = json.dumps(
        {
            "question": state["question"],
            "objective": (state.get("plan") or {}).get("objective"),
            "evidence": [
                {
                    "result_id": item["result_id"],
                    "tool": item["tool"],
                    "step_id": item["step_id"],
                    "numbers": item["numbers"][:200],
                    "tables": item["tables"][:3],
                }
                for item in items
            ],
            "data_quality": [
                {"code": issue.get("code"), "message": issue.get("message")}
                for issue in state.get("quality") or []
            ],
            "unsupported_claims": list(state.get("audit_feedback") or []),
            "business_context": "无（保持数据集无关性）",
        },
        ensure_ascii=False,
    )
    last_error = ""
    base_cap = ctx.settings.llm_max_output_tokens
    for attempt in range(2):
        prompt = user
        if attempt and last_error:
            prompt = user + "\n\n# 上一次输出不合格\n" + last_error + "\n请重新输出合法 JSON。"
        # 报告 JSON 比计划更长；推理型模型还会先写思维链，4096 很容易被截断成空串。
        cap = base_cap if attempt == 0 else base_cap * 2
        result = await ctx.llm_call(
            purpose="report",
            system=SYSTEM_PROMPT,
            user=prompt,
            max_tokens=cap,
        )
        text = (result.text or "").strip()
        if result.truncated or not text:
            last_error = f"输出被 max_tokens={cap} 截断或为空"
            continue
        if text.startswith("```"):
            text = text.strip("`")
            text = text.split("\n", 1)[-1] if "\n" in text else text
        try:
            draft = _validate_draft(json.loads(text))
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = str(exc)[:500]
            continue
        draft["narrative_source"] = "llm"
        return draft
    raise ValueError(last_error or "模型未能产出合法的报告草稿")


async def report(state: AgentState, ctx: RunContext) -> dict[str, Any]:
    ctx.check_cancel()
    warnings = list(state.get("warnings") or [])
    items = _evidence_items(ctx, state)
    draft: dict[str, Any]

    if state.get("mode") == "demo":
        draft = demo_planner.build_draft(
            question=state["question"],
            plan=state.get("plan") or {},
            evidence=items,
            dataset_meta=state.get("dataset_meta") or {},
            feedback=list(state.get("audit_feedback") or []),
        )
    else:
        try:
            draft = await _llm_report(state, ctx, items)
        except Exception as exc:
            logger.warning(
                "report_llm_failed",
                extra={"run_id": ctx.run_id, "error": str(exc)[:300]},
            )
            warnings.append("叙述生成失败，本报告仅含工具结果")
            draft = demo_planner.build_draft(
                question=state["question"],
                plan=state.get("plan") or {},
                evidence=items,
                dataset_meta=state.get("dataset_meta") or {},
                feedback=["叙述生成失败，以下内容为确定性模板输出"],
            )
            draft["narrative_source"] = "template"
            return {"draft": draft, "warnings": warnings, "status": "partial"}

    return {"draft": draft, "warnings": warnings}
