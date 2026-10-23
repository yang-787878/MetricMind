"""Demo 模式：无模型、纯模板的计划与叙述（§6.3 / §10.2）。

硬约束：
- 计划由字段语义确定性生成，不含随机；
- 叙述里的每个数字都从工具结果里读取，模板只负责排版，不做算术；
- 同一数据集同一问题运行两次，除时间戳外结果完全一致。
"""

from __future__ import annotations

import json
from typing import Any

from ..services.report_builder import format_value


def _column(columns: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((item for item in columns if item.get("name") == name), None)


def _metrics_step(step_id: str, title: str, intent: str, metrics: list[dict[str, Any]]) -> dict:
    return {
        "step_id": step_id,
        "title": title,
        "intent": intent,
        "tool": "calculate_metrics",
        "tool_args_hint": {"dataset_id": None, "metrics": metrics},
        "expected_output": "确定性指标结果（含分组值与口径公式）",
        "validation": "分组值之和与总量一致（误差 < 0.1%）",
    }


MONEY_HINTS = ("revenue", "sales", "amount", "gmv", "销售额", "收入", "profit", "cost", "price")


def _pick_metric(candidates: list[str]) -> str | None:
    """优先选"可求和"的金额类指标：revenue/sales 比 unit_price 更适合做总量。"""
    best: tuple[int, str] | None = None
    for name in candidates:
        lowered = name.lower()
        for rank, hint in enumerate(MONEY_HINTS):
            if hint in lowered and (best is None or rank < best[0]):
                best = (rank, name)
    if best is not None:
        return best[1]
    return candidates[0] if candidates else None


def build_plan(*, question: str, dataset_meta: dict[str, Any]) -> dict[str, Any]:
    dataset_id = dataset_meta.get("dataset_id")
    columns = dataset_meta.get("columns", [])
    metrics = list(dataset_meta.get("candidate_metrics") or [])
    dimensions = list(dataset_meta.get("candidate_dimensions") or [])
    date_column = dataset_meta.get("candidate_date_column")
    metric = _pick_metric(metrics)

    steps: list[dict[str, Any]] = []
    if metric:
        total_name = f"total_{metric}"
        steps.append(
            _metrics_step(
                "s1",
                f"计算 {metric} 总量",
                "先确认整体规模，作为后续拆解的分母与校验基准",
                [{"name": total_name, "kind": "sum", "column": metric}],
            )
        )
    else:
        steps.append(
            _metrics_step(
                "s1",
                "统计记录数",
                "数据中没有可求和的数值列，先确认记录规模",
                [{"name": "row_count_metric", "kind": "count"}],
            )
        )

    if metric and date_column:
        steps.append(
            _metrics_step(
                "s2",
                f"按 {date_column} 月度汇总 {metric}",
                "观察时间趋势，并为环比提供输入",
                [
                    {
                        "name": f"monthly_{metric}",
                        "kind": "sum",
                        "column": metric,
                        "group_by": ["month"],
                        "date_column": date_column,
                        "sort": {"by": "key", "order": "asc"},
                    }
                ],
            )
        )
        steps.append(
            _metrics_step(
                "s3",
                f"计算 {metric} 最近一期环比",
                "量化最近一个周期相对上一周期的变化幅度",
                [
                    {
                        "name": f"{metric}_growth",
                        "kind": "growth_rate",
                        "column": metric,
                        "date_column": date_column,
                        "period": "month",
                        "agg": "sum",
                    }
                ],
            )
        )

    if metric and dimensions:
        dimension = dimensions[0]
        steps.append(
            _metrics_step(
                "s4",
                f"计算 {dimension} 维度的 {metric} 占比",
                "定位结构性差异，找出主要贡献者",
                [
                    {
                        "name": f"{metric}_share_by_{dimension}",
                        "kind": "share",
                        "column": metric,
                        "group_by": [dimension],
                        "sort": {"by": "value", "order": "desc"},
                        "limit": 8,
                    }
                ],
            )
        )

    if metric and date_column:
        steps.append(
            {
                "step_id": f"s{len(steps) + 1}",
                "title": f"{metric} 月度趋势图",
                "intent": "把时间序列可视化，便于人工核对波动形态",
                "tool": "create_chart",
                "tool_args_hint": {
                    "from_result_id": "$step:s2",
                    "type": "line",
                    "x": "month",
                    "y": f"monthly_{metric}",
                    "title": f"{metric} 月度趋势",
                    "subtitle": f"口径：{metric} 求和，按 {date_column} 月粒度",
                    "sort_by": "x_asc",
                },
                "expected_output": "引用 s2 结果集的折线图规格",
                "validation": "图表数据与 s2 返回的行完全一致",
            }
        )
    elif metric and dimensions:
        dimension = dimensions[0]
        steps.append(
            {
                "step_id": f"s{len(steps) + 1}",
                "title": f"{metric} 按 {dimension} 分布图",
                "intent": "把结构占比可视化",
                "tool": "create_chart",
                "tool_args_hint": {
                    "from_result_id": "$step:s4",
                    "type": "bar",
                    "x": dimension,
                    "y": f"{metric}_share_by_{dimension}",
                    "title": f"{metric} 按 {dimension} 占比",
                    "sort_by": "y_desc",
                },
                "expected_output": "引用 s4 结果集的柱状图规格",
                "validation": "图表数据与 s4 返回的行完全一致",
            }
        )

    for step in steps:
        args = step["tool_args_hint"]
        if "dataset_id" in args:
            args["dataset_id"] = dataset_id

    out_of_scope: list[str] = []
    if not date_column:
        out_of_scope.append("数据中没有可解析的时间列，无法给出趋势或环比结论")
    if not dimensions:
        out_of_scope.append("数据中没有低基数的分类列，无法做结构拆解")
    if not metric:
        out_of_scope.append("数据中没有数值列，无法计算求和/均值类指标")

    return {
        "objective": f"围绕问题「{question}」给出可复现的量化结论",
        "required_fields": [
            name
            for name in (metric, date_column, dimensions[0] if dimensions else None)
            if name
        ],
        "assumptions": ["指标口径为列值求和/占比，未做通胀或汇率调整"],
        "steps": steps,
        "risks": ["数据质量问题会削弱结论强度，需在报告中声明"],
        "out_of_scope": out_of_scope,
        "narrative_source": "template",
    }


def repair_step(
    *, step: dict[str, Any], error: dict[str, Any], dataset_meta: dict[str, Any]
) -> dict[str, Any] | None:
    """Demo 修复：只在"列名写错 / 空结果"这类确定性问题上重写参数。"""
    code = str(error.get("code"))
    available = [column["name"] for column in dataset_meta.get("columns", [])]
    tool = str(step.get("tool"))
    args = dict(step.get("tool_args_hint") or {})

    if code == "INVALID_COLUMN":
        bad = str(error.get("column") or "")
        replacement = next((name for name in available if name != bad), None)
        if not replacement:
            return None
        text = json.dumps(args, ensure_ascii=False).replace(bad, replacement)
        rebuilt = json.loads(text)
        return {"tool": tool, "tool_args_hint": rebuilt, "reason": f"列 {bad} 改为 {replacement}"}

    if code == "EMPTY_RESULT":
        metrics = args.get("metrics")
        if metrics:
            for metric in metrics:
                metric.pop("filters", None)
            return {
                "tool": tool,
                "tool_args_hint": args,
                "reason": "移除筛选条件后重试",
            }
    return None


def _first_metric_payload(
    evidence: list[dict[str, Any]],
    tool: str,
    kind: str | None = None,
    *,
    require_value: bool = False,
    require_groups: bool = False,
) -> tuple[str, dict[str, Any]] | None:
    """挑第一个可用指标。

    `require_value` / `require_groups` 用来跳过"分组指标"：分组指标的
    `value` 恒为 None（数值在 `groups` 里），若被当成标量读取会 float(None) 崩溃。
    """
    for item in evidence:
        if item.get("tool") != tool:
            continue
        data = item.get("data") or {}
        for metric in data.get("metrics", []):
            if kind is not None and metric.get("kind") != kind:
                continue
            if require_value and metric.get("value") is None:
                continue
            if require_groups and not (metric.get("groups") or []):
                continue
            return str(item["result_id"]), metric
    return None


def _latest_group(metric: dict[str, Any]) -> tuple[str, float] | None:
    """分组指标取最后一组的值（只读取，不做算术）。"""
    groups = [group for group in metric.get("groups") or [] if group.get("value") is not None]
    if not groups:
        return None
    latest = groups[-1]
    label = " / ".join(str(value) for value in (latest.get("key") or {}).values())
    return label, float(latest["value"])


def build_draft(
    *,
    question: str,
    plan: dict[str, Any],
    evidence: list[dict[str, Any]],
    dataset_meta: dict[str, Any],
    feedback: list[str] | None = None,
) -> dict[str, Any]:
    """模板叙述：只读取工具结果里的数字，不做任何二次计算。"""
    total = _first_metric_payload(evidence, "calculate_metrics", "sum", require_value=True)
    count = _first_metric_payload(evidence, "calculate_metrics", "count", require_value=True)
    growth = _first_metric_payload(
        evidence, "calculate_metrics", "growth_rate", require_value=True
    )
    share = _first_metric_payload(evidence, "calculate_metrics", "share", require_groups=True)

    kpi_source = total or count
    sections: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    headline_parts: list[str] = []

    if kpi_source:
        result_id, metric = kpi_source
        unit = metric.get("unit")
        value = float(metric["value"]) if metric.get("value") is not None else None
        if value is not None:
            text = f"{metric['name']} 为 {format_value(value, unit)}"
            headline_parts.append(text)
            sections.append(
                {
                    "heading": "总体规模",
                    "body": (
                        f"{text}（口径：{metric.get('formula')}，"
                        f"使用 {metric.get('inputs', {}).get('rows_used', 0)} 行数据）。"
                    ),
                    "evidence_ids": [result_id],
                }
            )
            claims.append(
                {
                    "claim_id": "c1",
                    "text": text,
                    "numbers": [{"value": value, "unit": unit or ""}],
                    "evidence_ids": [result_id],
                }
            )

    if not kpi_source:
        # 全程按周期分组时没有标量指标，也要给出可核验的最新一期数值，
        # 否则报告会退化成"未产出结论"，而图上明明有数据。
        grouped = _first_metric_payload(
            evidence, "calculate_metrics", "sum", require_groups=True
        )
        latest = _latest_group(grouped[1]) if grouped else None
        if grouped and latest:
            result_id, metric = grouped
            label, value = latest
            text = f"{metric['name']} 在 {label} 为 {format_value(value, metric.get('unit'))}"
            headline_parts.append(text)
            sections.append(
                {
                    "heading": "最新一期规模",
                    "body": (
                        f"{text}（口径：{metric.get('formula')}，"
                        f"使用 {metric.get('inputs', {}).get('rows_used', 0)} 行数据）。"
                    ),
                    "evidence_ids": [result_id],
                }
            )
            claims.append(
                {
                    "claim_id": "c1",
                    "text": text,
                    "numbers": [{"value": value, "unit": metric.get("unit") or ""}],
                    "evidence_ids": [result_id],
                }
            )

    if growth:
        result_id, metric = growth
        value = float(metric["value"]) if metric.get("value") is not None else None
        if value is not None:
            text = f"最近一个周期环比 {format_value(value, 'ratio')}"
            headline_parts.append(text)
            sections.append(
                {
                    "heading": "变化趋势",
                    "body": (
                        f"{text}（计算式：{metric.get('formula')}，"
                        f"使用 {metric.get('inputs', {}).get('rows_used', 0)} 行数据）。"
                    ),
                    "evidence_ids": [result_id],
                }
            )
            claims.append(
                {
                    "claim_id": "c2",
                    "text": text,
                    "numbers": [{"value": value, "unit": "ratio"}],
                    "evidence_ids": [result_id],
                }
            )

    if share:
        result_id, metric = share
        groups = [group for group in (metric.get("groups") or []) if group.get("value") is not None]
        if groups:
            top = groups[0]
            key = " / ".join(str(value) for value in (top.get("key") or {}).values())
            value = float(top["value"])
            text = f"{key} 的占比最高，为 {format_value(value, 'ratio')}"
            headline_parts.append(text)
            sections.append(
                {
                    "heading": "结构分布",
                    "body": (
                        f"{text}（共 {len(groups)} 个分组，口径：{metric.get('formula')}）。"
                    ),
                    "evidence_ids": [result_id],
                }
            )
            claims.append(
                {
                    "claim_id": "c3",
                    "text": text,
                    "numbers": [{"value": value, "unit": "ratio"}],
                    "evidence_ids": [result_id],
                }
            )

    limitations: list[str] = []
    issues = dataset_meta.get("quality") or []
    if issues:
        limitations.append(
            f"数据存在 {len(issues)} 项质量问题（如 {issues[0].get('message', '')}），相关结论强度有限。"
        )
    if not dataset_meta.get("candidate_date_column"):
        limitations.append("数据缺少可解析的时间列，本报告不包含趋势或环比结论。")
    for item in plan.get("out_of_scope", []):
        limitations.append(f"超出数据能力范围：{item}")
    if feedback:
        limitations.extend(feedback)

    headline = "；".join(headline_parts) + "。" if headline_parts else "本次分析未产出可核验的量化结论。"

    return {
        "title": f"{question} 分析报告",
        "headline": headline,
        "sections": sections,
        "claims": claims,
        "limitations": limitations,
        "next_steps": [
            "补充更长的时间窗口，排除季节性影响",
            "按第二个维度做交叉拆解，验证主因是否稳健",
        ],
        "narrative_source": "template",
    }
