"""RunContext：一次 run 的运行期依赖与副作用入口。

节点只通过它触发事件、调用工具、调用 LLM——这样：
- 预算与取消检查无法被某个节点绕过；
- 单测可以直接构造 RunContext（注入 FakeLLM / 临时 store），不需要启动 HTTP。
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from ..config import Settings
from ..llm.base import LLMClient, LLMRequest, LLMResult
from ..logging_conf import get_logger
from ..models.enums import RunMode
from ..models.events import validate_event_payload
from ..models.run import Budget, Usage
from ..models.tool import ToolEnvelope
from ..services.engine import Engine
from ..services.event_bus import bus
from ..services.evidence import EvidencePool
from ..services.loader import DatasetLoader
from ..services.store import Store
from .context import ToolContext
from .registry import execute_tool

logger = get_logger(__name__)


class RunCancelled(Exception):
    """用户取消：节点间检查点抛出，runner 捕获后写入 cancelled 状态。"""


class BudgetExhausted(Exception):
    def __init__(self, kind: str, used: int, limit: int) -> None:
        super().__init__(f"预算耗尽：{kind} {used}/{limit}")
        self.kind = kind
        self.used = used
        self.limit = limit


def _preview(data: Any, max_chars: int = 240) -> Any:
    if isinstance(data, dict):
        keys = list(data.keys())
        if "rows" in data and isinstance(data["rows"], list):
            return {"keys": keys, "rows": data["rows"][:3], "row_count": len(data["rows"])}
        if "metrics" in data and isinstance(data["metrics"], list):
            return {
                "keys": keys,
                "metrics": [
                    {"name": m.get("name"), "value": m.get("value"), "groups": (m.get("groups") or [])[:3]}
                    for m in data["metrics"][:2]
                ],
            }
        text = json.dumps(data, ensure_ascii=False, default=str)
        return data if len(text) <= max_chars else {"keys": keys, "preview": text[:max_chars]}
    text = json.dumps(data, ensure_ascii=False, default=str)
    return text[:max_chars]


def _args_summary(arguments: dict[str, Any], max_chars: int = 300) -> dict[str, Any]:
    text = json.dumps(arguments, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return arguments
    return {"truncated": True, "preview": text[:max_chars]}


@dataclass
class RunContext:
    run_id: str
    dataset_id: str
    question: str
    mode: RunMode
    store: Store
    loader: DatasetLoader
    engine: Engine
    evidence: EvidencePool
    settings: Settings
    llm: LLMClient
    budget: Budget
    usage: Usage = field(default_factory=Usage)
    cancel_flag: asyncio.Event = field(default_factory=asyncio.Event)
    model_name: str = "demo-template"
    last_result_id: str | None = None
    budget_hit: str | None = None
    started_monotonic: float = field(default_factory=time.monotonic)
    _tool_ctx: ToolContext | None = None

    # ---------------- 基础设施 ----------------
    @property
    def tool_ctx(self) -> ToolContext:
        if self._tool_ctx is None:
            self._tool_ctx = ToolContext(
                run_id=self.run_id,
                dataset_id=self.dataset_id,
                store=self.store,
                loader=self.loader,
                engine=self.engine,
                evidence=self.evidence,
                settings=self.settings,
                mode=self.mode,
            )
        return self._tool_ctx

    def check_cancel(self) -> None:
        if self.cancel_flag.is_set():
            raise RunCancelled()

    def charge_llm(self, result: LLMResult) -> None:
        self.usage.llm_calls += 1
        self.usage.prompt_tokens += result.prompt_tokens
        self.usage.completion_tokens += result.completion_tokens

    # ---------------- 事件 ----------------
    async def emit(
        self, event_type: str, payload: dict[str, Any], step_id: str | None = None
    ) -> dict[str, Any]:
        normalised = validate_event_payload(event_type, payload)
        event = self.store.append_event(self.run_id, event_type, normalised, step_id=step_id)
        bus.publish(self.run_id, event)
        return event

    def emit_sync_placeholder(self) -> None:  # pragma: no cover - 明确禁止同步发事件
        raise RuntimeError("事件必须通过 await ctx.emit(...) 发送")

    # ---------------- 工具与 LLM ----------------
    def _check_tool_budget(self) -> None:
        used = self.usage.tool_calls_used
        if used >= self.budget.max_tool_calls:
            self.budget_hit = "max_tool_calls"
            raise BudgetExhausted("max_tool_calls", used, self.budget.max_tool_calls)

    async def call_tool(
        self, name: str, arguments: dict[str, Any], step_id: str | None = None
    ) -> ToolEnvelope:
        self.check_cancel()
        try:
            self._check_tool_budget()
        except BudgetExhausted as exc:
            await self.emit(
                "budget_warning",
                {"kind": "max_tool_calls", "used": exc.used, "limit": exc.limit},
                step_id=step_id,
            )
            raise

        call_id = f"call_{self.run_id[-6:]}_{self.usage.tool_calls_used + 1}"
        await self.emit(
            "tool_call_started",
            {"call_id": call_id, "tool": name, "args_summary": _args_summary(arguments)},
            step_id=step_id,
        )
        envelope = await execute_tool(self.tool_ctx, name, arguments, step_id=step_id)
        self.usage.tool_calls_used = self.tool_ctx.tool_calls_used
        if envelope.ok:
            if envelope.result_id:
                self.last_result_id = envelope.result_id
            await self.emit(
                "tool_call_succeeded",
                {
                    "call_id": call_id,
                    "tool": name,
                    "result_id": envelope.result_id,
                    "duration_ms": envelope.meta.duration_ms,
                    "rows_returned": envelope.meta.rows_returned,
                    "data_preview": _preview(envelope.data),
                },
                step_id=step_id,
            )
        else:
            error = envelope.error
            await self.emit(
                "tool_call_failed",
                {
                    "call_id": call_id,
                    "tool": name,
                    # 带上 hint / fields：否则前端和日志只能看到"参数不合法"，
                    # 既没法自助排查，也没法据此修参数。
                    "error": {
                        "code": error.code if error else "INTERNAL_TOOL_ERROR",
                        "message": error.message if error else "工具执行失败",
                        "hint": error.hint if error else None,
                        "fields": list(error.fields or []) if error else [],
                    },
                    "duration_ms": envelope.meta.duration_ms,
                },
                step_id=step_id,
            )
        return envelope

    async def llm_call(
        self,
        *,
        purpose: str,
        system: str,
        user: str,
        json_mode: bool = True,
        max_tokens: int = 2048,
    ) -> LLMResult:
        self.check_cancel()
        result = await self.llm.complete(
            LLMRequest(
                system=system,
                user=user,
                json_mode=json_mode,
                purpose=purpose,
                max_tokens=max_tokens,
            )
        )
        self.charge_llm(result)
        return result
