"""§4.1 枚举的唯一来源，前后端逐字对应（frontend/src/types/contract.ts）。

放在单独模块的原因：report.py / run.py / chart.py 互相引用状态枚举，
如果各自定义会形成循环 import，也容易出现"两个 RunStatus"。
"""

from __future__ import annotations

from enum import Enum


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_RUN_STATUSES: frozenset[RunStatus] = frozenset(
    {RunStatus.SUCCEEDED, RunStatus.PARTIAL, RunStatus.FAILED, RunStatus.CANCELLED}
)


class RunMode(str, Enum):
    LIVE = "live"
    DEMO = "demo"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class ToolStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    REJECTED = "rejected"


class VerificationStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNVERIFIABLE = "unverifiable"


class SemanticType(str, Enum):
    NUMERIC = "numeric"
    TEMPORAL = "temporal"
    CATEGORICAL = "categorical"
    IDENTIFIER = "identifier"
    TEXT = "text"
    BOOLEAN = "boolean"


class ChartType(str, Enum):
    BAR = "bar"
    STACKED_BAR = "stacked_bar"
    LINE = "line"
    AREA = "area"
    SCATTER = "scatter"


class SourceKind(str, Enum):
    UPLOAD = "upload"
    SAMPLE = "sample"


class IssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RequestedMode(str, Enum):
    """POST /api/runs 的入参模式：auto 是"由是否配置 Key 决定"。"""

    AUTO = "auto"
    LIVE = "live"
    DEMO = "demo"
