"""统一错误体系：错误码枚举 + 异常类型 + 统一响应信封。

为什么需要：前端按 `code` 渲染人话与重试按钮，LLM 按 `hint` 修复参数，
两者都不能依赖散落的 HTTPException 字符串。所有对外错误必须经过这里。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorCode(str, Enum):
    # --- 工具层 (§5.3) ---
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DATASET_NOT_FOUND = "DATASET_NOT_FOUND"
    RESULT_NOT_FOUND = "RESULT_NOT_FOUND"
    INVALID_COLUMN = "INVALID_COLUMN"
    SQL_REJECTED = "SQL_REJECTED"
    SQL_EXECUTION_ERROR = "SQL_EXECUTION_ERROR"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    EMPTY_RESULT = "EMPTY_RESULT"
    INTERNAL_TOOL_ERROR = "INTERNAL_TOOL_ERROR"
    # --- 上传 / 数据集 ---
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    DATASET_TOO_LARGE = "DATASET_TOO_LARGE"
    INVALID_DATASET = "INVALID_DATASET"
    DATASET_IN_USE = "DATASET_IN_USE"
    # --- run / 报告 ---
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    RUN_ALREADY_FINISHED = "RUN_ALREADY_FINISHED"
    RUN_INTERRUPTED = "RUN_INTERRUPTED"
    RUN_TIMEOUT = "RUN_TIMEOUT"
    REPORT_NOT_READY = "REPORT_NOT_READY"
    # --- LLM ---
    LLM_NOT_CONFIGURED = "LLM_NOT_CONFIGURED"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_INVALID_OUTPUT = "LLM_INVALID_OUTPUT"
    # --- 通用 ---
    RATE_LIMITED = "RATE_LIMITED"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# HTTP 语义映射（§5.3 表格 + 通用错误）
HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.DATASET_NOT_FOUND: 404,
    ErrorCode.RESULT_NOT_FOUND: 404,
    ErrorCode.INVALID_COLUMN: 400,
    ErrorCode.SQL_REJECTED: 400,
    ErrorCode.SQL_EXECUTION_ERROR: 400,
    ErrorCode.TOOL_TIMEOUT: 504,
    ErrorCode.BUDGET_EXCEEDED: 429,
    ErrorCode.EMPTY_RESULT: 200,
    ErrorCode.INTERNAL_TOOL_ERROR: 500,
    ErrorCode.UNSUPPORTED_FILE_TYPE: 415,
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.DATASET_TOO_LARGE: 413,
    ErrorCode.INVALID_DATASET: 400,
    ErrorCode.DATASET_IN_USE: 409,
    ErrorCode.RUN_NOT_FOUND: 404,
    ErrorCode.RUN_ALREADY_FINISHED: 409,
    ErrorCode.RUN_INTERRUPTED: 409,
    ErrorCode.RUN_TIMEOUT: 504,
    ErrorCode.REPORT_NOT_READY: 409,
    ErrorCode.LLM_NOT_CONFIGURED: 409,
    ErrorCode.LLM_UNAVAILABLE: 503,
    ErrorCode.LLM_INVALID_OUTPUT: 502,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.INTERNAL_ERROR: 500,
}

RETRYABLE: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.SQL_EXECUTION_ERROR,  # 仅语法类
        ErrorCode.TOOL_TIMEOUT,
        ErrorCode.EMPTY_RESULT,
        ErrorCode.INTERNAL_TOOL_ERROR,
        ErrorCode.LLM_UNAVAILABLE,
        ErrorCode.RUN_TIMEOUT,
    }
)


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    """统一错误响应体 {"error": {...}}，前端 ApiError 直接解析它。"""

    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


class AppError(Exception):
    """所有业务异常的基类：带错误码、人话 message、结构化 details、修复 hint。"""

    def __init__(
        self,
        code: ErrorCode | str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        hint: str | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code.value if isinstance(code, ErrorCode) else str(code)
        self.message = message
        self.details = details or {}
        if hint:
            self.details.setdefault("hint", hint)
        self._http_status = http_status

    @property
    def http_status(self) -> int:
        if self._http_status is not None:
            return self._http_status
        try:
            return HTTP_STATUS[ErrorCode(self.code)]
        except (ValueError, KeyError):
            return 500

    @property
    def retryable(self) -> bool:
        try:
            return ErrorCode(self.code) in RETRYABLE
        except ValueError:
            return False

    def to_envelope(self, request_id: str | None = None) -> ErrorEnvelope:
        return ErrorEnvelope(
            error=ErrorBody(
                code=self.code,
                message=self.message,
                details=self.details,
                request_id=request_id,
            )
        )

    def __str__(self) -> str:  # pragma: no cover - 仅日志可读性
        return f"{self.code}: {self.message}"


# --- 便捷构造器：调用点只关心语义，不关心 HTTP 细节 ---
def validation_error(message: str, **details: Any) -> AppError:
    return AppError(ErrorCode.VALIDATION_ERROR, message, details=details)


def dataset_not_found(dataset_id: str) -> AppError:
    return AppError(
        ErrorCode.DATASET_NOT_FOUND,
        f"数据集 {dataset_id} 不存在",
        details={"dataset_id": dataset_id},
    )


def invalid_column(column: str, available: list[str]) -> AppError:
    return AppError(
        ErrorCode.INVALID_COLUMN,
        f"列 {column} 不存在",
        details={"column": column, "available": available},
        hint="请从 available 中选择真实存在的列名",
    )


def result_not_found(result_id: str) -> AppError:
    return AppError(
        ErrorCode.RESULT_NOT_FOUND,
        f"结果集 {result_id} 不存在于当前运行",
        details={"result_id": result_id},
        hint="只能引用本 run 内工具真实返回的 result_id",
    )


def llm_not_configured() -> AppError:
    return AppError(
        ErrorCode.LLM_NOT_CONFIGURED,
        "未配置大模型 API Key，无法以 live 模式运行",
        details={"action": "switch_to_demo"},
        hint="在 .env 中配置 OPENAI_API_KEY，或选择 Demo 模式运行",
    )


def run_not_found(run_id: str) -> AppError:
    return AppError(ErrorCode.RUN_NOT_FOUND, f"运行 {run_id} 不存在", details={"run_id": run_id})
