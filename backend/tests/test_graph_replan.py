"""图重规划与失败路径单测（§10.1 第 6 条）。"""

from __future__ import annotations

import json

import pytest

from app.llm.fake_client import FakeLLM


def _plan_with_bad_column(dataset_id: str) -> dict:
    return {
        "objective": "验证重规划",
        "required_fields": ["revenue"],
        "assumptions": [],
        "steps": [
            {
                "step_id": "s1",
                "title": "计算不存在的列",
                "intent": "触发 INVALID_COLUMN",
                "tool": "calculate_metrics",
                "tool_args_hint": {
                    "dataset_id": dataset_id,
                    "metrics": [{"name": "bad", "kind": "sum", "column": "not_a_column"}],
                },
                "expected_output": "指标",
                "validation": "无",
            }
        ],
        "risks": [],
        "out_of_scope": [],
    }


def _plan_valid(dataset_id: str) -> dict:
    return {
        "objective": "修正后的计划",
        "required_fields": ["revenue"],
        "assumptions": [],
        "steps": [
            {
                "step_id": "s1",
                "title": "计算总收入",
                "intent": "确认规模",
                "tool": "calculate_metrics",
                "tool_args_hint": {
                    "dataset_id": dataset_id,
                    "metrics": [{"name": "total_revenue", "kind": "sum", "column": "revenue"}],
                },
                "expected_output": "总收入",
                "validation": "与行数口径一致",
            }
        ],
        "risks": [],
        "out_of_scope": [],
    }


def _plan_bad_dataset() -> dict:
    return {
        "objective": "引用不存在的数据集",
        "required_fields": [],
        "assumptions": [],
        "steps": [
            {
                "step_id": "s1",
                "title": "错误数据集",
                "intent": "触发 DATASET_NOT_FOUND",
                "tool": "calculate_metrics",
                "tool_args_hint": {
                    "dataset_id": "ds_not_exists",
                    "metrics": [{"name": "x", "kind": "count"}],
                },
                "expected_output": "无",
                "validation": "无",
            }
        ],
        "risks": [],
        "out_of_scope": [],
    }


def _reporter(store, run_id):
    def build(_request):
        results = [item for item in store.list_results(run_id) if item["tool"] == "calculate_metrics"]
        total = results[-1]["payload"]["data"]["metrics"][0]["value"]
        return json.dumps(
            {
                "title": "重规划后的报告",
                "headline": "总收入已由工具计算",
                "sections": [
                    {
                        "heading": "结论",
                        "body": "总收入来自工具结果。",
                        "evidence_ids": [results[-1]["result_id"]],
                    }
                ],
                "claims": [
                    {
                        "claim_id": "c1",
                        "text": "总收入",
                        "numbers": [{"value": total, "unit": "CNY"}],
                        "evidence_ids": [results[-1]["result_id"]],
                    }
                ],
                "limitations": [],
                "next_steps": [],
            },
            ensure_ascii=False,
        )

    return build


async def test_replan_recovers_from_invalid_column(harness) -> None:
    dataset_id = harness.dataset_id
    llm = FakeLLM(
        responses=[
            json.dumps(_plan_with_bad_column(dataset_id)),
            json.dumps({"step_id": "s1", "tool": None, "reason": "列不存在，无法修复"}),
            json.dumps(_plan_valid(dataset_id)),
            _reporter(harness.store, harness.run_id),
        ]
    )
    final = await harness.run(mode="live", llm=llm)

    types = harness.event_types()
    assert "replan_requested" in types, f"应触发重规划：{types}"
    assert "run_succeeded" in types
    assert final["status"] == "succeeded"
    report = harness.report()
    assert report is not None
    assert report["verification"]["coverage"] >= 0.9
    assert harness.run_row()["status"] == "succeeded"


async def test_unrecoverable_dataset_error_marks_failed(harness) -> None:
    """不可恢复错误（引用别的数据集）→ execute 判定 fail → fail → finalize(failed)。

    注意：计划里的 dataset_id 现在由服务端注入，模型无法再写错；
    所以这里直接构造一个跨数据集的步骤，专门验证 execute 的 fatal 分支。
    """
    from app.agent.nodes import execute as execute_node
    from app.agent.nodes import fail as fail_node
    from app.agent.nodes import finalize as finalize_node

    await harness.run(mode="demo")  # 建立 context / 证据池
    ctx = harness.context
    assert ctx is not None
    events_before = len(harness.events())

    state = {
        "steps": [
            {
                "step_id": "s1",
                "title": "错误的跨数据集步骤",
                "intent": "触发 DATASET_NOT_FOUND",
                "tool": "calculate_metrics",
                "tool_args_hint": {
                    "dataset_id": "ds_not_exists",
                    "metrics": [{"name": "x", "kind": "count"}],
                },
                "status": "pending",
                "tool_calls": [],
            }
        ],
        "step_index": 0,
        "step_results": [],
        "warnings": [],
        "dataset_id": harness.dataset_id,
        "question": "不可恢复错误",
        "mode": "demo",
    }

    executed = await execute_node.execute(state, ctx)
    assert executed["routing"] == "fail"
    assert executed["error"]["code"] == "DATASET_NOT_FOUND"

    state.update(executed)
    failed = await fail_node.fail(state, ctx)
    assert failed["status"] == "failed"
    state.update(failed)
    await finalize_node.finalize(state, ctx)

    row = harness.run_row()
    assert row["status"] == "failed"
    error = json.loads(row["error_json"])
    assert error["code"] == "DATASET_NOT_FOUND"
    new_types = [event["type"] for event in harness.events()[events_before:]]
    assert new_types[-1] == "run_failed"
    assert "run_succeeded" not in new_types


async def test_budget_exhaustion_is_partial(harness, settings) -> None:
    from app.models.run import Budget

    budget = Budget(max_steps=10, max_tool_calls=3, max_replans=0, timeout_seconds=60)
    final = await harness.run(mode="demo", budget=budget)
    types = harness.event_types()
    assert "budget_warning" in types
    assert final["status"] == "partial"
    assert harness.run_row()["status"] == "partial"
    report = harness.report()
    assert report is not None
    assert any("预算" in item for item in report["limitations"])
