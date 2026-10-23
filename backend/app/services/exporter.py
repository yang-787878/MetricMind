"""报告导出（§5.2(7)）：HTML 完全自包含（内联 CSS + 内联 SVG，无外链无 JS），Markdown 用 GFM 表格。

为什么 SVG 在导出时现画：前端用 Recharts 渲染的是同一份 ChartSpec，
导出侧只需要"同一份数据"的另一种画法，避免把浏览器渲染结果当作图片依赖。
"""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from ..config import Settings
from ..errors import AppError, ErrorCode
from ..logging_conf import get_logger
from ..models.chart import ChartSpec
from ..models.report import ReportModel
from ..services.charts import render_svg
from .store import Store, utcnow_iso

logger = get_logger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

_html_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(default=True, default_for_string=True, enabled_extensions=("j2",)),
    trim_blocks=False,
    lstrip_blocks=False,
)
_md_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=False,
)


def _format_cell(value: Any) -> str:
    """Markdown 表格里的数值：整数原样，浮点保留两位，避免 14570.019999999999。"""
    if isinstance(value, bool) or value is None:
        return "—" if value is None else str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return f"{value:,.0f}"
        return f"{value:,.2f}"
    return str(value)


_md_env.filters["num"] = _format_cell

FORMATS: dict[str, tuple[str, str]] = {
    "html": ("html", "text/html; charset=utf-8"),
    "md": ("md", "text/markdown; charset=utf-8"),
}


def artifact_id_for(run_id: str, fmt: str) -> str:
    return f"art_{run_id[-10:]}_{fmt}"


def load_charts(store: Store, run_id: str, chart_ids: list[str]) -> list[ChartSpec]:
    """从证据池取回报告引用到的 ChartSpec；引用不到的直接报错（不允许导出假图）。"""
    wanted = set(chart_ids)
    found: dict[str, ChartSpec] = {}
    for payload in store.list_results(run_id):
        if payload["tool"] != "create_chart":
            continue
        data = payload["payload"].get("data") or {}
        chart_id = str(data.get("chart_id", ""))
        if chart_id in wanted and chart_id not in found:
            found[chart_id] = ChartSpec.model_validate(data)
    missing = wanted - set(found)
    if missing:
        raise AppError(
            ErrorCode.RESULT_NOT_FOUND,
            f"报告引用的图表 {sorted(missing)} 在证据池中不存在",
            details={"missing": sorted(missing), "run_id": run_id},
            hint="请重新运行分析以生成完整证据",
        )
    return [found[chart_id] for chart_id in chart_ids if chart_id in found]


def _generated_at_text(report: ReportModel) -> str:
    moment = report.generated_at
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _coverage_text(report: ReportModel) -> str | None:
    if report.verification is None:
        return None
    return f"{report.verification.coverage:.0%}"


def render_report(
    report: ReportModel,
    charts: list[ChartSpec],
    fmt: str,
    *,
    dataset_name: str | None = None,
) -> str:
    context: dict[str, Any] = {
        "report": report.model_dump(mode="json"),
        "generated_at": _generated_at_text(report),
        "coverage": _coverage_text(report),
        "dataset_name": dataset_name,
    }
    if fmt == "html":
        context["charts"] = [
            {"spec": chart.model_dump(mode="json"), "svg": Markup(render_svg(chart))}
            for chart in charts
        ]
        return _html_env.get_template("report.html.j2").render(**context)

    if fmt == "md":
        context["charts"] = [
            {"spec": chart.model_dump(mode="json")} for chart in charts
        ]
        return _md_env.get_template("report.md.j2").render(**context)

    raise AppError(
        ErrorCode.VALIDATION_ERROR,
        f"不支持的导出格式 {fmt}",
        details={"available": sorted(FORMATS)},
        hint="format 只支持 html 或 md",
    )


def export_run(
    *,
    store: Store,
    settings: Settings,
    run_id: str,
    report: ReportModel,
    fmt: str,
    dataset_name: str | None = None,
) -> dict[str, Any]:
    if fmt not in FORMATS:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"不支持的导出格式 {fmt}",
            details={"available": sorted(FORMATS)},
        )
    extension, _ = FORMATS[fmt]
    charts = load_charts(store, run_id, report.charts)
    content = render_report(report, charts, fmt, dataset_name=dataset_name)

    settings.ensure_dirs()
    path = settings.exports_dir / f"{run_id}.{extension}"
    path.write_text(content, encoding="utf-8")
    size_bytes = len(content.encode("utf-8"))

    artifact = {
        "artifact_id": artifact_id_for(run_id, fmt),
        "run_id": run_id,
        "kind": "report",
        "format": fmt,
        "path": str(path),
        "size_bytes": size_bytes,
        "created_at": utcnow_iso(),
    }
    store.save_artifact(artifact)
    logger.info(
        "report_exported",
        extra={"run_id": run_id, "format": fmt, "size_bytes": size_bytes, "charts": len(charts)},
    )
    return {
        "artifact_id": artifact["artifact_id"],
        "format": fmt,
        "size_bytes": size_bytes,
        "download_url": f"{settings.api_prefix}/runs/{run_id}/export?format={fmt}",
        "generated_at": artifact["created_at"],
        "path": str(path),
        "chart_count": len(charts),
    }


def existing_artifact(store: Store, run_id: str, fmt: str) -> dict[str, Any] | None:
    artifact = store.find_artifact(run_id, fmt)
    if artifact and Path(artifact["path"]).exists():
        return artifact
    return None


__all__ = [
    "FORMATS",
    "artifact_id_for",
    "load_charts",
    "render_report",
    "export_run",
    "existing_artifact",
]
