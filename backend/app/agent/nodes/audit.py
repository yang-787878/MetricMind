"""audit：自动调用 verify_result 审计全部 claims，决定 succeeded / 重写 / partial。"""

from __future__ import annotations

from typing import Any

from ...logging_conf import get_logger
from ..run_context import BudgetExhausted, RunContext
from ..state import AgentState

logger = get_logger(__name__)


def _claims_payload(draft: dict[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for raw in draft.get("claims", []):
        claims.append(
            {
                "claim_id": str(raw.get("claim_id", ""))[:40] or "c",
                "text": str(raw.get("text", ""))[:500] or "（空）",
                "numbers": [
                    {"value": float(number.get("value", 0.0)), "unit": str(number.get("unit", ""))}
                    for number in raw.get("numbers", [])
                ],
                "evidence_ids": [str(value) for value in raw.get("evidence_ids", [])],
            }
        )
    return claims


async def audit(state: AgentState, ctx: RunContext) -> dict[str, Any]:
    ctx.check_cancel()
    draft = state.get("draft") or {}
    claims = _claims_payload(draft)
    attempts = int(state.get("audit_attempts") or 0)
    warnings = list(state.get("warnings") or [])

    if not claims:
        empty = {"coverage": 0.0, "items": [], "supported": 0, "unsupported": 0, "unverifiable": 0}
        await ctx.emit(
            "verification_completed",
            {"coverage": 0.0, "supported": 0, "unsupported": 0, "unverifiable": 0},
        )
        warnings.append("报告没有任何可核验的数字结论")
        return {
            "verification": empty,
            "routing": "finalize",
            "status": "partial",
            "warnings": warnings,
        }

    try:
        envelope = await ctx.call_tool(
            "verify_result", {"run_id": ctx.run_id, "claims": claims}, step_id="audit"
        )
    except BudgetExhausted:
        # 工具调用预算用尽时不能让审计直接失效：verify_claims 是纯计算，就地跑一遍
        from ...services.verifier import ClaimInput, verify_claims

        warnings.append("工具预算已用尽，审计改为就地执行（不占用工具额度）")
        result = verify_claims(
            [
                ClaimInput(
                    claim_id=str(claim["claim_id"]),
                    text=str(claim["text"]),
                    numbers=list(claim["numbers"]),
                    evidence_ids=list(claim["evidence_ids"]),
                )
                for claim in claims
            ],
            ctx.evidence.get,
        )
        data = result.model_dump(mode="json")
        envelope = None
    except Exception as exc:  # 其它工具异常：不阻断报告，标记为部分结果
        warnings.append(f"数字审计未能完成（{type(exc).__name__}），报告按部分结果处理")
        return {
            "verification": {
                "coverage": 0.0,
                "items": [],
                "supported": 0,
                "unsupported": 0,
                "unverifiable": len(claims),
            },
            "routing": "finalize",
            "status": "partial",
            "warnings": warnings,
        }
    if envelope is not None:
        if not envelope.ok or not isinstance(envelope.data, dict):
            warnings.append("数字审计工具未能执行，报告按部分结果处理")
            return {
                "verification": {"coverage": 0.0, "items": [], "supported": 0, "unsupported": 0, "unverifiable": len(claims)},
                "routing": "finalize",
                "status": "partial",
                "warnings": warnings,
            }
        data = envelope.data
    await ctx.emit(
        "verification_completed",
        {
            "coverage": float(data.get("coverage", 0.0)),
            "supported": int(data.get("supported", 0)),
            "unsupported": int(data.get("unsupported", 0)),
            "unverifiable": int(data.get("unverifiable", 0)),
        },
        step_id="audit",
    )

    coverage = float(data.get("coverage", 0.0))
    if coverage >= ctx.settings.min_coverage:
        return {"verification": data, "routing": "finalize", "status": "succeeded"}

    failures = [
        f"{item.get('claim_id')}：{item.get('reason') or '数字未在证据中找到'}"
        for item in data.get("items", [])
        if item.get("status") != "supported"
    ]
    if attempts == 0 and coverage >= 0.6:
        warnings.append(f"审计覆盖率 {coverage:.0%}，针对未通过结论重写一次")
        return {
            "verification": data,
            "routing": "report",
            "audit_attempts": attempts + 1,
            "audit_feedback": failures,
            "warnings": warnings,
        }

    logger.info(
        "audit_below_threshold",
        extra={"run_id": ctx.run_id, "coverage": coverage, "attempts": attempts},
    )
    warnings.append(f"数字审计覆盖率 {coverage:.0%}，未通过项已降级为局限性")
    return {
        "verification": data,
        "routing": "finalize",
        "status": "partial",
        "audit_feedback": failures,
        "warnings": warnings,
    }
