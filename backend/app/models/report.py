"""报告模型：KPI / 结论 / claims / 方法论 / 质量 / 局限性（§4.2 报告模型）。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import IssueSeverity, RunMode, RunStatus, VerificationStatus


class Kpi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: float | None = None
    unit: str | None = None
    delta: float | None = None
    delta_label: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    display_value: str | None = None  # 由证据值重新格式化，见 §6.4 第 4 条


class ReportSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    heading: str
    body: str
    evidence_ids: list[str] = Field(default_factory=list)
    degraded: bool = False  # 未通过审计而被降级为"未经证实的推断"


class ClaimNumber(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float
    unit: str = ""


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    text: str
    numbers: list[ClaimNumber] = Field(default_factory=list)
    display_numbers: list[str] = Field(default_factory=list)  # 由证据值格式化，供报告渲染
    evidence_ids: list[str] = Field(default_factory=list)
    status: VerificationStatus = VerificationStatus.UNVERIFIABLE
    reason: str | None = None
    matched_value: float | None = None


class MethodologyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    description: str
    tool: str
    result_id: str | None = None
    sql: str | None = None
    formula: str | None = None


class DataQualityNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: IssueSeverity
    message: str
    column: str | None = None


class VerificationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coverage: float = Field(ge=0.0, le=1.0)
    supported: int = 0
    unsupported: int = 0
    unverifiable: int = 0


class ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    title: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mode: RunMode
    status: RunStatus
    headline: str
    kpis: list[Kpi] = Field(default_factory=list)
    sections: list[ReportSection] = Field(default_factory=list)
    charts: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    methodology: list[MethodologyItem] = Field(default_factory=list)
    data_quality: list[DataQualityNote] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    verification: VerificationSummary | None = None
    narrative_source: str = "llm"  # "llm" | "template"，前端据此标注 Demo
    extra: dict[str, Any] = Field(default_factory=dict)
