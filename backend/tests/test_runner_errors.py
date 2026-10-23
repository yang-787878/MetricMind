"""Runner 错误分类单测：模型侧错误不能被兜底成 INTERNAL_ERROR。"""

from __future__ import annotations

from app.errors import AppError, ErrorCode
from app.llm.base import LLMError
from app.runner import RunManager, classify_run_failure


def test_llm_error_maps_to_llm_unavailable() -> None:
    code, message = classify_run_failure(
        LLMError("Error code: 400 - model not supported", code="LLM_UNAVAILABLE")
    )
    assert code == ErrorCode.LLM_UNAVAILABLE.value
    assert "model not supported" in message


def test_llm_error_without_code_defaults_to_unavailable() -> None:
    code, _ = classify_run_failure(LLMError("boom", code=""))
    assert code == ErrorCode.LLM_UNAVAILABLE.value


def test_app_error_keeps_its_code() -> None:
    code, message = classify_run_failure(AppError(ErrorCode.LLM_INVALID_OUTPUT, "计划非法"))
    assert code == ErrorCode.LLM_INVALID_OUTPUT.value
    assert message == "计划非法"


def test_unknown_error_falls_back_to_internal() -> None:
    code, message = classify_run_failure(RuntimeError("boom"))
    assert code == ErrorCode.INTERNAL_ERROR.value
    assert message


def test_message_is_truncated_to_one_line() -> None:
    code, message = classify_run_failure(LLMError("first line\nsecond line\nthird line"))
    assert code == ErrorCode.LLM_UNAVAILABLE.value
    assert message == "first line"


def test_progress_snapshot_keeps_steps_and_evidence_ids() -> None:
    """失败的 run 也要把计划与已执行步骤落库，否则前端工作区是空白的。"""
    state = {
        "plan_version": 1,
        "plan": {"objective": "x", "steps": []},
        "steps": [
            {"step_id": "s1", "status": "succeeded", "tool_calls": [{"result_id": "res_1"}]},
            {"step_id": "s2", "status": "failed", "tool_calls": [{"result_id": None}]},
        ],
        "warnings": ["w"],
        "replan_count": 1,
    }
    snapshot = RunManager._progress(state)
    assert snapshot["plan_json"]
    assert '"s1"' in snapshot["state_json"]
    assert '"res_1"' in snapshot["state_json"]


def test_progress_snapshot_is_empty_without_state() -> None:
    assert RunManager._progress(None) == {}

