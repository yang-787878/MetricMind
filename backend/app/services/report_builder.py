"""报告装配（§4.2 / §6.4）：把证据、计划、草稿拼成可渲染的 ReportModel。

三条纪律：
1. 所有数字来自证据 payload，装配过程不做任何算术；
2. KPI 与 claim 的展示值用证据值重新格式化（§6.4 第 4 条），并保留 claimed 供审计；
3. 未通过审计的 claim 必须降级进 limitations，而不是从报告里悄悄删掉。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..models.enums import IssueSeverity, RunMode, RunStatus, VerificationStatus
from ..models.report import (
    Claim,
    ClaimNumber,
    DataQualityNote,
    Kpi,
    MethodologyItem,
    ReportModel,
    ReportSection,
    VerificationSummary,
)

MAX_KPIS = 4


def format_value(value: float | None, unit: str | None) -> str:
    """统一数字展示：金额用万/亿，比率用百分比，其余保留 1 位小数。"""
    if value is None:
        return "—"
    if unit == "CNY":
        amount = float(value)
        if abs(amount) >= 1e8:
            return f"¥{amount / 1e8:.2f} 亿"
        if abs(amount) >= 1e4:
            return f"¥{amount / 1e4:.1f} 万"
        return f"¥{amount:,.0f}"
    if unit in {"ratio", "%"}:
        return f"{float(value) * 100:.1f}%"
    if unit == "count":
        return f"{float(value):,.0f}"
    return f"{float(value):,.2f}"


def _human_metric(name: str) -> str:
    if name.endswith("_growth"):
        return f"{name[: -len('_growth')].replace('_', ' ')} 环比变化"
    if name.startswith("total_"):
        return f"{name[len('total_'):].replace('_', ' ')} 总量"
    if "_share_by_" in name:
        metric, dimension = name.split("_share_by_", 1)
        return f"{metric.replace('_', ' ')} 在 {dimension.replace('_', ' ')} 的占比"
    if name.startswith("monthly_"):
        return f"{name[len('monthly_'):].replace('_', ' ')} 月度值"
    return name.replace("_", " ")


def _collect_kpis(
    steps: list[dict[str, Any]], evidence: dict[str, dict[str, Any]]
) -> list[Kpi]:
    kpis: list[Kpi] = []
    for step in steps:
        if step.get("status") != "succeeded":
            continue
        for record in step.get("tool_calls", []):
            result_id = record.get("result_id")
            if not result_id or result_id not in evidence:
                continue
            payload = evidence[result_id]
            if payload.get("tool") != "calculate_metrics":
                continue
            for metric in (payload.get("data") or {}).get("metrics", []):
                value = metric.get("value")
                if value is None:
                    continue
                unit = metric.get("unit")
                kpis.append(
                    Kpi(
                        label=_human_metric(str(metric.get("name", "指标"))),
                        value=float(value),
                        unit=unit,
                        delta=None,
                        delta_label=None,
                        evidence_ids=[result_id],
                        display_value=format_value(float(value), unit),
                    )
                )
                if len(kpis) >= MAX_KPIS:
                    return kpis

    # 分组指标（如按月汇总）没有标量 value，只有 groups；取最新一期作为 KPI，
    # 只做取值不做算术，避免图表齐全但 KPI 区一片空白的报告。
    for step in steps:
        if step.get("status") != "succeeded":
            continue
        for record in step.get("tool_calls", []):
            result_id = record.get("result_id")
            if not result_id or result_id not in evidence:
                continue
            payload = evidence[result_id]
            if payload.get("tool") != "calculate_metrics":
                continue
            for metric in (payload.get("data") or {}).get("metrics", []):
                groups = [
                    group
                    for group in metric.get("groups") or []
                    if group.get("value") is not None
                ]
                if metric.get("value") is not None or not groups:
                    continue
                latest = groups[-1]
                key = " / ".join(str(part) for part in (latest.get("key") or {}).values())
                unit = metric.get("unit")
                value = float(latest["value"])
                kpis.append(
                    Kpi(
                        label=f"{_human_metric(str(metric.get('name', '指标')))}（{key}）"
                        if key
                        else _human_metric(str(metric.get("name", "指标"))),
                        value=value,
                        unit=unit,
                        delta=None,
                        delta_label=None,
                        evidence_ids=[result_id],
                        display_value=format_value(value, unit),
                    )
                )
                if len(kpis) >= MAX_KPIS:
                    return kpis
    return kpis


def _collect_charts(evidence: dict[str, dict[str, Any]]) -> list[str]:
    charts: list[str] = []
    for payload in evidence.values():
        if payload.get("tool") == "create_chart":
            chart_id = (payload.get("data") or {}).get("chart_id")
            if chart_id:
                charts.append(str(chart_id))
    return charts


def _methodology(
    steps: list[dict[str, Any]], evidence: dict[str, dict[str, Any]]
) -> list[MethodologyItem]:
    items: list[MethodologyItem] = []
    for step in steps:
        result_id = None
        formula = None
        sql = None
        for record in step.get("tool_calls", []):
            if record.get("result_id"):
                result_id = record["result_id"]
            payload = evidence.get(record.get("result_id") or "")
            if payload:
                if payload.get("tool") == "calculate_metrics":
                    metrics = (payload.get("data") or {}).get("metrics") or []
                    if metrics:
                        formula = metrics[0].get("formula")
                elif payload.get("tool") == "query_data":
                    sql = ((payload.get("data") or {}).get("sql_executed")) or None
        items.append(
            MethodologyItem(
                step_id=str(step.get("step_id")),
                description=str(step.get("title") or step.get("intent") or ""),
                tool=str(step.get("tool") or ""),
                result_id=result_id,
                sql=sql,
                formula=formula,
            )
        )
    return items


def _data_quality(quality: list[dict[str, Any]]) -> list[DataQualityNote]:
    notes: list[DataQualityNote] = []
    for issue in quality:
        severity = str(issue.get("severity", "warning"))
        try:
            parsed = IssueSeverity(severity)
        except ValueError:
            parsed = IssueSeverity.WARNING
        notes.append(
            DataQualityNote(
                code=str(issue.get("code", "UNKNOWN")),
                severity=parsed,
                message=str(issue.get("message", "")),
                column=issue.get("column"),
            )
        )
    return notes


def _claims_from_draft(
    draft: dict[str, Any], verification: dict[str, Any] | None
) -> list[Claim]:
    statuses = {
        item.get("claim_id"): item for item in (verification or {}).get("items", [])
    }
    claims: list[Claim] = []
    for raw in draft.get("claims", []):
        claim_id = str(raw.get("claim_id"))
        item = statuses.get(claim_id, {})
        numbers = [
            ClaimNumber(value=float(number.get("value", 0.0)), unit=str(number.get("unit", "")))
            for number in raw.get("numbers", [])
        ]
        claims.append(
            Claim(
                claim_id=claim_id,
                text=str(raw.get("text", "")),
                numbers=numbers,
                display_numbers=[format_value(number.value, number.unit) for number in numbers],
                evidence_ids=[str(value) for value in raw.get("evidence_ids", [])],
                status=VerificationStatus(item.get("status", "unverifiable")),
                reason=item.get("reason") or None,
                matched_value=item.get("matched_value"),
            )
        )
    return claims


def build_report(
    *,
    run_id: str,
    question: str,
    mode: RunMode,
    status: RunStatus,
    plan: dict[str, Any] | None,
    steps: list[dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
    dataset_meta: dict[str, Any],
    draft: dict[str, Any],
    verification: dict[str, Any] | None,
    warnings: list[str],
    narrative_source: str = "llm",
) -> ReportModel:
    claims = _claims_from_draft(draft, verification)
    limitations = [str(item) for item in draft.get("limitations", [])]
    degraded_sections: set[str] = set()
    unsupported = [
        claim for claim in claims if claim.status == VerificationStatus.UNSUPPORTED
    ]
    for claim in unsupported:
        limitations.append(
            f"未经证实的推断：{claim.text}（{claim.reason or '数字未能在证据中找到'}）"
        )
        for section in draft.get("sections", []):
            if claim.claim_id in section.get("claim_ids", []) or any(
                evidence_id in section.get("evidence_ids", []) for evidence_id in claim.evidence_ids
            ):
                degraded_sections.add(str(section.get("heading")))

    sections = [
        ReportSection(
            id=f"finding_{index + 1}",
            heading=str(section.get("heading", "")),
            body=str(section.get("body", "")),
            evidence_ids=[str(value) for value in section.get("evidence_ids", [])],
            degraded=str(section.get("heading")) in degraded_sections,
        )
        for index, section in enumerate(draft.get("sections", []))
    ]

    if warnings:
        limitations.extend(warnings)

    summary = None
    if verification:
        summary = VerificationSummary(
            coverage=float(verification.get("coverage", 0.0)),
            supported=int(verification.get("supported", 0)),
            unsupported=int(verification.get("unsupported", 0)),
            unverifiable=int(verification.get("unverifiable", 0)),
        )

    title = str(draft.get("title") or f"{question} 分析报告")
    headline = str(draft.get("headline") or "本次分析仅包含工具执行结果。")

    return ReportModel(
        run_id=run_id,
        title=title,
        generated_at=datetime.now(UTC),
        mode=mode,
        status=status,
        headline=headline,
        kpis=_collect_kpis(steps, evidence),
        sections=sections,
        charts=_collect_charts(evidence),
        claims=claims,
        methodology=_methodology(steps, evidence),
        data_quality=_data_quality(dataset_meta.get("quality", [])),
        limitations=limitations,
        next_steps=[str(item) for item in draft.get("next_steps", [])],
        verification=summary,
        narrative_source=narrative_source,
    )
