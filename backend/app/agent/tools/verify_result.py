"""verify_result（§5.2(6)）：把结论里的数字逐条比对证据池，输出覆盖率。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ...errors import AppError, ErrorCode
from ...models.tool import ToolEnvelope, ToolMeta
from ...services.verifier import ClaimInput, verify_claims
from ..context import ToolContext

NAME = "verify_result"
DESCRIPTION = (
    "把结论中的每个数字与证据池中的真实结果逐一比对（相对误差 0.5% 内判 supported，"
    "1% 内判接近但超差）。返回 coverage 与逐条 claim 的匹配值，用于报告前的自动审计。"
)
TIMEOUT_S = 20.0
MAX_CALLS = 3
# §4.2：result_id 只对产出表格/数值的工具存在，审计工具本身不产生新证据
PRODUCES_RESULT = False


class NumberInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float
    unit: str = ""


class ClaimModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=500)
    numbers: list[NumberInput] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    claims: list[ClaimModel] = Field(min_length=1, max_length=30)


async def run(ctx: ToolContext, args: Input) -> ToolEnvelope:
    if args.run_id != ctx.run_id:
        raise AppError(
            ErrorCode.RUN_NOT_FOUND,
            f"运行 {args.run_id} 与当前 run 不一致",
            details={"run_id": args.run_id, "current_run_id": ctx.run_id},
        )

    claims = [
        ClaimInput(
            claim_id=claim.claim_id,
            text=claim.text,
            numbers=[{"value": number.value, "unit": number.unit} for number in claim.numbers],
            evidence_ids=list(claim.evidence_ids),
        )
        for claim in args.claims
    ]
    result = verify_claims(claims, ctx.evidence.get)
    data = result.model_dump(mode="json")
    warnings = (
        [f"{result.unsupported} 条结论未通过数字校验"] if result.unsupported else []
    )
    return ToolEnvelope.success(
        tool=NAME,
        data=data,
        meta=ToolMeta(tool=NAME, rows_returned=len(result.items), warnings=warnings),
    )
