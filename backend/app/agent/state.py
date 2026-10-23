"""AgentState（§6.1）：LangGraph 在节点之间传递的唯一状态。

约束：
- 节点只读自己需要的字段，返回增量 dict；
- 列表字段（steps / warnings / step_results）由节点返回**完整新列表**，避免依赖 reducer；
- `evidence_pool` 只存摘要（result_id → {tool, step_id, numbers}），真正的 payload 在 SQLite。
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    dataset_id: str
    question: str
    mode: str

    dataset_meta: dict[str, Any]
    field_summary: dict[str, Any]
    quality: list[dict[str, Any]]

    plan: dict[str, Any] | None
    plan_version: int
    step_index: int
    steps: list[dict[str, Any]]
    step_results: list[dict[str, Any]]

    evidence_pool: dict[str, dict[str, Any]]
    replan_count: int
    repair_count: int
    audit_attempts: int

    warnings: list[str]
    verification: dict[str, Any] | None
    draft: dict[str, Any] | None
    report: dict[str, Any] | None
    audit_feedback: list[str]

    status: str
    error: dict[str, Any] | None
    routing: str
    failed_step: str | None
    token_usage: dict[str, int]


def initial_state(
    *,
    run_id: str,
    dataset_id: str,
    question: str,
    mode: str,
) -> AgentState:
    return AgentState(
        run_id=run_id,
        dataset_id=dataset_id,
        question=question,
        mode=mode,
        dataset_meta={},
        field_summary={},
        quality=[],
        plan=None,
        plan_version=1,
        step_index=0,
        steps=[],
        step_results=[],
        evidence_pool={},
        replan_count=0,
        repair_count=0,
        audit_attempts=0,
        warnings=[],
        verification=None,
        draft=None,
        report=None,
        audit_feedback=[],
        status="running",
        error=None,
        routing="continue",
        failed_step=None,
        token_usage={"llm_calls": 0, "prompt_tokens": 0, "completion_tokens": 0},
    )
