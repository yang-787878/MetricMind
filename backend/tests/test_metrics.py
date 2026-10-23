"""指标计算单测（§10.1）：每种 kind 用手算 fixture 校验，误差 1e-6。"""

from __future__ import annotations

import pandas as pd
import pytest

from app.errors import AppError, ErrorCode
from app.services.metrics import FilterSpec, MetricSpec, compute_metric, compute_metrics


@pytest.fixture
def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "channel": ["DTC", "DTC", "Outlet", "Outlet"],
            "region": ["North", "South", "North", "South"],
            "revenue": [100.0, 200.0, 50.0, 50.0],
            "cost": [60.0, 120.0, 40.0, 40.0],
            "returns_flag": [0, 1, 0, 1],
            "zeros": [0.0, 0.0, 0.0, 0.0],
            "order_date": pd.to_datetime(
                ["2025-01-05", "2025-01-20", "2025-02-10", "2025-02-11"]
            ),
        }
    )


def value_of(frame: pd.DataFrame, **kwargs) -> float | None:
    return compute_metric(frame, MetricSpec(**kwargs))["value"]


def test_sum_mean_median_min_max(frame: pd.DataFrame) -> None:
    assert value_of(frame, name="s", kind="sum", column="revenue") == pytest.approx(400.0)
    assert value_of(frame, name="m", kind="mean", column="revenue") == pytest.approx(100.0)
    assert value_of(frame, name="md", kind="median", column="revenue") == pytest.approx(75.0)
    assert value_of(frame, name="mn", kind="min", column="revenue") == pytest.approx(50.0)
    assert value_of(frame, name="mx", kind="max", column="revenue") == pytest.approx(200.0)


def test_count_and_count_distinct(frame: pd.DataFrame) -> None:
    assert value_of(frame, name="c", kind="count") == pytest.approx(4.0)
    assert value_of(frame, name="cd", kind="count_distinct", column="channel") == pytest.approx(2.0)


def test_sum_with_group_by(frame: pd.DataFrame) -> None:
    result = compute_metric(
        frame,
        MetricSpec(name="rev_by_channel", kind="sum", column="revenue", group_by=["channel"]),
    )
    groups = {item["key"]["channel"]: item["value"] for item in result["groups"]}
    assert groups == {"DTC": pytest.approx(300.0), "Outlet": pytest.approx(100.0)}
    assert result["unit"] == "CNY"
    assert "GROUP BY channel" in result["formula"]


def test_share_is_relative_to_total(frame: pd.DataFrame) -> None:
    result = compute_metric(
        frame,
        MetricSpec(
            name="share", kind="share", column="revenue", group_by=["channel"], sort=None
        ),
    )
    shares = {item["key"]["channel"]: item["value"] for item in result["groups"]}
    assert shares["DTC"] == pytest.approx(0.75, abs=1e-6)
    assert shares["Outlet"] == pytest.approx(0.25, abs=1e-6)


def test_ratio_uses_numerator_and_denominator(frame: pd.DataFrame) -> None:
    result = compute_metric(
        frame,
        MetricSpec(
            name="margin", kind="ratio", numerator="revenue", denominator="cost", column=None
        ),
    )
    assert result["value"] == pytest.approx(400.0 / 260.0, abs=1e-6)
    assert result["formula"] == "SUM(revenue) / SUM(cost)"


def test_ratio_divide_by_zero_returns_null_with_warning(frame: pd.DataFrame) -> None:
    result = compute_metric(
        frame,
        MetricSpec(name="bad", kind="ratio", numerator="revenue", denominator="zeros"),
    )
    assert result["value"] is None
    assert "分母为 0，比率无法计算" in result["warnings"]


def test_rate_with_value_when(frame: pd.DataFrame) -> None:
    result = compute_metric(
        frame, MetricSpec(name="return_rate", kind="rate", value_when="returns_flag = 1")
    )
    assert result["value"] == pytest.approx(0.5)
    assert "COUNT(returns_flag = 1)" in result["formula"]


def test_growth_rate_uses_last_two_periods(frame: pd.DataFrame) -> None:
    result = compute_metric(
        frame,
        MetricSpec(
            name="growth",
            kind="growth_rate",
            column="revenue",
            date_column="order_date",
            period="month",
            agg="sum",
        ),
    )
    # 1 月 300 → 2 月 100
    assert result["value"] == pytest.approx((100.0 - 300.0) / 300.0, abs=1e-6)
    assert "2025-02" in result["formula"] and "2025-01" in result["formula"]
    assert [group["key"]["month"] for group in result["groups"]] == ["2025-01", "2025-02"]


def test_growth_rate_requires_complete_params() -> None:
    with pytest.raises(ValueError):
        MetricSpec(name="g", kind="growth_rate", column="revenue")


def test_filters_ops(frame: pd.DataFrame) -> None:
    assert value_of(
        frame,
        name="f",
        kind="sum",
        column="revenue",
        filters=[FilterSpec(column="channel", op="=", value="DTC")],
    ) == pytest.approx(300.0)
    assert value_of(
        frame,
        name="f",
        kind="sum",
        column="revenue",
        filters=[FilterSpec(column="channel", op="in", value=["DTC", "Outlet"])],
    ) == pytest.approx(400.0)
    assert value_of(
        frame,
        name="f",
        kind="sum",
        column="revenue",
        filters=[FilterSpec(column="revenue", op="between", value=[60, 200])],
    ) == pytest.approx(300.0)
    assert value_of(
        frame,
        name="f",
        kind="count",
        filters=[FilterSpec(column="returns_flag", op=">=", value=1)],
    ) == pytest.approx(2.0)
    assert value_of(
        frame,
        name="f",
        kind="count",
        filters=[FilterSpec(column="region", op="is_not_null")],
    ) == pytest.approx(4.0)


def test_month_period_grouping(frame: pd.DataFrame) -> None:
    result = compute_metric(
        frame,
        MetricSpec(
            name="monthly",
            kind="sum",
            column="revenue",
            group_by=["month"],
            date_column="order_date",
            sort=None,
        ),
    )
    groups = {item["key"]["month"]: item["value"] for item in result["groups"]}
    assert groups == {"2025-01": pytest.approx(300.0), "2025-02": pytest.approx(100.0)}
    assert "month(order_date)" in result["formula"]


def test_period_alone_implies_grouping(frame: pd.DataFrame) -> None:
    """只写 period 不写 group_by 时也必须按周期分组，不能静默退化成标量。"""
    result = compute_metric(
        frame,
        MetricSpec(
            name="monthly",
            kind="sum",
            column="revenue",
            date_column="order_date",
            period="month",
        ),
    )
    assert result["value"] is None
    groups = {item["key"]["month"]: item["value"] for item in result["groups"]}
    assert groups == {"2025-01": pytest.approx(300.0), "2025-02": pytest.approx(100.0)}
    assert "GROUP BY month(order_date)" in result["formula"]


def test_period_combines_with_group_by(frame: pd.DataFrame) -> None:
    result = compute_metric(
        frame,
        MetricSpec(
            name="monthly_by_channel",
            kind="sum",
            column="revenue",
            group_by=["channel"],
            date_column="order_date",
            period="month",
        ),
    )
    keys = {(item["key"]["month"], item["key"]["channel"]): item["value"] for item in result["groups"]}
    assert keys == {
        ("2025-01", "DTC"): pytest.approx(300.0),
        ("2025-02", "Outlet"): pytest.approx(100.0),
    }
    assert "GROUP BY channel, month(order_date)" in result["formula"]


def test_period_infers_date_column(frame: pd.DataFrame) -> None:
    result = compute_metric(
        frame,
        MetricSpec(name="monthly", kind="count", period="month"),
    )
    groups = {item["key"]["month"]: item["value"] for item in result["groups"]}
    assert groups == {"2025-01": pytest.approx(2.0), "2025-02": pytest.approx(2.0)}
    assert "month(order_date)" in result["formula"]


def test_invalid_column_raises(frame: pd.DataFrame) -> None:
    with pytest.raises(AppError) as info:
        compute_metric(frame, MetricSpec(name="x", kind="sum", column="nope"))
    assert info.value.code == ErrorCode.INVALID_COLUMN.value
    assert "channel" in info.value.details["available"]


def test_empty_filter_result_warns(frame: pd.DataFrame) -> None:
    result = compute_metric(
        frame,
        MetricSpec(
            name="none",
            kind="sum",
            column="revenue",
            filters=[FilterSpec(column="channel", op="=", value="Missing")],
        ),
    )
    assert result["value"] is None
    assert any("没有匹配" in warning for warning in result["warnings"])
    assert result["inputs"]["rows_used"] == 0


def test_ratio_with_group_by(frame: pd.DataFrame) -> None:
    result = compute_metric(
        frame,
        MetricSpec(
            name="margin_by_channel",
            kind="ratio",
            numerator="revenue",
            denominator="cost",
            group_by=["channel"],
        ),
    )
    groups = {item["key"]["channel"]: item["value"] for item in result["groups"]}
    assert groups["DTC"] == pytest.approx(300.0 / 180.0, abs=1e-6)
    assert groups["Outlet"] == pytest.approx(100.0 / 80.0, abs=1e-6)
    assert "GROUP BY channel" in result["formula"]


def test_rate_with_group_by(frame: pd.DataFrame) -> None:
    result = compute_metric(
        frame,
        MetricSpec(
            name="return_rate_by_channel",
            kind="rate",
            value_when="returns_flag = 1",
            group_by=["channel"],
        ),
    )
    groups = {item["key"]["channel"]: item["value"] for item in result["groups"]}
    assert groups["DTC"] == pytest.approx(0.5)
    assert groups["Outlet"] == pytest.approx(0.5)


def test_compute_metrics_returns_all(frame: pd.DataFrame) -> None:
    result = compute_metrics(
        frame,
        [MetricSpec(name="a", kind="sum", column="revenue"), MetricSpec(name="b", kind="count")],
    )
    assert [metric["name"] for metric in result["metrics"]] == ["a", "b"]
