"""确定性指标计算（§5.2(4)）：所有算法写死在这里，模型只提供结构化参数。

支持 kind：sum / mean / median / count / count_distinct / min / max / ratio / share /
rate / growth_rate。除零、分母为空、列不存在都返回可解释的错误或 null + warning，
绝不让上层猜。
"""

from __future__ import annotations

import re
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..errors import AppError, ErrorCode
from ..logging_conf import get_logger
from .jsonable import to_jsonable

logger = get_logger(__name__)

MetricKind = Literal[
    "sum", "mean", "median", "count", "count_distinct", "min", "max",
    "ratio", "share", "rate", "growth_rate",
]
FilterOp = Literal[
    "=", "!=", ">", ">=", "<", "<=", "in", "not_in", "between", "is_null", "is_not_null"
]
Period = Literal["day", "week", "month"]
PERIODS: frozenset[str] = frozenset({"day", "week", "month"})
MONEY_HINTS = ("revenue", "cost", "profit", "price", "amount", "spend", "sales", "金额", "销售额")


class FilterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(min_length=1)
    op: FilterOp
    value: Any = None


class SortSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    by: str = "value"
    order: Literal["asc", "desc"] = "desc"


class MetricSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    kind: MetricKind
    column: str | None = None
    numerator: str | None = None
    denominator: str | None = None
    value_when: str | None = None
    group_by: list[str] = Field(
        default_factory=list,
        description="分组维度：真实列名，或 day/week/month（周期分组）。",
    )
    date_column: str | None = Field(
        default=None,
        description="时间列；按周期分组或计算 growth_rate 时使用，省略则自动推断。",
    )
    period: Period | None = Field(
        default=None,
        description="周期粒度；设置后等同于把 day/week/month 加进 group_by（与 group_by 叠加）。",
    )
    agg: Literal["sum", "mean", "count"] | None = None
    filters: list[FilterSpec] = Field(default_factory=list)
    sort: SortSpec | None = None
    limit: int | None = Field(default=None, ge=1, le=500)

    @model_validator(mode="after")
    def _check_requirements(self) -> "MetricSpec":
        if self.kind in {"ratio", "rate"}:
            if self.value_when:
                return self
            if not (self.numerator and self.denominator):
                raise ValueError(f"{self.kind} 需要 numerator + denominator，或 value_when")
        elif self.kind == "growth_rate":
            if not (self.column and self.date_column and self.period and self.agg):
                raise ValueError("growth_rate 需要 column + date_column + period + agg 齐备")
        elif self.kind == "share":
            if not self.column:
                raise ValueError("share 需要 column")
            if not self.group_by:
                raise ValueError("share 需要 group_by（占比必须相对于某个分组总数）")
        elif self.kind == "count":
            return self
        elif not self.column:
            raise ValueError(f"{self.kind} 需要 column")
        return self


# ---------------------------------------------------------------- 基础工具
def _available(df: pd.DataFrame) -> list[str]:
    return [str(c) for c in df.columns]


def _require(df: pd.DataFrame, column: str | None, field: str) -> str:
    if not column:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"{field} 不能为空",
            details={"field": field, "available": _available(df)},
        )
    if column not in df.columns:
        raise AppError(
            ErrorCode.INVALID_COLUMN,
            f"列 {column} 不存在",
            details={"column": column, "available": _available(df)},
            hint="请从 available 中选择真实存在的列名",
        )
    return column


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _apply_filters(df: pd.DataFrame, filters: list[FilterSpec]) -> tuple[pd.DataFrame, list[str]]:
    applied: list[str] = []
    frame = df
    for item in filters:
        column = _require(frame, item.column, "filters.column")
        series = frame[column]
        op = item.op
        if op == "is_null":
            frame = frame[series.isna()]
            applied.append(f"{column} IS NULL")
        elif op == "is_not_null":
            frame = frame[series.notna()]
            applied.append(f"{column} IS NOT NULL")
        elif op == "in":
            values = item.value if isinstance(item.value, list) else [item.value]
            frame = frame[series.isin(values)]
            applied.append(f"{column} IN {values}")
        elif op == "not_in":
            values = item.value if isinstance(item.value, list) else [item.value]
            frame = frame[~series.isin(values)]
            applied.append(f"{column} NOT IN {values}")
        elif op == "between":
            if not isinstance(item.value, list) or len(item.value) != 2:
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    "between 需要两个值的数组",
                    details={"field": "value"},
                )
            low, high = item.value
            if pd.api.types.is_datetime64_any_dtype(series):
                series = pd.to_datetime(series, errors="coerce")
                low = pd.to_datetime(low, errors="coerce")
                high = pd.to_datetime(high, errors="coerce")
            frame = frame[(series >= low) & (series <= high)]
            applied.append(f"{column} BETWEEN {low} AND {high}")
        else:
            target = item.value
            if op in {">", ">=", "<", "<="}:
                if pd.api.types.is_datetime64_any_dtype(series):
                    series = pd.to_datetime(series, errors="coerce")
                    target = pd.to_datetime(target, errors="coerce")
                    mask = {
                        ">": series > target,
                        ">=": series >= target,
                        "<": series < target,
                        "<=": series <= target,
                    }[op]
                    frame = frame[mask.fillna(False)]
                else:
                    numeric_series = _numeric(series)
                    numeric_target = float(target)
                    mask = {
                        ">": numeric_series > numeric_target,
                        ">=": numeric_series >= numeric_target,
                        "<": numeric_series < numeric_target,
                        "<=": numeric_series <= numeric_target,
                    }[op]
                    frame = frame[mask.fillna(False)]
            elif op == "!=":
                frame = frame[series != target]
            else:  # "="
                if pd.api.types.is_datetime64_any_dtype(series):
                    target = pd.to_datetime(target, errors="coerce")
                frame = frame[series == target]
            applied.append(f"{column} {op} {target}")
    return frame, applied


def _parse_condition(expression: str) -> tuple[str, str, Any]:
    match = re.match(
        r"^\s*(?P<col>[A-Za-z_][\w]*)\s*(?P<op>>=|<=|==|!=|=|>|<)\s*(?P<val>.+?)\s*$",
        expression,
    )
    if not match:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"value_when 无法解析：{expression}",
            details={"field": "value_when"},
            hint="支持形如 returns_flag = 1 或 revenue > 100 的条件",
        )
    raw = match.group("val").strip().strip("'\"")
    try:
        value: Any = float(raw) if re.fullmatch(r"-?\d+(\.\d+)?", raw) else raw
    except ValueError:
        value = raw
    return match.group("col"), match.group("op"), value


def _condition_mask(df: pd.DataFrame, expression: str) -> pd.Series:
    column, op, value = _parse_condition(expression)
    _require(df, column, "value_when")
    series = df[column]
    if op in {">", ">=", "<", "<="}:
        numeric = _numeric(series)
        mask = {
            ">": numeric > float(value),
            ">=": numeric >= float(value),
            "<": numeric < float(value),
            "<=": numeric <= float(value),
        }[op]
        return mask.fillna(False)
    if op == "!=":
        return series != value
    return series == value


def _period_series(series: pd.Series, period: str) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.isna().all():
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "时间列无法解析，无法按周期聚合",
            details={"period": period},
            hint="请先确认该列是可解析的日期（YYYY-MM-DD）",
        )
    if period == "month":
        return parsed.dt.strftime("%Y-%m")
    if period == "week":
        iso = parsed.dt.isocalendar()
        return (
            iso["year"].astype("Int64").astype(str)
            + "-W"
            + iso["week"].astype("Int64").astype(str).str.zfill(2)
        )
    return parsed.dt.strftime("%Y-%m-%d")


def _infer_date_column(df: pd.DataFrame) -> str | None:
    for column in df.columns:
        series = df[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            return str(column)
    for column in df.columns:
        if any(hint in str(column).lower() for hint in ("date", "time", "日期", "时间")):
            if pd.to_datetime(df[column], errors="coerce").notna().mean() >= 0.9:
                return str(column)
    return None


def _unit_for(kind: str, column: str | None) -> str | None:
    if kind in {"count", "count_distinct"}:
        return "count"
    if kind in {"ratio", "share", "rate", "growth_rate"}:
        return "ratio"
    if column and any(hint in column.lower() for hint in MONEY_HINTS):
        return "CNY"
    return None


def _aggregate(frame: pd.DataFrame, spec: MetricSpec, share_total: float | None = None) -> float | None:
    kind = spec.kind
    if kind == "count":
        return float(len(frame))
    column = _require(frame, spec.column, "column")
    series = _numeric(frame[column]) if kind != "count_distinct" else frame[column]
    if kind == "count_distinct":
        return float(series.nunique(dropna=True))
    non_null = series.dropna()
    if non_null.empty:
        return None
    if kind == "sum":
        return float(non_null.sum())
    if kind == "mean":
        return float(non_null.mean())
    if kind == "median":
        return float(non_null.median())
    if kind == "min":
        return float(non_null.min())
    if kind == "max":
        return float(non_null.max())
    if kind == "share":
        total = share_total if share_total is not None else float(non_null.sum())
        return None if total == 0 else float(non_null.sum()) / total
    raise AppError(ErrorCode.VALIDATION_ERROR, f"未实现的 kind: {kind}")


def _ratio_value(frame: pd.DataFrame, spec: MetricSpec) -> tuple[float | None, str]:
    if spec.value_when:
        mask = _condition_mask(frame, spec.value_when)
        numerator = float(mask.sum())
        denominator = float(len(frame))
        formula = f"COUNT({spec.value_when}) / COUNT(*)"
    else:
        num_col = _require(frame, spec.numerator, "numerator")
        den_col = _require(frame, spec.denominator, "denominator")
        numerator = float(_numeric(frame[num_col]).dropna().sum())
        denominator = float(_numeric(frame[den_col]).dropna().sum())
        formula = f"SUM({num_col}) / SUM({den_col})"
    if denominator == 0:
        return None, formula
    return numerator / denominator, formula


def _sort_groups(groups: list[dict[str, Any]], spec: MetricSpec) -> list[dict[str, Any]]:
    if not groups:
        return groups
    sort = spec.sort
    if sort is None:
        return groups
    if sort.by == "value":
        key = lambda item: (item["value"] is None, item["value"] or 0.0)  # noqa: E731
    elif sort.by == "key":
        first = next(iter(groups[0]["key"]), None)
        key = lambda item: str(item["key"].get(first, ""))  # noqa: E731
    else:
        key = lambda item: str(item["key"].get(sort.by, ""))  # noqa: E731
    return sorted(groups, key=key, reverse=sort.order == "desc")


def compute_metric(df: pd.DataFrame, spec: MetricSpec) -> dict[str, Any]:
    warnings: list[str] = []
    frame, applied = _apply_filters(df, spec.filters)
    if frame.empty:
        warnings.append("筛选后没有匹配的数据")
    rows_used = int(len(frame))

    # --- growth_rate 走独立路径：先按周期聚合，再取最后两期 ---
    if spec.kind == "growth_rate":
        period = spec.period or "month"
        date_column = _require(frame, spec.date_column or _infer_date_column(frame), "date_column")
        working = frame.copy()
        working["_period"] = _period_series(working[date_column], period)
        column = _require(working, spec.column, "column")
        numeric = _numeric(working[column])
        working = working.assign(_value=numeric)
        agg_fn = {"sum": "sum", "mean": "mean", "count": "count"}[spec.agg or "sum"]
        grouped = (
            working.dropna(subset=["_period"])
            .groupby("_period", dropna=False)["_value"]
            .agg(agg_fn)
            .sort_index()
        )
        groups = [
            {"key": {period: str(index)}, "value": to_jsonable(value)}
            for index, value in grouped.items()
        ]
        if len(grouped) < 2:
            warnings.append("周期数量不足 2，无法计算环比")
            return {
                "name": spec.name,
                "kind": spec.kind,
                "unit": "ratio",
                "value": None,
                "groups": groups,
                "formula": f"{agg_fn.upper()}({column}) 按 {period}({date_column})",
                "inputs": {"rows_used": rows_used, "filters_applied": applied},
                "warnings": warnings,
            }
        current_label, previous_label = str(grouped.index[-1]), str(grouped.index[-2])
        current, previous = float(grouped.iloc[-1]), float(grouped.iloc[-2])
        if previous == 0:
            value = None
            warnings.append("上一周期为 0，环比无法计算")
        else:
            value = (current - previous) / previous
        return {
            "name": spec.name,
            "kind": spec.kind,
            "unit": "ratio",
            "value": to_jsonable(value),
            "groups": groups,
            "formula": f"({current_label} - {previous_label}) / {previous_label}，"
            f"口径 {agg_fn.upper()}({column}) 按 {period}({date_column})",
            "inputs": {"rows_used": rows_used, "filters_applied": applied},
            "warnings": warnings,
        }

    # --- 分组维度（真实列名或 day/week/month 周期） ---
    # period 是 group_by 的语法糖：模型常写 period="month" 而不填 group_by，
    # 旧实现只在 group_by 里识别周期，导致这类请求静默退化成标量（图表随之失败）。
    group_by = list(spec.group_by)
    if spec.period and spec.period not in group_by:
        group_by.append(spec.period)

    group_columns: list[tuple[str, str]] = []
    period_dates: dict[str, str] = {}
    working = frame.copy()
    if group_by:
        for raw in group_by:
            if raw in PERIODS:
                date_column = spec.date_column or _infer_date_column(working)
                if not date_column:
                    raise AppError(
                        ErrorCode.VALIDATION_ERROR,
                        f"按周期 {raw} 分组，但数据集没有可解析的时间列",
                        details={"group_by": group_by, "available": _available(working)},
                        hint="请提供 date_column，或从 available 中选择一个日期列",
                    )
                _require(working, date_column, "date_column")
                working[raw] = _period_series(working[date_column], raw)
                group_columns.append((raw, raw))
                period_dates[raw] = date_column
            else:
                _require(working, raw, "group_by")
                group_columns.append((raw, raw))

    if group_columns:
        share_total: float | None = None
        if spec.kind == "share":
            column = _require(working, spec.column, "column")
            share_total = float(_numeric(working[column]).dropna().sum())
            if share_total == 0:
                warnings.append("总量为 0，占比无法计算")
        names = [name for name, _ in group_columns]
        groups: list[dict[str, Any]] = []
        ratio_formula = ""
        for keys, chunk in working.groupby(names, dropna=False):
            if not isinstance(keys, tuple):
                keys = (keys,)
            key_map = {name: to_jsonable(key) for name, key in zip(names, keys, strict=False)}
            if spec.kind in {"ratio", "rate"}:
                chunk_value, ratio_formula = _ratio_value(chunk, spec)
                if chunk_value is None:
                    warnings.append(f"分组 {key_map} 分母为 0，比率无法计算")
            else:
                chunk_value = _aggregate(chunk, spec, share_total)
            groups.append({"key": key_map, "value": to_jsonable(chunk_value)})
        groups = _sort_groups(groups, spec)
        if spec.limit:
            groups = groups[: spec.limit]
        group_clause = " GROUP BY " + ", ".join(
            f"{name}({period_dates.get(raw) or spec.date_column})" if raw in PERIODS else raw
            for (name, raw) in group_columns
        )
        if spec.kind in {"ratio", "rate"}:
            formula = f"{ratio_formula or spec.kind}{group_clause}"
        else:
            formula = f"{spec.kind.upper()}({spec.column or '*'}){group_clause}"
        return {
            "name": spec.name,
            "kind": spec.kind,
            "unit": _unit_for(spec.kind, spec.column),
            "value": None,
            "groups": groups,
            "formula": formula,
            "inputs": {"rows_used": rows_used, "filters_applied": applied},
            "warnings": warnings,
        }

    if spec.kind in {"ratio", "rate"}:
        value, formula = _ratio_value(working, spec)
        if value is None:
            warnings.append("分母为 0，比率无法计算")
        return {
            "name": spec.name,
            "kind": spec.kind,
            "unit": "ratio",
            "value": to_jsonable(value),
            "groups": [],
            "formula": formula,
            "inputs": {"rows_used": rows_used, "filters_applied": applied},
            "warnings": warnings,
        }

    value = _aggregate(working, spec)
    if value is None and spec.kind != "count":
        warnings.append("该列全部为空，无法计算")
    return {
        "name": spec.name,
        "kind": spec.kind,
        "unit": _unit_for(spec.kind, spec.column),
        "value": to_jsonable(value),
        "groups": [],
        "formula": f"{spec.kind.upper()}({spec.column or '*'})",
        "inputs": {"rows_used": rows_used, "filters_applied": applied},
        "warnings": warnings,
    }


def compute_metrics(df: pd.DataFrame, specs: list[MetricSpec]) -> dict[str, Any]:
    metrics = [compute_metric(df, spec) for spec in specs]
    return {"metrics": metrics}
