"""报告导出单测（§11 阶段 4 出口标准）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.registry import execute_tool
from app.models.report import ReportModel
from app.services.exporter import export_run, load_charts, render_report


async def _report_and_charts(harness):
    await harness.run(mode="demo")
    stored = harness.report()
    assert stored is not None
    report = ReportModel.model_validate(stored)
    charts = load_charts(harness.store, harness.run_id, report.charts)
    return report, charts


async def test_html_is_self_contained(harness) -> None:
    report, charts = await _report_and_charts(harness)
    html = render_report(report, charts, "html")

    assert len(charts) >= 1
    assert html.count("<svg") == len(charts), "每个图表必须内联一张 SVG"
    assert "Demo mode" in html
    assert report.kpis[0].display_value in html

    # 自包含：除 SVG 命名空间外，不允许任何外链、脚本
    stripped = html.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "http://" not in stripped
    assert "https://" not in stripped
    assert "<script" not in html.lower()
    assert "@import" not in html
    assert "src=" not in stripped
    assert "href=" not in stripped

    # 证据链与口径必须出现在正文里
    assert "result_id" in html
    assert "方法论与口径" in html
    assert "局限性" in html


async def test_markdown_uses_gfm_tables(harness) -> None:
    report, charts = await _report_and_charts(harness)
    markdown = render_report(report, charts, "md")

    assert markdown.startswith("# ")
    assert "| --- |" in markdown or "|---|" in markdown
    assert "## KPI" in markdown
    assert "## 数字核验" in markdown
    assert "## 方法论与口径" in markdown
    assert charts[0].chart_id not in markdown  # 图表以数据表替代，不引用 chart_id
    assert charts[0].source.result_id in markdown
    assert charts[0].title in markdown


async def test_export_writes_artifact_and_reuses(harness, settings) -> None:
    report, _ = await _report_and_charts(harness)
    first = export_run(
        store=harness.store, settings=settings, run_id=harness.run_id, report=report, fmt="html"
    )
    path = Path(first["path"])
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert content.startswith("<!doctype html>")
    assert first["size_bytes"] == len(content.encode("utf-8"))

    second = export_run(
        store=harness.store, settings=settings, run_id=harness.run_id, report=report, fmt="html"
    )
    assert second["artifact_id"] == first["artifact_id"]
    artifacts = harness.store.list_artifacts(harness.run_id)
    assert len(artifacts) == 1
    assert artifacts[0]["format"] == "html"


async def test_export_rejects_unknown_format(harness, settings) -> None:
    report, _ = await _report_and_charts(harness)
    from app.errors import AppError

    with pytest.raises(AppError) as info:
        export_run(store=harness.store, settings=settings, run_id=harness.run_id, report=report, fmt="pdf")
    assert info.value.code == "VALIDATION_ERROR"


async def test_export_report_tool(harness) -> None:
    await harness.run(mode="demo")
    envelope = await execute_tool(
        harness.context.tool_ctx,
        "export_report",
        {"run_id": harness.run_id, "format": "md"},
    )
    assert envelope.ok, envelope.error
    data = envelope.data
    assert data["format"] == "md"
    assert data["size_bytes"] > 0
    assert data["download_url"].endswith(f"/runs/{harness.run_id}/export?format=md")
    assert envelope.result_id is None, "导出工具不产生新的证据"


async def test_export_before_report_is_rejected(harness) -> None:
    envelope = await execute_tool(
        harness.context.tool_ctx if harness.context else _make_ctx(harness),
        "export_report",
        {"run_id": harness.run_id, "format": "html"},
    )
    assert not envelope.ok
    assert envelope.error.code in {"REPORT_NOT_READY", "RUN_NOT_FOUND"}


def _make_ctx(harness):
    from app.agent.run_context import RunContext
    from app.llm.fake_client import FakeLLM
    from app.models.run import Budget
    from app.services.evidence import EvidencePool

    return RunContext(
        run_id=harness.run_id,
        dataset_id=harness.dataset_id,
        question="导出测试",
        mode="demo",
        store=harness.store,
        loader=harness.loader,
        engine=harness.engine,
        evidence=EvidencePool(harness.store, harness.run_id),
        settings=harness.settings,
        llm=FakeLLM(),
        budget=Budget(max_steps=5, max_tool_calls=5, max_replans=1, timeout_seconds=60),
    ).tool_ctx


async def test_api_export_download_and_artifacts(api_client) -> None:
    import time

    csv = "channel,revenue,order_date\nDTC,100,2025-01-01\nOutlet,80,2025-02-01\n"
    dataset = api_client.post(
        "/api/datasets", files={"file": ("export.csv", csv.encode(), "text/csv")}
    ).json()
    run_id = api_client.post(
        "/api/runs",
        json={"dataset_id": dataset["dataset_id"], "question": "各渠道收入差异？", "mode": "demo"},
    ).json()["run_id"]

    deadline = time.time() + 60
    while time.time() < deadline:
        detail = api_client.get(f"/api/runs/{run_id}").json()
        if detail["status"] in {"succeeded", "partial", "failed"}:
            break
        time.sleep(0.15)
    assert detail["status"] in {"succeeded", "partial"}

    export = api_client.get(f"/api/runs/{run_id}/export?format=html")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/html")
    assert "attachment" in export.headers["content-disposition"]
    assert "<svg" in export.text

    artifacts = api_client.get(f"/api/runs/{run_id}/artifacts").json()
    assert artifacts["total"] == 1
    assert artifacts["items"][0]["format"] == "html"
    assert artifacts["items"][0]["download_url"].endswith("format=html")

    bad = api_client.get(f"/api/runs/{run_id}/export?format=pdf")
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"

    missing = api_client.get("/api/runs/run_missing/export?format=html")
    assert missing.status_code == 404
