"""Demo 模式确定性单测（§10.2）：同一数据集同一问题两次运行，数值与 KPI 完全一致。"""

from __future__ import annotations

import json

from conftest import GraphHarness


VOLATILE_KEYS = {
    "run_id",
    "generated_at",
    "evidence_ids",
    "result_id",
    "matched_evidence_id",
    "chart_id",
    "charts",
}


def _normalise(value):
    """去掉每次运行都会变的 id/时间戳，只比较"内容本身"。"""
    if isinstance(value, dict):
        return {
            key: _normalise(item)
            for key, item in value.items()
            if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_normalise(item) for item in value]
    return value


async def test_demo_mode_is_deterministic(store, loader, settings, dataset_row) -> None:
    first = GraphHarness(store=store, loader=loader, settings=settings, dataset_row=dataset_row)
    second = GraphHarness(store=store, loader=loader, settings=settings, dataset_row=dataset_row)

    await first.run(mode="demo", question="为什么销售额下降了？")
    await second.run(mode="demo", question="为什么销售额下降了？")

    report_a = first.report()
    report_b = second.report()
    assert report_a and report_b

    assert _normalise(report_a) == _normalise(report_b)
    assert report_a["mode"] == "demo"
    assert report_a["narrative_source"] == "template"
    assert [kpi["display_value"] for kpi in report_a["kpis"]] == [
        kpi["display_value"] for kpi in report_b["kpis"]
    ]
    assert [claim["numbers"] for claim in report_a["claims"]] == [
        claim["numbers"] for claim in report_b["claims"]
    ]


async def test_demo_mode_uses_real_tools(store, harness) -> None:
    await harness.run(mode="demo")
    succeeded = [raw for raw in harness.events() if raw["type"] == "tool_call_succeeded"]
    assert len(succeeded) >= 3, "Demo 模式必须真实调用工具，而不是只渲染模板"

    results = store.list_results(harness.run_id)
    assert results, "results 表必须有证据记录"
    assert any(item["tool"] == "calculate_metrics" for item in results)
    assert any(item["tool"] == "create_chart" for item in results)
    for item in results:
        assert item["run_id"] == harness.run_id
