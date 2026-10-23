"""ChartSpec 构造 + SVG 渲染（§4.2 / §5.2(7)）。

两类用途：
1. create_chart 工具用 `build_chart_spec` 生成规范，前端用 Recharts 渲染；
2. 导出 HTML 时用 `render_svg` 把同一份 ChartSpec 画成内联 SVG（无 JS、无外链）。

SVG 的颜色写 `var(--chart-N, #hex)`：内联进导出 HTML 时继承文档里的 token，
单独打开时回退到同一色值——既不重复维护色板，也保证自包含。
"""

from __future__ import annotations

import uuid
from typing import Any
from xml.sax.saxutils import escape

from ..errors import AppError, ErrorCode
from ..models.chart import ChartAxis, ChartSeriesRef, ChartSource, ChartSpec
from ..models.enums import ChartType, SemanticType
from ..services.jsonable import to_jsonable

MAX_POINTS = 500
DEFAULT_POINTS = 200

# 与 src/styles/tokens.css 的 --chart-1..6 一致（fallback 值，便于单独打开 SVG）
PALETTE = (
    ("var(--chart-1, #3452c4)", "#3452c4"),
    ("var(--chart-2, #0e9384)", "#0e9384"),
    ("var(--chart-3, #b54708)", "#b54708"),
    ("var(--chart-4, #6941c6)", "#6941c6"),
    ("var(--chart-5, #175cd3)", "#175cd3"),
    ("var(--chart-6, #667085)", "#667085"),
)

SVG_WIDTH = 720
SVG_HEIGHT = 360
PAD_LEFT = 64
PAD_RIGHT = 16
PAD_TOP = 28
PAD_BOTTOM = 44


def new_chart_id() -> str:
    return f"ch_{uuid.uuid4().hex[:8]}"


def table_from_result(result_id: str, payload: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    """把任意结果集归一化成 (列名, 行字典)，供 create_chart 校验与绘图。"""
    data = payload.get("data")
    tool = payload.get("tool", "unknown")
    if not isinstance(data, dict):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"结果集 {result_id} 不含结构化数据",
            details={"result_id": result_id, "tool": tool},
            hint="请引用 query_data 或 calculate_metrics 的结果",
        )

    if isinstance(data.get("columns"), list) and isinstance(data.get("rows"), list):
        names = [
            item.get("name") if isinstance(item, dict) else str(item)
            for item in data["columns"]
        ]
        rows = [
            {str(name): to_jsonable(value) for name, value in zip(names, record, strict=False)}
            for record in data["rows"]
        ]
        return [str(name) for name in names], rows

    metrics = data.get("metrics")
    if isinstance(metrics, list) and metrics:
        rows_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
        keys: list[str] = []
        for metric in metrics:
            # growth_rate 的 groups 是"被聚合的周期值"，不是增长率本身，
            # 混进表格会让列名与含义不符，因此不参与绘图列。
            if str(metric.get("kind")) == "growth_rate":
                continue
            name = str(metric.get("name", "value"))
            for group in metric.get("groups") or []:
                key_map = group.get("key") or {}
                for key_name in key_map:
                    if key_name not in keys:
                        keys.append(str(key_name))
                signature = tuple(key_map.get(item) for item in keys)
                row = rows_by_key.setdefault(signature, {})
                row.update({str(k): to_jsonable(v) for k, v in key_map.items()})
                row[name] = to_jsonable(group.get("value"))
        if not rows_by_key:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"结果集 {result_id} 的指标没有分组数据，无法绘图",
                details={"result_id": result_id},
                hint="请先用 group_by 计算分组指标",
            )
        metric_names = [
            str(metric.get("name", "value"))
            for metric in metrics
            if str(metric.get("kind")) != "growth_rate"
        ]
        return keys + metric_names, list(rows_by_key.values())

    raise AppError(
        ErrorCode.VALIDATION_ERROR,
        f"结果集 {result_id}（{tool}）不含可绘制的表格数据",
        details={"result_id": result_id, "tool": tool, "available": sorted(data.keys())},
        hint="请引用 query_data 或 calculate_metrics 产出的分组结果",
    )


def _sort_rows(rows: list[dict[str, Any]], sort_by: str | None, x_key: str, y_key: str) -> list[dict[str, Any]]:
    if not sort_by:
        return rows
    field = x_key if sort_by.startswith("x") else y_key
    reverse = sort_by.endswith("_desc")
    numeric = sort_by.startswith("y")

    def key(row: dict[str, Any]) -> tuple[bool, Any]:
        value = row.get(field)
        if numeric:
            try:
                return (value is None, float(value))
            except (TypeError, ValueError):
                return (True, 0.0)
        return (value is None, str(value))

    return sorted(rows, key=key, reverse=reverse)


def build_chart_spec(
    *,
    result_id: str,
    payload: dict[str, Any],
    chart_type: ChartType,
    x: str,
    y: str,
    series: str | None,
    title: str,
    subtitle: str | None,
    unit: str | None,
    sort_by: str | None,
    limit_points: int,
) -> ChartSpec:
    columns, rows = table_from_result(result_id, payload)
    for name in (x, y, series):
        if name and name not in columns:
            raise AppError(
                ErrorCode.INVALID_COLUMN,
                f"列 {name} 不在结果集 {result_id} 中",
                details={"column": name, "available": columns},
                hint="请从 available 中选择真实存在的列名",
            )
    if series and chart_type not in {ChartType.BAR, ChartType.STACKED_BAR, ChartType.LINE, ChartType.AREA}:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"{chart_type.value} 不支持 series 分组",
            details={"chart_type": chart_type.value},
        )

    notes: list[str] = []
    limit = min(limit_points or DEFAULT_POINTS, MAX_POINTS)
    sorted_rows = _sort_rows(rows, sort_by, x, y)
    if len(sorted_rows) > limit:
        notes.append(f"结果共 {len(sorted_rows)} 行，图表只展示前 {limit} 行")
        sorted_rows = sorted_rows[:limit]

    x_type = SemanticType.TEMPORAL if x.lower() in {"month", "week", "day"} else SemanticType.CATEGORICAL
    meta = payload.get("meta") or {}
    source = ChartSource(
        result_id=result_id,
        tool=str(payload.get("tool", "unknown")),
        step_id=payload.get("step_id"),
        row_count=len(rows),
        truncated=bool(meta.get("truncated", False)),
    )
    if source.truncated:
        notes.append("来源结果集已截断，图表可能不完整")

    return ChartSpec(
        chart_id=new_chart_id(),
        type=chart_type,
        title=title,
        subtitle=subtitle,
        unit=unit,
        x=ChartAxis(key=x, label=x, type=x_type),
        y=ChartAxis(key=y, label=y, type=SemanticType.NUMERIC),
        series=ChartSeriesRef(key=series, label=series) if series else None,
        data=sorted_rows,
        source=source,
        notes=notes,
    )


# ---------------------------------------------------------------- SVG 渲染
def _as_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _axis_text(value: float, unit: str | None) -> str:
    if unit in {"ratio", "%"}:
        return f"{value * 100:.0f}%"
    if abs(value) >= 1e8:
        return f"{value / 1e8:.1f}亿"
    if abs(value) >= 1e4:
        return f"{value / 1e4:.1f}万"
    if abs(value) >= 1000:
        return f"{value / 1000:.1f}k"
    if abs(value) < 1 and value != 0:
        return f"{value:.2f}"
    return f"{value:.0f}"


def _ordered_categories(spec: ChartSpec) -> list[str]:
    seen: list[str] = []
    for row in spec.data:
        value = row.get(spec.x.key)
        if value is None:
            continue
        text = str(value)
        if text not in seen:
            seen.append(text)
    return seen


def _series_keys(spec: ChartSpec) -> list[str]:
    if spec.series is None:
        return [""]
    keys: list[str] = []
    for row in spec.data:
        value = row.get(spec.series.key)
        text = "" if value is None else str(value)
        if text not in keys:
            keys.append(text)
    return keys or [""]


def _value_matrix(spec: ChartSpec, categories: list[str], series: list[str]) -> dict[tuple[str, str], float | None]:
    matrix: dict[tuple[str, str], float | None] = {}
    for row in spec.data:
        category = row.get(spec.x.key)
        if category is None:
            continue
        series_value = "" if spec.series is None else str(row.get(spec.series.key) or "")
        matrix[(series_value, str(category))] = _as_number(row.get(spec.y.key))
    return matrix


def _empty_svg(spec: ChartSpec, message: str) -> str:
    return (
        f'<svg viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" role="img" '
        f'aria-label="{escape(spec.title)}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{SVG_WIDTH}" height="{SVG_HEIGHT}" fill="var(--surface, #ffffff)"/>'
        f'<text x="{SVG_WIDTH / 2}" y="{SVG_HEIGHT / 2}" text-anchor="middle" '
        f'font-family="var(--font-sans, sans-serif)" font-size="13" '
        f'fill="var(--text-muted, #667085)">{escape(message)}</text></svg>'
    )


def render_svg(spec: ChartSpec, width: int = SVG_WIDTH, height: int = SVG_HEIGHT) -> str:
    """把 ChartSpec 画成内联 SVG；只依赖标准库字符串拼接，不引入绘图库。"""
    categories = _ordered_categories(spec)
    if not categories:
        return _empty_svg(spec, "暂无数据")

    series = _series_keys(spec)
    matrix = _value_matrix(spec, categories, series)

    stacked = spec.type is ChartType.STACKED_BAR
    values = [value for value in matrix.values() if value is not None]
    if not values:
        return _empty_svg(spec, "暂无数据")

    if stacked:
        totals = [
            sum(matrix.get((key, category)) or 0.0 for key in series) for category in categories
        ]
        y_high = max(max(totals), 0.0)
        y_low = min(min(totals), 0.0)
    elif spec.type in {ChartType.LINE, ChartType.AREA, ChartType.SCATTER}:
        # 折线/散点不强制从 0 起：否则一条 200万~180万的趋势会被压成一条直线
        y_high = max(values)
        y_low = min(values)
        padding = (y_high - y_low) * 0.08 or abs(y_high) * 0.05 or 1.0
        y_high += padding
        y_low -= padding
        if min(values) >= 0:
            # 全为非负数据时不要出现负数刻度（金额出现 -16.6万 会让人以为有退款）
            y_low = max(y_low, 0.0)
    else:
        y_high = max(max(values), 0.0)
        y_low = min(min(values), 0.0)
    if y_high == y_low:
        y_high = y_low + 1.0

    plot_w = width - PAD_LEFT - PAD_RIGHT
    plot_h = height - PAD_TOP - PAD_BOTTOM

    def x_at(index: int) -> float:
        if len(categories) == 1:
            return PAD_LEFT + plot_w / 2
        return PAD_LEFT + plot_w * index / (len(categories) - 1)

    def slot_center(index: int) -> float:
        return PAD_LEFT + plot_w * (index + 0.5) / len(categories)

    def y_at(value: float) -> float:
        span = y_high - y_low
        return PAD_TOP + plot_h * (1 - (value - y_low) / span)

    parts: list[str] = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(spec.title)}" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="var(--font-sans, sans-serif)">',
        f'<rect width="{width}" height="{height}" fill="var(--surface, #ffffff)"/>',
    ]

    # 网格与 Y 轴刻度
    ticks = 4
    for step in range(ticks + 1):
        value = y_low + (y_high - y_low) * step / ticks
        y = y_at(value)
        parts.append(
            f'<line x1="{PAD_LEFT}" y1="{y:.1f}" x2="{width - PAD_RIGHT}" y2="{y:.1f}" '
            f'stroke="var(--grid, #eaecf0)" stroke-width="1" stroke-dasharray="3 3"/>'
        )
        parts.append(
            f'<text x="{PAD_LEFT - 8}" y="{y + 3:.1f}" text-anchor="end" font-size="11" '
            f'fill="var(--text-muted, #667085)">{escape(_axis_text(value, spec.unit))}</text>'
        )

    # X 轴标签（最多 8 个，避免重叠）
    stride = max(1, (len(categories) + 7) // 8)
    for index, category in enumerate(categories):
        if index % stride and index != len(categories) - 1:
            continue
        x = slot_center(index) if spec.type in {ChartType.BAR, ChartType.STACKED_BAR} else x_at(index)
        label = category if len(category) <= 12 else category[:11] + "…"
        anchor = "end" if index == len(categories) - 1 else "middle"
        parts.append(
            f'<text x="{x:.1f}" y="{height - PAD_BOTTOM + 18}" text-anchor="{anchor}" '
            f'font-size="11" fill="var(--text-muted, #667085)">{escape(label)}</text>'
        )

    # 数据系列
    if spec.type in {ChartType.BAR, ChartType.STACKED_BAR}:
        slot = plot_w / len(categories)
        bar_width = max(slot * (0.62 if stacked else 0.62 / len(series)), 2.0)
        for index, category in enumerate(categories):
            if stacked:
                cursor = 0.0
                base_y = y_at(0.0)
                for series_index, key in enumerate(series):
                    value = matrix.get((key, category)) or 0.0
                    if value == 0:
                        continue
                    top_y = y_at(cursor + value)
                    color, _ = PALETTE[series_index % len(PALETTE)]
                    x = slot_center(index) - bar_width / 2
                    parts.append(
                        f'<rect x="{x:.1f}" y="{min(top_y, base_y):.1f}" width="{bar_width:.1f}" '
                        f'height="{abs(base_y - top_y):.1f}" fill="{color}"/>'
                    )
                    cursor += value
            else:
                for series_index, key in enumerate(series):
                    value = matrix.get((key, category))
                    if value is None:
                        continue
                    color, _ = PALETTE[series_index % len(PALETTE)]
                    offset = (series_index - (len(series) - 1) / 2) * bar_width
                    x = slot_center(index) + offset - bar_width / 2
                    top_y = y_at(value)
                    base_y = y_at(0.0)
                    parts.append(
                        f'<rect x="{x:.1f}" y="{min(top_y, base_y):.1f}" width="{bar_width:.1f}" '
                        f'height="{abs(base_y - top_y):.1f}" fill="{color}" rx="2"/>'
                    )
    elif spec.type is ChartType.SCATTER:
        for series_index, key in enumerate(series):
            color, _ = PALETTE[series_index % len(PALETTE)]
            for index, category in enumerate(categories):
                value = matrix.get((key, category))
                if value is None:
                    continue
                parts.append(
                    f'<circle cx="{x_at(index):.1f}" cy="{y_at(value):.1f}" r="3.5" '
                    f'fill="{color}"/>'
                )
    else:
        for series_index, key in enumerate(series):
            color, _ = PALETTE[series_index % len(PALETTE)]
            points: list[tuple[float, float]] = []
            for index, category in enumerate(categories):
                value = matrix.get((key, category))
                if value is None:
                    continue
                points.append((x_at(index), y_at(value)))
            if not points:
                continue
            if spec.type is ChartType.AREA and len(points) > 1:
                baseline = y_at(max(y_low, 0.0))
                path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
                parts.append(
                    f'<polygon points="{PAD_LEFT},{baseline:.1f} {path} '
                    f'{points[-1][0]:.1f},{baseline:.1f}" fill="{color}" opacity="0.14"/>'
                )
            coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
            parts.append(
                f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2" '
                f'stroke-linejoin="round" stroke-linecap="round"/>'
            )
            if len(points) <= 60:
                for x, y in points:
                    parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{color}"/>')

    # 图例
    if spec.series is not None and len(series) > 1:
        legend_x = PAD_LEFT
        for series_index, key in enumerate(series):
            color, _ = PALETTE[series_index % len(PALETTE)]
            parts.append(
                f'<rect x="{legend_x}" y="{PAD_TOP - 16}" width="8" height="8" rx="2" fill="{color}"/>'
            )
            parts.append(
                f'<text x="{legend_x + 12}" y="{PAD_TOP - 9}" font-size="11" '
                f'fill="var(--text-secondary, #475467)">{escape(key)}</text>'
            )
            legend_x += 16 + 8 * len(key) + 16

    parts.append(
        f'<text x="{width - PAD_RIGHT}" y="{PAD_TOP - 9}" text-anchor="end" font-size="11" '
        f'fill="var(--text-muted, #667085)">{escape(spec.y.key)}'
        f'{"（" + escape(spec.unit) + "）" if spec.unit else ""}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)
