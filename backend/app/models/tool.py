"""工具层契约：统一结果信封 + 错误对象（§4.2 / §5.3）。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import ToolStatus


class ToolErrorInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    hint: str | None = None
    retryable: bool = False
    fields: list[dict[str, Any]] | None = None


class ToolMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    duration_ms: int = 0
    rows_returned: int | None = None
    truncated: bool = False
    sql_executed: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ToolEnvelope(BaseModel):
    """七个工具统一的返回信封；result_id 只对产出表格/数值的工具存在。"""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    result_id: str | None = None
    data: Any | None
    error: ToolErrorInfo | None = None
    meta: ToolMeta

    @classmethod
    def success(
        cls,
        *,
        tool: str,
        data: Any,
        result_id: str | None = None,
        meta: ToolMeta | None = None,
    ) -> "ToolEnvelope":
        base = meta or ToolMeta(tool=tool)
        return cls(ok=True, result_id=result_id, data=data, error=None, meta=base)

    @classmethod
    def failure(
        cls,
        *,
        tool: str,
        code: str,
        message: str,
        hint: str | None = None,
        retryable: bool = False,
        fields: list[dict[str, Any]] | None = None,
        duration_ms: int = 0,
        warnings: list[str] | None = None,
    ) -> "ToolEnvelope":
        return cls(
            ok=False,
            result_id=None,
            data=None,
            error=ToolErrorInfo(
                code=code, message=message, hint=hint, retryable=retryable, fields=fields
            ),
            meta=ToolMeta(tool=tool, duration_ms=duration_ms, warnings=warnings or []),
        )


class ToolCallRecord(BaseModel):
    """一次工具调用在 run 中的持久化形态，前端 ToolCallCard 直接消费。"""

    model_config = ConfigDict(extra="forbid")

    call_id: str
    step_id: str | None = None
    tool: str
    status: ToolStatus
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_id: str | None = None
    duration_ms: int = 0
    result: dict[str, Any] | None = None
    error: ToolErrorInfo | None = None
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VerificationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    status: str
    matched_evidence_id: str | None = None
    matched_value: float | None = None
    claimed_value: float | None = None
    relative_delta: float | None = None
    reason: str = ""


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coverage: float = Field(ge=0.0, le=1.0)
    items: list[VerificationItem] = Field(default_factory=list)
    supported: int = 0
    unsupported: int = 0
    unverifiable: int = 0
