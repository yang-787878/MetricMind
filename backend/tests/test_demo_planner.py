"""Demo/降级模板叙述单测：分组指标（value=None）不能把报告生成打崩。"""

from __future__ import annotations

from app.agent.demo_planner import build_draft


def _evidence(metrics: list[dict], result_id: str = "res_1") -> list[dict]:
    return [
        {
            "result_id": result_id,
            "tool": "calculate_metrics",
            "step_id": "s1",
            "data": {"metrics": metrics},
        }
    ]


def test_grouped_sum_is_not_crashing_and_scalar_is_used() -> None:
    """分组 sum 的 value 恒为 None；模板必须跳过它，改用后面的标量 sum。"""
    evidence = _evidence(
        [
            {
                "name": "monthly_revenue",
                "kind": "sum",
                "unit": "CNY",
                "value": None,
                "groups": [{"key": {"month": "2025-09"}, "value": 100.0}],
                "formula": "SUM(revenue) GROUP BY month(order_date)",
                "inputs": {"rows_used": 10},
            },
            {
                "name": "total_revenue",
                "kind": "sum",
                "unit": "CNY",
                "value": 400.0,
                "groups": [],
                "formula": "SUM(revenue)",
                "inputs": {"rows_used": 10},
            },
        ]
    )
    draft = build_draft(question="q", plan={}, evidence=evidence, dataset_meta={})
    assert draft["claims"][0]["numbers"] == [{"value": 400.0, "unit": "CNY"}]
    assert "total_revenue" in draft["headline"]


def test_only_grouped_metrics_uses_latest_group() -> None:
    """全程分组时用最新一期的值兜底，而不是给出"未产出结论"。"""
    evidence = _evidence(
        [
            {
                "name": "monthly_revenue",
                "kind": "sum",
                "unit": "CNY",
                "value": None,
                "groups": [
                    {"key": {"month": "2025-08"}, "value": 200.0},
                    {"key": {"month": "2025-09"}, "value": 100.0},
                ],
                "formula": "SUM(revenue) GROUP BY month(order_date)",
                "inputs": {"rows_used": 10},
            }
        ]
    )
    draft = build_draft(question="q", plan={}, evidence=evidence, dataset_meta={})
    assert len(draft["claims"]) == 1
    assert draft["claims"][0]["numbers"] == [{"value": 100.0, "unit": "CNY"}]
    assert "2025-09" in draft["headline"]
    assert draft["headline"] != "本次分析未产出可核验的量化结论。"


def test_share_requires_groups() -> None:
    evidence = _evidence(
        [
            {"name": "share_no_group", "kind": "share", "value": None, "groups": []},
            {
                "name": "share_by_channel",
                "kind": "share",
                "unit": "ratio",
                "value": None,
                "groups": [{"key": {"channel": "DTC"}, "value": 0.75}],
                "formula": "SUM(revenue) / SUM(revenue) GROUP BY channel",
                "inputs": {"rows_used": 4},
            },
        ]
    )
    draft = build_draft(question="q", plan={}, evidence=evidence, dataset_meta={})
    assert any("0.75" in claim["text"] or "75" in claim["text"] for claim in draft["claims"])
