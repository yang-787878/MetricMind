"""节点共用的小工具：步骤记录、时间戳、占位符解析。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

PLACEHOLDER_STEP = "$step:"
DATASET_TOOLS = frozenset({"inspect_dataset", "profile_dataset", "query_data", "calculate_metrics"})


def with_dataset_id(tool: str, args: dict[str, Any], dataset_id: str) -> dict[str, Any]:
    """数据集 id 由服务端注入，避免模型编造（实测 DeepSeek 会把 dataset_id 写成 "data"）。"""
    if tool in DATASET_TOOLS:
        return {**args, "dataset_id": dataset_id}
    return args


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def step_records_from_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "step_id": step["step_id"],
            "title": step.get("title", ""),
            "intent": step.get("intent", ""),
            "tool": step["tool"],
            "tool_args_hint": step.get("tool_args_hint") or {},
            "expected_output": step.get("expected_output", ""),
            "validation": step.get("validation", ""),
            "status": "pending",
            "summary": "",
            "tool_calls": [],
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "error": None,
        }
        for step in plan.get("steps", [])
    ]


def step_result_id(state: dict[str, Any], step_id: str) -> str | None:
    for item in reversed(state.get("step_results") or []):
        if item.get("step_id") == step_id and item.get("result_id"):
            return str(item["result_id"])
    return None


def resolve_placeholders(
    args: Any, state: dict[str, Any], last_result_id: str | None
) -> Any:
    """把 `$step:s2` / `$last_result` 替换成真实 result_id。

    计划在生成时不可能知道未来 result_id（它由执行决定），所以用占位符表达依赖，
    由执行节点在真实结果产生后解析——这样"图表只能引用真实结果"依然成立。
    """
    if isinstance(args, dict):
        return {key: resolve_placeholders(value, state, last_result_id) for key, value in args.items()}
    if isinstance(args, list):
        return [resolve_placeholders(item, state, last_result_id) for item in args]
    if isinstance(args, str):
        if args.startswith(PLACEHOLDER_STEP):
            return step_result_id(state, args[len(PLACEHOLDER_STEP):]) or args
        if args == "$last_result":
            return last_result_id or args
    return args


def describe_args(args: Any) -> str:
    try:
        return json.dumps(args, ensure_ascii=False)[:300]
    except (TypeError, ValueError):  # pragma: no cover - 参数都应可序列化
        return str(args)[:300]
