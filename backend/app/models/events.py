"""SSE 事件契约（§6.5）：类型枚举 + 每种事件的 payload 模型 + 信封校验。

为什么 payload 用"按 type 查表校验"，而不是 16 个 Event 子类的 union：
信封字段（seq/run_id/ts/step_id）对所有事件完全一致，只有 payload 不同；
查表校验既能强制字段一致（frontend/src/types/events.ts 同一份契约），
又不会让 events.py 膨胀成 16 个只差一个字段的类。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import RunMode, RunStatus, StepStatus
from .run import Budget


class EventType(str, Enum):
    RUN_CREATED = "run_created"
    RUN_STARTED = "run_started"
    DATASET_INSPECTED = "dataset_inspected"
    PLAN_CREATED = "plan_created"
    STEP_STARTED = "step_started"
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_SUCCEEDED = "tool_call_succeeded"
    TOOL_CALL_FAILED = "tool_call_failed"
    STEP_COMPLETED = "step_completed"
    REPLAN_REQUESTED = "replan_requested"
    VERIFICATION_COMPLETED = "verification_completed"
    REPORT_CREATED = "report_created"
    BUDGET_WARNING = "budget_warning"
    RUN_SUCCEEDED = "run_succeeded"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorBrief(_Payload):
    code: str
    message: str
    hint: str | None = None
    # 字段级校验明细（如 metrics.0.kind），前端据此定位是哪个参数写错了
    fields: list[dict[str, Any]] | None = None


class RunCreatedPayload(_Payload):
    run_id: str
    mode: RunMode
    dataset_id: str


class RunStartedPayload(_Payload):
    model: str | None = None
    budget: Budget


class DatasetInspectedPayload(_Payload):
    row_count: int
    column_count: int
    quality_issue_count: int = 0


class PlanStepBrief(_Payload):
    step_id: str
    title: str
    tool: str


class PlanCreatedPayload(_Payload):
    plan_version: int = 1
    steps: list[PlanStepBrief] = Field(default_factory=list)
    objective: str = ""


class StepStartedPayload(_Payload):
    step_id: str
    title: str
    tool: str


class ToolCallStartedPayload(_Payload):
    call_id: str
    tool: str
    args_summary: dict[str, Any] = Field(default_factory=dict)


class ToolCallSucceededPayload(_Payload):
    call_id: str
    tool: str
    result_id: str | None = None
    duration_ms: int = 0
    rows_returned: int | None = None
    data_preview: Any | None = None


class ToolCallFailedPayload(_Payload):
    call_id: str
    tool: str
    error: ErrorBrief
    duration_ms: int = 0


class StepCompletedPayload(_Payload):
    step_id: str
    status: StepStatus
    summary: str = ""


class ReplanRequestedPayload(_Payload):
    reason: str
    replan_count: int
    failed_step_id: str | None = None


class VerificationCompletedPayload(_Payload):
    coverage: float
    supported: int = 0
    unsupported: int = 0
    unverifiable: int = 0


class ReportCreatedPayload(_Payload):
    report_id: str
    kpi_count: int = 0
    chart_count: int = 0
    status: RunStatus = RunStatus.SUCCEEDED


class BudgetWarningPayload(_Payload):
    kind: Literal["max_steps", "max_tool_calls", "max_replans"]
    used: int
    limit: int


class RunTerminalPayload(_Payload):
    status: RunStatus
    finished_at: datetime | None = None
    duration_ms: int | None = None
    error: ErrorBrief | None = None


PAYLOAD_MODELS: dict[str, type[_Payload]] = {
    EventType.RUN_CREATED.value: RunCreatedPayload,
    EventType.RUN_STARTED.value: RunStartedPayload,
    EventType.DATASET_INSPECTED.value: DatasetInspectedPayload,
    EventType.PLAN_CREATED.value: PlanCreatedPayload,
    EventType.STEP_STARTED.value: StepStartedPayload,
    EventType.TOOL_CALL_STARTED.value: ToolCallStartedPayload,
    EventType.TOOL_CALL_SUCCEEDED.value: ToolCallSucceededPayload,
    EventType.TOOL_CALL_FAILED.value: ToolCallFailedPayload,
    EventType.STEP_COMPLETED.value: StepCompletedPayload,
    EventType.REPLAN_REQUESTED.value: ReplanRequestedPayload,
    EventType.VERIFICATION_COMPLETED.value: VerificationCompletedPayload,
    EventType.REPORT_CREATED.value: ReportCreatedPayload,
    EventType.BUDGET_WARNING.value: BudgetWarningPayload,
    EventType.RUN_SUCCEEDED.value: RunTerminalPayload,
    EventType.RUN_FAILED.value: RunTerminalPayload,
    EventType.RUN_CANCELLED.value: RunTerminalPayload,
}


class Event(BaseModel):
    """SSE data 帧的完整形状；model_validate 时会顺带校验 payload。"""

    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=1)
    run_id: str
    ts: datetime
    type: EventType
    step_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _validate_payload(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw_type = data.get("type")
            key = raw_type.value if isinstance(raw_type, Enum) else str(raw_type)
            model = PAYLOAD_MODELS.get(key)
            if model is None:
                raise ValueError(f"未知事件类型: {key}")
            validated = model.model_validate(data.get("payload") or {})
            data = {**data, "payload": validated.model_dump(mode="json")}
        return data


def validate_event_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """给 runner/测试用的独立校验入口：返回规范化后的 payload。"""
    model = PAYLOAD_MODELS.get(event_type)
    if model is None:
        raise ValueError(f"未知事件类型: {event_type}")
    return model.model_validate(payload).model_dump(mode="json")
