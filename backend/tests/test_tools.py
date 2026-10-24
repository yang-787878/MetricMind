"""工具层单测（§10.1）：成功 / 参数非法 / 空结果 / 列不存在 / 结果集引用失效 / 预算。"""

from __future__ import annotations

import pytest

from app.agent.registry import TOOLS, execute_tool
from app.errors import ErrorCode


async def test_seven_tool_contract_registered() -> None:
    assert set(TOOLS) == {
        "inspect_dataset",
        "profile_dataset",
        "query_data",
        "calculate_metrics",
        "create_chart",
        "verify_result",
        "export_report",
    }
    for spec in TOOLS.values():
        schema = spec.json_schema()
        assert schema["parameters"]["type"] == "object"
        assert schema["parameters"]["additionalProperties"] is False
        assert spec.max_calls_per_run >= 1
    # export_report 只在运行结束后可用，不进入规划器的候选工具集
    from app.agent.registry import tool_schemas

    planner_names = {schema["name"] for schema in tool_schemas(planner_only=True)}
    assert "export_report" not in planner_names
    assert len(planner_names) == 6


async def test_inspect_dataset_success(ctx) -> None:
    envelope = await execute_tool(ctx, "inspect_dataset", {"dataset_id": ctx.dataset_id})
    assert envelope.ok
    assert envelope.result_id and envelope.result_id.startswith("res_")
    data = envelope.data
    assert data["row_count"] == 60
    assert data["column_count"] == 9
    assert data["candidate_date_column"] == "order_date"
    assert data["time_range"]["min"].startswith("2025-01")
    assert "revenue" in data["candidate_metrics"]
    assert "channel" in data["candidate_dimensions"]


async def test_inspect_dataset_rejects_extra_fields(ctx) -> None:
    envelope = await execute_tool(
        ctx, "inspect_dataset", {"dataset_id": ctx.dataset_id, "unknown": 1}
    )
    assert not envelope.ok
    assert envelope.error.code == ErrorCode.VALIDATION_ERROR.value


async def test_profile_dataset_success(ctx) -> None:
    envelope = await execute_tool(ctx, "profile_dataset", {"dataset_id": ctx.dataset_id})
    assert envelope.ok
    assert envelope.data["method"] == "IQR 1.5"
    assert envelope.data["row_count"] == 60
    assert {issue["code"] for issue in envelope.data["issues"]} <= {
        "NULL_VALUES",
        "DUPLICATE_ROWS",
        "ZERO_OR_NEGATIVE",
        "OUTLIERS_IQR",
        "CONSTANT_COLUMN",
        "HIGH_CARDINALITY",
        "DATE_UNPARSEABLE",
        "TYPE_MIXED",
    }
    assert envelope.data["columns"][0]["null_count"] == 0


async def test_profile_dataset_invalid_column(ctx) -> None:
    envelope = await execute_tool(
        ctx, "profile_dataset", {"dataset_id": ctx.dataset_id, "columns": ["nope"]}
    )
    assert not envelope.ok
    assert envelope.error.code == ErrorCode.INVALID_COLUMN.value


async def test_query_data_success_and_truncation(ctx) -> None:
    envelope = await execute_tool(
        ctx,
        "query_data",
        {
            "dataset_id": ctx.dataset_id,
            "sql": "SELECT channel, SUM(revenue) AS revenue FROM data GROUP BY channel",
            "max_rows": 2,
        },
    )
    assert envelope.ok
    assert envelope.result_id
    assert envelope.data["row_count"] == 2
    assert envelope.data["truncated"] is True
    assert "截断" in " ".join(envelope.meta.warnings)


async def test_query_data_month_label_compares_as_text(
    loader, store, engine, settings
) -> None:
    """回归：order_month 为 YYYY-MM 时必须保持文本，SQL 才能按 '2018-07' 等值过滤。"""
    from app.agent.context import ToolContext
    from app.services.evidence import EvidencePool

    payload = (
        "order_id,order_month,item_total\n"
        "o1,2018-07,100\n"
        "o2,2018-07,50\n"
        "o3,2018-08,80\n"
    ).encode("utf-8")
    row = loader.create_from_upload("month_sales.csv", payload)
    ctx = ToolContext(
        run_id="run_month",
        dataset_id=row["dataset_id"],
        store=store,
        loader=loader,
        engine=engine,
        evidence=EvidencePool(store, "run_month"),
        settings=settings,
    )
    envelope = await execute_tool(
        ctx,
        "query_data",
        {
            "dataset_id": row["dataset_id"],
            "sql": (
                "SELECT order_month, SUM(item_total) AS gmv FROM data "
                "WHERE order_month IN ('2018-07', '2018-08') "
                "GROUP BY order_month ORDER BY order_month"
            ),
        },
    )
    assert envelope.ok, envelope.error
    rows = {row_item[0]: float(row_item[1]) for row_item in envelope.data["rows"]}
    assert rows == {"2018-07": 150.0, "2018-08": 80.0}


async def test_query_data_empty_result(ctx) -> None:
    envelope = await execute_tool(
        ctx,
        "query_data",
        {"dataset_id": ctx.dataset_id, "sql": "SELECT * FROM data WHERE revenue < 0"},
    )
    assert envelope.ok
    assert envelope.data["row_count"] == 0
    assert any("0 行" in warning for warning in envelope.meta.warnings)


async def test_query_data_guard_rejects_write(ctx) -> None:
    envelope = await execute_tool(
        ctx, "query_data", {"dataset_id": ctx.dataset_id, "sql": "DROP TABLE data"}
    )
    assert not envelope.ok
    assert envelope.error.code == ErrorCode.SQL_REJECTED.value


async def test_query_data_bad_column_is_execution_error(ctx) -> None:
    envelope = await execute_tool(
        ctx,
        "query_data",
        {"dataset_id": ctx.dataset_id, "sql": "SELECT missing_column FROM data"},
    )
    assert not envelope.ok
    assert envelope.error.code == ErrorCode.SQL_EXECUTION_ERROR.value


async def test_calculate_metrics_success_and_chart(ctx) -> None:
    metrics = await execute_tool(
        ctx,
        "calculate_metrics",
        {
            "dataset_id": ctx.dataset_id,
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
    )
    assert metrics.ok
    assert metrics.result_id
    assert len(metrics.data["metrics"][0]["groups"]) == 3

    chart = await execute_tool(
        ctx,
        "create_chart",
        {
            "from_result_id": metrics.result_id,
            "type": "bar",
            "x": "channel",
            "y": "revenue_by_channel",
            "title": "各渠道销售额",
        },
    )
    assert chart.ok
    assert chart.data["source"]["result_id"] == metrics.result_id
    assert len(chart.data["data"]) == 3


async def test_create_chart_requires_existing_result(ctx) -> None:
    envelope = await execute_tool(
        ctx,
        "create_chart",
        {
            "from_result_id": "res_does_not_exist",
            "type": "bar",
            "x": "channel",
            "y": "revenue",
            "title": "x",
        },
    )
    assert not envelope.ok
    assert envelope.error.code == ErrorCode.RESULT_NOT_FOUND.value


async def test_create_chart_invalid_column(ctx) -> None:
    metrics = await execute_tool(
        ctx,
        "calculate_metrics",
        {
            "dataset_id": ctx.dataset_id,
            "metrics": [{"name": "rev", "kind": "sum", "column": "revenue", "group_by": ["channel"]}],
        },
    )
    envelope = await execute_tool(
        ctx,
        "create_chart",
        {
            "from_result_id": metrics.result_id,
            "type": "bar",
            "x": "channel",
            "y": "missing_metric",
            "title": "x",
        },
    )
    assert not envelope.ok
    assert envelope.error.code == ErrorCode.INVALID_COLUMN.value


async def test_calculate_metrics_accepts_top_level_limit(ctx) -> None:
    """模型常把 limit 写在调用层；应作为所有指标的默认条数上限，而不是报 VALIDATION_ERROR。"""
    envelope = await execute_tool(
        ctx,
        "calculate_metrics",
        {
            "dataset_id": ctx.dataset_id,
            "limit": 2,
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
    )
    assert envelope.ok, envelope.error
    assert len(envelope.data["metrics"][0]["groups"]) == 2


async def test_calculate_metrics_invalid_column(ctx) -> None:
    envelope = await execute_tool(
        ctx,
        "calculate_metrics",
        {"dataset_id": ctx.dataset_id, "metrics": [{"name": "x", "kind": "sum", "column": "nope"}]},
    )
    assert not envelope.ok
    assert envelope.error.code == ErrorCode.INVALID_COLUMN.value


async def test_verify_result_supports_and_rejects(ctx) -> None:
    metrics = await execute_tool(
        ctx,
        "calculate_metrics",
        {
            "dataset_id": ctx.dataset_id,
            "metrics": [{"name": "rev", "kind": "sum", "column": "revenue"}],
        },
    )
    true_value = metrics.data["metrics"][0]["value"]
    envelope = await execute_tool(
        ctx,
        "verify_result",
        {
            "run_id": ctx.run_id,
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "总收入",
                    "numbers": [{"value": true_value, "unit": "CNY"}],
                    "evidence_ids": [metrics.result_id],
                },
                {
                    "claim_id": "c2",
                    "text": "编造",
                    "numbers": [{"value": true_value * 3, "unit": "CNY"}],
                    "evidence_ids": [metrics.result_id],
                },
                {
                    "claim_id": "c3",
                    "text": "没有证据",
                    "numbers": [{"value": 1.0, "unit": "count"}],
                    "evidence_ids": [],
                },
            ],
        },
    )
    assert envelope.ok
    statuses = {item["claim_id"]: item["status"] for item in envelope.data["items"]}
    assert statuses["c1"] == "supported"
    assert statuses["c2"] in {"unsupported", "unverifiable"}
    assert statuses["c3"] == "unsupported"
    assert envelope.data["coverage"] == pytest.approx(1 / 3, abs=1e-6)


async def test_verify_result_rejects_foreign_run(ctx) -> None:
    envelope = await execute_tool(
        ctx,
        "verify_result",
        {
            "run_id": "run_other",
            "claims": [{"claim_id": "c1", "text": "x", "numbers": [], "evidence_ids": []}],
        },
    )
    assert not envelope.ok
    assert envelope.error.code == ErrorCode.RUN_NOT_FOUND.value


async def test_budget_exceeded(ctx) -> None:
    for _ in range(6):
        envelope = await execute_tool(
            ctx, "query_data", {"dataset_id": ctx.dataset_id, "sql": "SELECT 1"}
        )
        assert envelope.ok
    blocked = await execute_tool(
        ctx, "query_data", {"dataset_id": ctx.dataset_id, "sql": "SELECT 1"}
    )
    assert not blocked.ok
    assert blocked.error.code == ErrorCode.BUDGET_EXCEEDED.value


async def test_unknown_tool(ctx) -> None:
    envelope = await execute_tool(ctx, "rm_rf", {})
    assert not envelope.ok
    assert envelope.error.code == ErrorCode.VALIDATION_ERROR.value
    assert "inspect_dataset" in envelope.error.message
