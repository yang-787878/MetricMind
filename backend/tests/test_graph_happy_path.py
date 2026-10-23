"""图主线单测（§10.1 第 5 条）：FakeLLM 脚本化计划 + 真实工具执行。"""

from __future__ import annotations

import json

import pytest

from app.llm.fake_client import FakeLLM

TOTAL = "19702878.99"


def _plan(dataset_id: str) -> dict:
    return {
        "objective": "定位销售额变化并给出结构分布",
        "required_fields": ["revenue", "channel"],
        "assumptions": ["revenue 为含税金额"],
        "steps": [
            {
                "step_id": "s1",
                "title": "计算总收入",
                "intent": "确认整体规模",
                "tool": "calculate_metrics",
                "tool_args_hint": {
                    "dataset_id": dataset_id,
                    "metrics": [{"name": "total_revenue", "kind": "sum", "column": "revenue"}],
                },
                "expected_output": "总收入数值",
                "validation": "与 profile 的行数口径一致",
            },
            {
                "step_id": "s2",
                "title": "按渠道拆分收入",
                "intent": "找出主要渠道",
                "tool": "calculate_metrics",
                "tool_args_hint": {
                    "dataset_id": dataset_id,
                    "metrics": [
                        {
                            "name": "revenue_by_channel",
                            "kind": "sum",
                            "column": "revenue",
                            "group_by": ["channel"],
                            "sort": {"by": "value", "order": "desc"},
                        }
                    ],
                },
                "expected_output": "各渠道收入",
                "validation": "各渠道之和等于总收入",
            },
            {
                "step_id": "s3",
                "title": "画渠道收入柱状图",
                "intent": "可视化结构",
                "tool": "create_chart",
                "tool_args_hint": {
                    "from_result_id": "$step:s2",
                    "type": "bar",
                    "x": "channel",
                    "y": "revenue_by_channel",
                    "title": "各渠道收入",
                },
                "expected_output": "ChartSpec",
                "validation": "图表数据与 s2 一致",
            },
        ],
        "risks": ["渠道缺失值会影响占比"],
        "out_of_scope": [],
    }


def _reporter(store, run_id):
    def build(_request):
        results = [item for item in store.list_results(run_id) if item["tool"] == "calculate_metrics"]
        total = results[0]
        channels = results[1]
        top = channels["payload"]["data"]["metrics"][0]["groups"][0]
        return json.dumps(
            {
                "title": "销售额分析",
                "headline": f"总收入 {TOTAL}",
                "sections": [
                    {
                        "heading": "总体规模",
                        "body": "总收入来自工具汇总结果。",
                        "evidence_ids": [total["result_id"]],
                    }
                ],
                "claims": [
                    {
                        "claim_id": "c1",
                        "text": "总收入",
                        "numbers": [{"value": total["payload"]["data"]["metrics"][0]["value"], "unit": "CNY"}],
                        "evidence_ids": [total["result_id"]],
                    },
                    {
                        "claim_id": "c2",
                        "text": "最大渠道收入",
                        "numbers": [{"value": top["value"], "unit": "CNY"}],
                        "evidence_ids": [channels["result_id"]],
                    },
                ],
                "limitations": ["渠道缺失值可能导致占比偏移"],
                "next_steps": ["按品类再拆一层"],
            },
            ensure_ascii=False,
        )

    return build


@pytest.fixture
def sample_harness(store, loader, settings, real_sample_csv):
    from conftest import GraphHarness

    row = loader.create_from_upload("sample_sales.csv", real_sample_csv.read_bytes())
    return GraphHarness(store=store, loader=loader, settings=settings, dataset_row=row)


async def test_happy_path_events_and_report(sample_harness, expected_answers) -> None:
    dataset_id = sample_harness.dataset_id
    llm = FakeLLM(responses=[json.dumps(_plan(dataset_id)), _reporter(sample_harness.store, sample_harness.run_id)])

    final = await sample_harness.run(mode="live", llm=llm, question="为什么 9 月销售额下降了？")
    types = sample_harness.event_types()

    for expected_event in (
        "plan_created",
        "step_started",
        "tool_call_started",
        "tool_call_succeeded",
        "verification_completed",
        "report_created",
        "run_succeeded",
    ):
        assert expected_event in types, f"缺少事件 {expected_event}"

    order = [
        "plan_created",
        "step_started",
        "tool_call_started",
        "tool_call_succeeded",
        "verification_completed",
        "report_created",
        "run_succeeded",
    ]
    cursor = -1
    for name in order:
        positions = [index for index, value in enumerate(types) if value == name and index > cursor]
        assert positions, f"事件 {name} 未出现在预期位置之后：{types}"
        cursor = positions[0]

    report = sample_harness.report()
    assert report is not None
    expected_total = expected_answers["sales"]["total_revenue"]["value"]
    assert float(report["kpis"][0]["value"]) == pytest.approx(expected_total, rel=1e-6)
    assert report["verification"]["coverage"] >= 0.9
    assert len(report["charts"]) == 1
    assert sample_harness.run_row()["status"] == "succeeded"
    assert final["status"] == "succeeded"
