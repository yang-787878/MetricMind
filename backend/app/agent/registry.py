"""工具注册表（§5.1）：schema 自动生成，执行统一走校验 → 预算 → 超时 → 证据 → 信封。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from ..errors import AppError, ErrorCode
from ..logging_conf import get_logger
from ..models.tool import ToolEnvelope, ToolMeta
from .context import ToolContext
from .tools import (
    calculate_metrics,
    create_chart,
    export_report,
    inspect_dataset,
    profile_dataset,
    query_data,
    verify_result,
)

logger = get_logger(__name__)

Handler = Callable[[ToolContext, Any], Awaitable[ToolEnvelope]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Handler
    timeout_s: float = 20.0
    max_calls_per_run: int = 3
    produces_result: bool = True
    planner_visible: bool = True

    def json_schema(self) -> dict[str, Any]:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return {
            "name": self.name,
            "description": self.description,
            "parameters": schema,
            "max_calls_per_run": self.max_calls_per_run,
            "timeout_s": self.timeout_s,
        }


def _spec(module) -> ToolSpec:
    return ToolSpec(
        name=module.NAME,
        description=module.DESCRIPTION,
        input_model=module.Input,
        handler=module.run,
        timeout_s=module.TIMEOUT_S,
        max_calls_per_run=module.MAX_CALLS,
        produces_result=getattr(module, "PRODUCES_RESULT", True),
        planner_visible=getattr(module, "PLANNER_VISIBLE", True),
    )


TOOLS: dict[str, ToolSpec] = {
    module.NAME: _spec(module)
    for module in (
        inspect_dataset,
        profile_dataset,
        query_data,
        calculate_metrics,
        create_chart,
        verify_result,
        export_report,
    )
}


def tool_schemas(*, planner_only: bool = False) -> list[dict[str, Any]]:
    """给规划/修复提示词用：schema 由 Pydantic 生成，不许手写第二份。

    export_report 只在运行结束后可用，因此不进入规划器可选工具集，
    否则模型会在执行阶段调用它并必然拿到 REPORT_NOT_READY。
    """
    return [
        spec.json_schema()
        for spec in TOOLS.values()
        if not planner_only or spec.planner_visible
    ]


def tool_names() -> list[str]:
    return list(TOOLS)


def get_tool(name: str) -> ToolSpec:
    spec = TOOLS.get(name)
    if spec is None:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"未知工具 {name}，可用：{', '.join(tool_names())}",
            details={"available": tool_names()},
            hint="请从 available 中选择工具名",
        )
    return spec


async def execute_tool(
    ctx: ToolContext,
    name: str,
    arguments: dict[str, Any],
    *,
    step_id: str | None = None,
) -> ToolEnvelope:
    """统一执行入口：任何工具都不能绕过这里，因此预算/超时/证据链无法被跳过。"""
    started = time.perf_counter()
    try:
        spec = get_tool(name)
    except AppError as exc:
        return ToolEnvelope.failure(tool=name, code=exc.code, message=exc.message,
                                    hint=exc.details.get("hint"), retryable=False)

    used = ctx.calls.get(spec.name, 0)
    if used >= spec.max_calls_per_run:
        return ToolEnvelope.failure(
            tool=spec.name,
            code=ErrorCode.BUDGET_EXCEEDED.value,
            message=f"{spec.name} 本次运行最多调用 {spec.max_calls_per_run} 次，已用 {used} 次",
            hint="请复用已有结果集，或减少同类调用",
            retryable=False,
        )

    try:
        args = spec.input_model.model_validate(arguments)
    except ValidationError as exc:
        fields = [
            {"loc": ".".join(str(part) for part in err.get("loc", [])), "msg": err.get("msg", "")}
            for err in exc.errors()
        ]
        # 把第一条字段错误写进 message：只给"参数不合法"时，模型和人都无从下手。
        detail = "；".join(
            f"{item['loc'] or '(root)'}: {item['msg']}" for item in fields[:3]
        )
        failed_count = len(fields) - len(fields[:3])
        if failed_count > 0:
            detail = f"{detail}；另有 {failed_count} 处错误"
        return ToolEnvelope.failure(
            tool=spec.name,
            code=ErrorCode.VALIDATION_ERROR.value,
            message=f"{spec.name} 参数不合法" + (f"：{detail}" if detail else ""),
            hint="请按 tools schema 修正参数，不要附加未知字段",
            fields=fields,
        )

    ctx.count_call(spec.name)
    previous_step = ctx.step_id
    ctx.step_id = step_id or ctx.step_id
    try:
        envelope = await asyncio.wait_for(spec.handler(ctx, args), timeout=spec.timeout_s)
    except (TimeoutError, asyncio.TimeoutError):
        envelope = ToolEnvelope.failure(
            tool=spec.name,
            code=ErrorCode.TOOL_TIMEOUT.value,
            message=f"{spec.name} 超过 {spec.timeout_s}s 未返回",
            hint="请缩小数据范围后重试",
            retryable=True,
        )
    except AppError as exc:
        envelope = ToolEnvelope.failure(
            tool=spec.name,
            code=exc.code,
            message=exc.message,
            hint=exc.details.get("hint"),
            retryable=exc.retryable,
        )
    except Exception as exc:  # pragma: no cover - 兜底，避免把堆栈泄漏给前端
        logger.exception(
            "tool_crashed",
            extra={"run_id": ctx.run_id, "tool": spec.name, "error": str(exc)},
        )
        envelope = ToolEnvelope.failure(
            tool=spec.name,
            code=ErrorCode.INTERNAL_TOOL_ERROR.value,
            message=f"{spec.name} 执行失败（内部错误）",
            hint="可重试一次；若持续失败请检查数据集",
            retryable=True,
        )
    finally:
        ctx.step_id = previous_step

    duration_ms = int((time.perf_counter() - started) * 1000)
    envelope.meta.duration_ms = duration_ms
    if envelope.ok and spec.produces_result and envelope.result_id is None:
        result_id = await asyncio.to_thread(
            ctx.evidence.record,
            tool=spec.name,
            data=envelope.data,
            meta=envelope.meta.model_dump(mode="json"),
            step_id=step_id,
        )
        envelope.result_id = result_id
    if not envelope.ok and envelope.error is not None:
        envelope.meta.warnings.extend(envelope.meta.warnings)
    return envelope


__all__ = [
    "ToolSpec",
    "TOOLS",
    "tool_schemas",
    "tool_names",
    "get_tool",
    "execute_tool",
    "ToolMeta",
]
