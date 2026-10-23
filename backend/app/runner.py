"""Runner：后台任务、并发信号量、取消、超时（§6.2 / §8 并发与限流）。

一个 run 一旦创建就由后台 task 持有：
- 客户端断开不影响执行；
- 取消通过 asyncio.Event 在节点间检查点生效；
- 超时由外层 asyncio.wait_for 兜底，超时后标记 failed(RUN_TIMEOUT)。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from .agent.graph import build_graph
from .agent.run_context import RunContext, RunCancelled
from .agent.state import initial_state
from .config import Settings
from .errors import AppError, ErrorCode
from .llm.base import LLMError
from .llm.factory import build_llm
from .logging_conf import get_logger
from .models.enums import RequestedMode, RunMode, RunStatus, TERMINAL_RUN_STATUSES
from .models.events import validate_event_payload
from .models.run import Budget
from .services.engine import Engine
from .services.evidence import EvidencePool
from .services.event_bus import bus
from .services.loader import DatasetLoader
from .services.store import Store, get_store, utcnow_iso

logger = get_logger(__name__)


def _emit(store: Store, run_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalised = validate_event_payload(event_type, payload)
    event = store.append_event(run_id, event_type, normalised)
    bus.publish(run_id, event)
    return event


def classify_run_failure(exc: Exception) -> tuple[str, str]:
    """把运行期异常映射成对用户有意义的错误码与一句话说明。

    为什么单独抽出来：`LLMError` 不是 `AppError`，之前会被兜底成 INTERNAL_ERROR，
    让"模型名写错 / Key 无效"看起来像服务端 bug。这里显式分类，并可单测。
    """
    if isinstance(exc, AppError):
        return exc.code, exc.message
    if isinstance(exc, LLMError):
        message = str(exc).strip().splitlines()[0][:300]
        return exc.code or ErrorCode.LLM_UNAVAILABLE.value, message or "大模型调用失败"
    return ErrorCode.INTERNAL_ERROR.value, "运行出现未预期错误"


class RunManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.semaphore = asyncio.Semaphore(max(settings.max_concurrent_runs, 1))
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.cancel_flags: dict[str, asyncio.Event] = {}
        self.engine = Engine()

    # ---------------- 创建 ----------------
    def resolve_mode(self, requested: RequestedMode) -> RunMode:
        if requested is RequestedMode.DEMO:
            return RunMode.DEMO
        if requested is RequestedMode.LIVE:
            if not self.settings.has_api_key:
                raise AppError(
                    ErrorCode.LLM_NOT_CONFIGURED,
                    "未配置大模型 API Key，无法以 live 模式运行",
                    details={"action": "switch_to_demo"},
                    hint="在 .env 配置 OPENAI_API_KEY，或选择 Demo 模式",
                )
            return RunMode.LIVE
        return RunMode(self.settings.resolved_llm_mode)

    async def create_run(
        self, *, dataset_id: str, question: str, requested: RequestedMode
    ) -> dict[str, Any]:
        store = get_store()
        dataset = store.get_dataset(dataset_id)
        if dataset is None:
            raise AppError(
                ErrorCode.DATASET_NOT_FOUND,
                f"数据集 {dataset_id} 不存在",
                details={"dataset_id": dataset_id},
            )
        mode = self.resolve_mode(requested)
        run_id = f"run_{uuid.uuid4().hex[:20]}"
        created_at = utcnow_iso()
        store.insert_run(
            {
                "run_id": run_id,
                "dataset_id": dataset_id,
                "question": question.strip(),
                "mode": mode.value,
                "model": "demo-template" if mode is RunMode.DEMO else self.settings.llm_model,
                "status": RunStatus.QUEUED.value,
                "plan_json": None,
                "state_json": None,
                "report_json": None,
                "verification_json": None,
                "usage_json": None,
                "error_json": None,
                "created_at": created_at,
                "started_at": None,
                "finished_at": None,
            }
        )
        _emit(store, run_id, "run_created", {"run_id": run_id, "mode": mode.value, "dataset_id": dataset_id})
        task = asyncio.create_task(self._execute(run_id), name=f"run:{run_id}")
        self.tasks[run_id] = task
        logger.info(
            "run_created",
            extra={"run_id": run_id, "dataset_id": dataset_id, "mode": mode.value},
        )
        return {
            "run_id": run_id,
            "status": RunStatus.QUEUED.value,
            "mode": mode.value,
            "stream_url": f"{self.settings.api_prefix}/runs/{run_id}/stream",
        }

    # ---------------- 执行 ----------------
    async def _execute(self, run_id: str) -> None:
        store = get_store()
        run = store.get_run(run_id)
        if run is None:  # pragma: no cover - 理论上不会发生
            return
        row = store.get_dataset(run["dataset_id"])
        if row is None:
            self._finalise_failure(store, run_id, "DATASET_NOT_FOUND", "数据集在运行前被删除")
            return

        mode = RunMode(run["mode"])
        llm = build_llm(self.settings, mode.value)
        ctx = RunContext(
            run_id=run_id,
            dataset_id=run["dataset_id"],
            question=run["question"],
            mode=mode,
            store=store,
            loader=DatasetLoader(store, self.settings),
            engine=self.engine,
            evidence=EvidencePool(store, run_id),
            settings=self.settings,
            llm=llm,
            budget=Budget(
                max_steps=self.settings.max_steps,
                max_tool_calls=self.settings.max_tool_calls,
                max_replans=self.settings.max_replans,
                timeout_seconds=self.settings.run_timeout_s,
            ),
            model_name="demo-template" if mode is RunMode.DEMO else self.settings.llm_model,
        )
        self.cancel_flags[run_id] = ctx.cancel_flag

        # 失败时也要保住进度：用 astream 累积每个节点后的最新 state，
        # 否则崩溃的 run 在 state_json 里什么都没有，前端工作区一片空白。
        latest_state: dict[str, Any] = {}

        async def _run_graph() -> None:
            async for chunk in graph.astream(
                state, config={"recursion_limit": 80}, stream_mode="values"
            ):
                if isinstance(chunk, dict):
                    latest_state.update(chunk)

        try:
            async with self.semaphore:
                if ctx.cancel_flag.is_set():
                    raise RunCancelled()
                store.update_run(run_id, status=RunStatus.RUNNING.value, started_at=utcnow_iso())
                graph = build_graph(ctx)
                state = initial_state(
                    run_id=run_id,
                    dataset_id=run["dataset_id"],
                    question=run["question"],
                    mode=mode.value,
                )
                await asyncio.wait_for(_run_graph(), timeout=self.settings.run_timeout_s)
        except RunCancelled:
            self._finalise_cancelled(store, run_id, latest_state)
        except (TimeoutError, asyncio.TimeoutError):
            self._finalise_failure(
                store,
                run_id,
                ErrorCode.RUN_TIMEOUT.value,
                f"运行超过 {self.settings.run_timeout_s}s 未完成，已终止",
                latest_state,
            )
        except AppError as exc:
            self._finalise_failure(store, run_id, exc.code, exc.message, latest_state)
        except LLMError as exc:
            code, message = classify_run_failure(exc)
            self._finalise_failure(store, run_id, code, message, latest_state)
        except Exception as exc:  # pragma: no cover - 兜底
            logger.exception("run_crashed", extra={"run_id": run_id, "error": str(exc)[:300]})
            code, message = classify_run_failure(exc)
            self._finalise_failure(store, run_id, code, message, latest_state)
        finally:
            self.engine.close_run(run_id)
            self.cancel_flags.pop(run_id, None)
            self.tasks.pop(run_id, None)

    # ---------------- 终态 ----------------
    @staticmethod
    def _progress(
        state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """把失败/取消时的进度整理成可落库的字段，保证前端还能看到计划与已执行步骤。"""
        if not state:
            return {}
        steps = state.get("steps") or []
        snapshot = {
            "plan_version": state.get("plan_version"),
            "steps": steps,
            "warnings": state.get("warnings") or [],
            "evidence_ids": sorted(
                {
                    str(call.get("result_id"))
                    for step in steps
                    for call in step.get("tool_calls") or []
                    if call.get("result_id")
                }
            ),
            "replan_count": state.get("replan_count"),
            "audit_attempts": state.get("audit_attempts"),
        }
        return {
            "plan_json": json.dumps(state.get("plan"), ensure_ascii=False),
            "state_json": json.dumps(snapshot, ensure_ascii=False),
        }

    def _finalise_failure(
        self,
        store: Store,
        run_id: str,
        code: str,
        message: str,
        state: dict[str, Any] | None = None,
    ) -> None:
        run = store.get_run(run_id) or {}
        if run.get("status") in {status.value for status in TERMINAL_RUN_STATUSES}:
            return
        finished_at = utcnow_iso()
        error = {"code": code, "message": message, "hint": "可重试一次；若持续失败请检查配置"}
        store.update_run(
            run_id,
            status=RunStatus.FAILED.value,
            error_json=json.dumps(error, ensure_ascii=False),
            finished_at=finished_at,
            **self._progress(state),
        )
        _emit(
            store,
            run_id,
            "run_failed",
            {
                "status": RunStatus.FAILED.value,
                "finished_at": finished_at,
                "duration_ms": self._duration_ms(run),
                "error": {"code": code, "message": message},
            },
        )
        logger.warning("run_failed", extra={"run_id": run_id, "code": code})

    def _finalise_cancelled(
        self, store: Store, run_id: str, state: dict[str, Any] | None = None
    ) -> None:
        run = store.get_run(run_id) or {}
        if run.get("status") in {status.value for status in TERMINAL_RUN_STATUSES}:
            return
        finished_at = utcnow_iso()
        store.update_run(
            run_id,
            status=RunStatus.CANCELLED.value,
            finished_at=finished_at,
            error_json=json.dumps(
                {"code": "RUN_CANCELLED", "message": "用户取消", "hint": None}, ensure_ascii=False
            ),
            **self._progress(state),
        )
        _emit(
            store,
            run_id,
            "run_cancelled",
            {
                "status": RunStatus.CANCELLED.value,
                "finished_at": finished_at,
                "duration_ms": self._duration_ms(run),
                "error": None,
            },
        )
        logger.info("run_cancelled", extra={"run_id": run_id})

    @staticmethod
    def _duration_ms(run: dict[str, Any]) -> int | None:
        started = run.get("started_at") or run.get("created_at")
        if not started:
            return None
        try:
            from datetime import datetime

            parsed = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            return int((time.time() - parsed.timestamp()) * 1000)
        except ValueError:  # pragma: no cover - 时间格式异常
            return None

    # ---------------- 取消 ----------------
    async def cancel(self, run_id: str) -> str:
        store = get_store()
        run = store.get_run(run_id)
        if run is None:
            raise AppError(ErrorCode.RUN_NOT_FOUND, f"运行 {run_id} 不存在", details={"run_id": run_id})
        if run["status"] in {status.value for status in TERMINAL_RUN_STATUSES}:
            raise AppError(
                ErrorCode.RUN_ALREADY_FINISHED,
                "运行已结束，无法取消",
                details={"status": run["status"]},
            )
        flag = self.cancel_flags.get(run_id)
        if flag is not None:
            flag.set()
        else:  # 还没进入执行（队列中）
            self._finalise_cancelled(store, run_id)
            return RunStatus.CANCELLED.value
        return "cancelling"

    def is_active(self, run_id: str) -> bool:
        return run_id in self.tasks and not self.tasks[run_id].done()

    async def shutdown(self) -> None:
        for task in list(self.tasks.values()):
            task.cancel()
        self.engine.close_all()


_manager: RunManager | None = None


def get_run_manager(settings: Settings | None = None) -> RunManager:
    global _manager
    if _manager is None:
        from .config import get_settings

        _manager = RunManager(settings or get_settings())
    return _manager


def reset_run_manager() -> None:
    """测试用：丢弃单例，避免跨用例共享信号量与引擎状态。"""
    global _manager
    _manager = None
