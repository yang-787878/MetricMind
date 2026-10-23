"""运行（run）模型：状态机 + 预算 + 步骤记录 + API 入参/出参（§4.2 / §8）。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import RequestedMode, RunMode, RunStatus, StepStatus
from .plan import StructuredPlan
from .report import ReportModel
from .tool import ToolCallRecord, VerificationResult


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_steps: int = 10
    max_tool_calls: int = 16
    max_replans: int = 2
    timeout_seconds: int = 240


class Usage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    steps_used: int = 0
    tool_calls_used: int = 0
    replans_used: int = 0


class StepRecord(BaseModel):
    """一个计划步骤的执行状态；tools 为该步内发生的全部工具调用。"""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    title: str
    intent: str = ""
    tool: str
    tool_args_hint: dict[str, Any] = Field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    expected_output: str = ""
    validation: str = ""
    summary: str = ""
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error: dict[str, Any] | None = None


class RunError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    hint: str | None = None


class RunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    dataset_id: str
    dataset_name: str | None = None
    question: str
    status: RunStatus
    mode: RunMode
    model: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None


class RunDetail(RunSummary):
    usage: Usage = Field(default_factory=Usage)
    budget: Budget = Field(default_factory=Budget)
    plan: StructuredPlan | None = None
    steps: list[StepRecord] = Field(default_factory=list)
    verification: VerificationResult | None = None
    report: ReportModel | None = None
    error: RunError | None = None
    warnings: list[str] = Field(default_factory=list)


class RunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RunSummary]
    total: int


class CreateRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    question: str = Field(min_length=3, max_length=500)
    mode: RequestedMode = RequestedMode.AUTO

    @field_validator("question")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("问题至少 3 个字符")
        return cleaned


class CreateRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: RunStatus
    mode: RunMode
    stream_url: str


class CancelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    run_id: str


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    version: str
    db: str
    llm_mode: RunMode
    model: str


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_upload_mb: int
    max_rows: int
    max_steps: int
    max_tool_calls: int
    max_replans: int
    run_timeout_s: int


class ConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_mode: RunMode
    model: str
    limits: Limits
    samples: list[dict[str, Any]] = Field(default_factory=list)


class ArtifactInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    run_id: str
    kind: str
    format: str
    size_bytes: int
    download_url: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "Budget", "Usage", "StepRecord", "RunError", "RunSummary", "RunDetail", "RunListResponse",
    "CreateRunRequest", "CreateRunResponse", "CancelResponse", "HealthResponse", "Limits",
    "ConfigResponse", "ArtifactInfo", "RunStatus",
]
