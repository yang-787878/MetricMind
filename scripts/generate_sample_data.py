#!/usr/bin/env python
"""Generate the deterministic MetricMind sample datasets.

Run from the repository root:

    python scripts/generate_sample_data.py

Outputs (always byte-identical for a fixed seed):
    data/sample_sales.csv
    data/sample_marketing_funnel.csv
    data/samples.json
"""

from __future__ import annotations

import calendar
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

SEED = 20260101

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
SALES_PATH = DATA_DIR / "sample_sales.csv"
FUNNEL_PATH = DATA_DIR / "sample_marketing_funnel.csv"
REGISTRY_PATH = DATA_DIR / "samples.json"

SALES_COLUMNS = [
    "order_id",
    "order_date",
    "region",
    "channel",
    "product_category",
    "product_name",
    "units",
    "unit_price",
    "discount_pct",
    "revenue",
    "cost",
    "gross_profit",
    "returns_flag",
    "customer_segment",
]

# Volume plan: 810 orders per month for Jan-Aug, 700 for September.
# This gives 7,180 rows (target 7,000-7,400) and a headline revenue decline
# of roughly 18% once the September Home discount uplift is included.
DTC_ORDERS_BASE = 365
WHOLESALE_ORDERS_BASE = 283
OUTLET_ORDERS_BASE = 162
DTC_ORDERS_SEPTEMBER = 274  # 274 / 365 - 1 = -24.93%
WHOLESALE_ORDERS_SEPTEMBER = 272
OUTLET_ORDERS_SEPTEMBER = 154

CHANNELS = ["DTC", "Wholesale", "Outlet"]
CATEGORIES = ["Home", "Electronics", "Apparel", "Beauty"]
CATEGORY_WEIGHTS = [0.28, 0.25, 0.27, 0.20]
REGIONS = ["North", "South", "East", "West"]
REGION_WEIGHTS = [0.27, 0.24, 0.26, 0.23]
SEGMENTS = ["New", "Returning", "VIP"]
SEGMENT_WEIGHTS = [0.33, 0.49, 0.18]

PRICE_RANGES = {
    "Home": (100.0, 1200.0),
    "Electronics": (200.0, 3000.0),
    "Apparel": (50.0, 600.0),
    "Beauty": (30.0, 400.0),
}
PRODUCT_NAMES = {
    "Home": ["Aurora Desk Lamp", "Oak Side Table", "Linen Throw Pillow"],
    "Electronics": ["Pulse Wireless Headphones", "Nova 27in Monitor", "Orbit Smart Speaker"],
    "Apparel": ["Everyday Knit Sweater", "Trail Running Jacket", "Classic Denim Jeans"],
    "Beauty": ["Hydra Glow Serum", "Mineral Sunscreen SPF50", "Velvet Matte Lipstick"],
}

# Data-quality injections (exact counts).
N_NULL_REGION = 120
N_DUPLICATE_ORDER_IDS = 15
N_ZERO_UNIT_PRICE = 30
N_2024_ORDER_DATES = 8
N_DISCOUNT_OUTLIERS = 3
DISCOUNT_OUTLIER_VALUE = 0.95
QUALITY_2024_START_DATE = date(2024, 11, 4)
DISCOUNT_OUTLIER_MONTHS = (2, 5, 8)

# Planted business-pattern parameters.
HOME_SEPTEMBER_DISCOUNT_LOW = 0.20
HOME_SEPTEMBER_DISCOUNT_HIGH = 0.32
NORMAL_DISCOUNT_ZERO_SHARE = 0.35
NORMAL_DISCOUNT_LOW = 0.05
NORMAL_DISCOUNT_HIGH = 0.35
OUTLET_RETURN_RATE_BASE = 0.03
OUTLET_RETURN_RATE_SEPTEMBER = 0.07
DTC_RETURN_RATE = 0.02
WHOLESALE_RETURN_RATE = 0.025

# Zero-price rows are spread over the nine 2025 months so they do not bias
# any single month's trend.
ZERO_PRICE_QUOTA = {1: 3, 2: 3, 3: 3, 4: 3, 5: 4, 6: 4, 7: 4, 8: 3, 9: 3}

# Marketing funnel: 52 ISO weeks x 5 channels = 260 rows.
FUNNEL_CHANNELS = ["Paid Search", "Social", "Email", "Affiliate", "Direct"]
FUNNEL_BASE_SESSIONS = {
    "Paid Search": 30000,
    "Social": 18000,
    "Email": 9000,
    "Affiliate": 7000,
    "Direct": 22000,
}
FUNNEL_CONVERSION = {
    "Paid Search": 0.030,
    "Social": 0.016,
    "Email": 0.055,
    "Affiliate": 0.024,
    "Direct": 0.060,
}
FUNNEL_AOV = {
    "Paid Search": 145.0,
    "Social": 95.0,
    "Email": 120.0,
    "Affiliate": 130.0,
    "Direct": 165.0,
}
FUNNEL_CPC = {
    "Paid Search": 1.10,
    "Social": 0.55,
    "Email": 0.0,
    "Affiliate": 0.35,
    "Direct": 0.0,
}
FUNNEL_WEEKS = 52


@dataclass(frozen=True)
class SalesMetrics:
    row_count: int
    date_min: str
    date_max: str
    september_revenue: float
    baseline_monthly_revenue: float
    revenue_change_pct: float
    dtc_september_orders: int
    dtc_baseline_monthly_orders: float
    dtc_orders_change_pct: float
    dtc_decline_contribution_pct: float
    home_revenue_change_pct: float
    home_gross_profit_change_pct: float
    outlet_returns_september: float
    outlet_returns_baseline: float
    null_region: int
    duplicate_order_ids: int
    zero_unit_price: int
    dates_2024: int
    discount_outliers: int
    max_region_share_shift_pct: float
    max_segment_share_shift_pct: float
    home_discount_september: float
    home_discount_baseline: float


def _month_channel_counts() -> dict[int, dict[str, int]]:
    plan: dict[int, dict[str, int]] = {}
    for month in range(1, 9):
        plan[month] = {
            "DTC": DTC_ORDERS_BASE,
            "Wholesale": WHOLESALE_ORDERS_BASE,
            "Outlet": OUTLET_ORDERS_BASE,
        }
    plan[9] = {
        "DTC": DTC_ORDERS_SEPTEMBER,
        "Wholesale": WHOLESALE_ORDERS_SEPTEMBER,
        "Outlet": OUTLET_ORDERS_SEPTEMBER,
    }
    return plan


def _return_quota(month: int, channel: str, rows_in_group: int) -> int:
    """Exact monthly return counts, so the Outlet 3% -> 7% shift is stable."""
    if channel == "Outlet":
        rate = OUTLET_RETURN_RATE_SEPTEMBER if month == 9 else OUTLET_RETURN_RATE_BASE
        return round(rows_in_group * rate)
    if channel == "DTC":
        return round(rows_in_group * DTC_RETURN_RATE)
    return round(rows_in_group * WHOLESALE_RETURN_RATE)


def _stratified_values(
    low: float, high: float, count: int, rng: random.Random
) -> list[float]:
    """Evenly spaced values in [low, high], shuffled for a natural order."""
    values = [round(low + (index + 0.5) * (high - low) / count, 2) for index in range(count)]
    rng.shuffle(values)
    return values


def _stratified_units(count: int, rng: random.Random) -> list[int]:
    values = [(index % 8) + 1 for index in range(count)]
    rng.shuffle(values)
    return values


def _stratified_discounts(
    count: int, home_september: bool, rng: random.Random
) -> list[float]:
    if home_september:
        spread = HOME_SEPTEMBER_DISCOUNT_HIGH - HOME_SEPTEMBER_DISCOUNT_LOW
        values = [
            round(HOME_SEPTEMBER_DISCOUNT_LOW + (index + 0.5) * spread / count, 2)
            for index in range(count)
        ]
    else:
        zero_count = round(count * NORMAL_DISCOUNT_ZERO_SHARE)
        paid_count = count - zero_count
        spread = NORMAL_DISCOUNT_HIGH - NORMAL_DISCOUNT_LOW
        values = [0.0] * zero_count + [
            round(NORMAL_DISCOUNT_LOW + (index + 0.5) * spread / paid_count, 2)
            for index in range(paid_count)
        ]
    rng.shuffle(values)
    return values


def _build_sales_frame(rng: random.Random) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for month, channel_counts in _month_channel_counts().items():
        days_in_month = calendar.monthrange(2025, month)[1]
        for channel in CHANNELS:
            category_sequence = _balanced_label_sequence(
                channel_counts[channel], CATEGORIES, CATEGORY_WEIGHTS
            )
            for category in CATEGORIES:
                category_count = category_sequence.count(category)
                low, high = PRICE_RANGES[category]
                prices = _stratified_values(low, high, category_count, rng)
                units_values = _stratified_units(category_count, rng)
                discounts = _stratified_discounts(
                    category_count, category == "Home" and month == 9, rng
                )
                for index in range(category_count):
                    rows.append(
                        {
                            "order_id": "",
                            "order_date": date(
                                2025, month, rng.randint(1, days_in_month)
                            ).isoformat(),
                            "region": rng.choices(REGIONS, weights=REGION_WEIGHTS, k=1)[0],
                            "channel": channel,
                            "product_category": category,
                            "product_name": rng.choice(PRODUCT_NAMES[category]),
                            "units": units_values[index],
                            "unit_price": prices[index],
                            "discount_pct": discounts[index],
                            "revenue": 0.0,
                            "cost": 0.0,
                            "gross_profit": 0.0,
                            "returns_flag": 0,
                            "customer_segment": rng.choices(
                                SEGMENTS, weights=SEGMENT_WEIGHTS, k=1
                            )[0],
                        }
                    )

    rng.shuffle(rows)
    frame = pd.DataFrame(rows, columns=SALES_COLUMNS)
    frame["order_id"] = [f"ORD-{index:06d}" for index in range(1, len(frame) + 1)]

    # Exact per-month/per-channel return counts.
    for month, channel_counts in _month_channel_counts().items():
        prefix = f"2025-{month:02d}-"
        for channel, count in channel_counts.items():
            group = frame.index[
                frame["order_date"].str.startswith(prefix) & (frame["channel"] == channel)
            ].to_list()
            quota = _return_quota(month, channel, count)
            for row_index in rng.sample(group, quota):
                frame.at[row_index, "returns_flag"] = 1
    return frame


def _sample_excluding(
    rng: random.Random,
    candidates: list[int],
    count: int,
    used: set[int],
) -> list[int]:
    pool = [index for index in candidates if index not in used]
    if len(pool) < count:
        raise ValueError(f"not enough candidate rows: need {count}, have {len(pool)}")
    chosen = rng.sample(pool, count)
    used.update(chosen)
    return chosen


def _stratified_null_regions(frame: pd.DataFrame, rng: random.Random) -> None:
    periods = sorted(frame["order_date"].str[:7].unique())
    total = len(frame)
    counts = {period: int((frame["order_date"].str[:7] == period).sum()) for period in periods}
    raw = {period: N_NULL_REGION * counts[period] / total for period in periods}
    quotas = {period: int(raw[period]) for period in periods}
    remainder = N_NULL_REGION - sum(quotas.values())
    for period in sorted(periods, key=lambda item: raw[item] - quotas[item], reverse=True)[:remainder]:
        quotas[period] += 1

    used: set[int] = set()
    for period in periods:
        if quotas[period] == 0:
            continue
        group = frame.index[frame["order_date"].str.startswith(period)].to_list()
        chosen = _sample_excluding(rng, group, quotas[period], used)
        for row_index in chosen:
            frame.at[row_index, "region"] = None


def _balanced_label_sequence(
    size: int, labels: list[str], weights: list[float]
) -> list[str]:
    """Build a low-discrepancy label sequence with exact target counts."""
    raw = [size * weight for weight in weights]
    counts = [int(value) for value in raw]
    remainder = size - sum(counts)
    fractional_order = sorted(
        range(len(labels)), key=lambda index: raw[index] - counts[index], reverse=True
    )
    for index in fractional_order[:remainder]:
        counts[index] += 1

    remaining = counts.copy()
    sequence: list[str] = []
    while len(sequence) < size:
        candidates = [index for index, count in enumerate(remaining) if count > 0]
        chosen = max(
            candidates,
            key=lambda index: (
                remaining[index] / weights[index] if weights[index] else remaining[index],
                remaining[index],
            ),
        )
        sequence.append(labels[chosen])
        remaining[chosen] -= 1
    return sequence


def _balance_revenue_dimension(
    frame: pd.DataFrame,
    column: str,
    labels: list[str],
    weights: list[float],
) -> None:
    """Assign a dimension so its monthly revenue mix stays stable.

    Within each month, rows are sorted by revenue and labels are assigned by a
    low-discrepancy sequence. Every label therefore sees the same revenue
    quantiles, keeping month-to-month revenue shares nearly flat.
    """
    months = sorted(frame["order_date"].str[:7].unique())
    for period in months:
        month_mask = frame["order_date"].str.startswith(period)
        if column == "region":
            month_mask &= frame["region"].notna()
        row_indexes = frame.index[month_mask].to_list()
        row_indexes.sort(
            key=lambda index: (
                -float(frame.at[index, "revenue"]),
                str(frame.at[index, "order_id"]),
            )
        )
        sequence = _balanced_label_sequence(len(row_indexes), labels, weights)
        for row_index, label in zip(row_indexes, sequence):
            frame.at[row_index, column] = label


def _inject_quality_issues(frame: pd.DataFrame) -> None:
    quality_rng = random.Random(SEED + 2)
    used: set[int] = set()

    # Exactly 30 rows with unit_price == 0, spread across 2025 months.
    for month, quota in ZERO_PRICE_QUOTA.items():
        candidates = frame.index[
            frame["order_date"].str.startswith(f"2025-{month:02d}-")
        ].to_list()
        for row_index in _sample_excluding(quality_rng, candidates, quota, used):
            frame.at[row_index, "unit_price"] = 0.0

    # Three extreme 0.95 discounts, kept away from Home/September so they do
    # not distort the planted Home margin story.
    for month in DISCOUNT_OUTLIER_MONTHS:
        candidates = frame.index[
            frame["order_date"].str.startswith(f"2025-{month:02d}-")
            & (frame["product_category"] != "Home")
        ].to_list()
        row_index = _sample_excluding(quality_rng, candidates, 1, used)[0]
        frame.at[row_index, "discount_pct"] = DISCOUNT_OUTLIER_VALUE

    # Eight order dates moved into 2024 (from Jan/Feb, so Jun-Sep trends stay clean).
    candidates = frame.index[
        frame["order_date"].str.startswith(("2025-01-", "2025-02-"))
    ].to_list()
    for offset, row_index in enumerate(
        _sample_excluding(quality_rng, candidates, N_2024_ORDER_DATES, used)
    ):
        frame.at[row_index, "order_date"] = (
            QUALITY_2024_START_DATE + timedelta(days=offset)
        ).isoformat()

    # Region nulls are stratified by month.
    _stratified_null_regions(frame, quality_rng)

    # Fifteen duplicated order_id values. Pairs live in the same month/channel
    # (Wholesale or Outlet) so DTC order counts remain unambiguous.
    pair_groups: list[tuple[str, str]] = []
    for month in range(1, 10):
        prefix = f"2025-{month:02d}-"
        for channel in ("Wholesale", "Outlet"):
            pair_groups.append((prefix, channel))
    quality_rng.shuffle(pair_groups)
    duplicated = 0
    for prefix, channel in pair_groups:
        if duplicated >= N_DUPLICATE_ORDER_IDS:
            break
        group = frame.index[
            frame["order_date"].str.startswith(prefix) & (frame["channel"] == channel)
        ].to_list()
        first, second = quality_rng.sample(group, 2)
        frame.at[second, "order_id"] = frame.at[first, "order_id"]
        duplicated += 1

    # Guarantee the advertised overall date span while keeping 2024 rows.
    if not (frame["order_date"] == "2025-01-01").any():
        candidate = frame.index[frame["order_date"].str.startswith("2025-01-")][0]
        frame.at[candidate, "order_date"] = "2025-01-01"
    if not (frame["order_date"] == "2025-09-30").any():
        candidate = frame.index[frame["order_date"].str.startswith("2025-09-")][0]
        frame.at[candidate, "order_date"] = "2025-09-30"


def _recompute_financials(frame: pd.DataFrame) -> None:
    units = frame["units"].astype(float)
    price = frame["unit_price"].astype(float)
    discount = frame["discount_pct"].astype(float)
    frame["revenue"] = (units * price * (1.0 - discount)).round(2)
    frame["cost"] = (units * price * 0.62).round(2)
    frame["gross_profit"] = (frame["revenue"] - frame["cost"]).round(2)


def build_sales() -> pd.DataFrame:
    rng = random.Random(SEED)
    frame = _build_sales_frame(rng)
    _inject_quality_issues(frame)
    _recompute_financials(frame)
    _balance_revenue_dimension(frame, "region", REGIONS, REGION_WEIGHTS)
    _balance_revenue_dimension(frame, "customer_segment", SEGMENTS, SEGMENT_WEIGHTS)
    frame = frame.sort_values(["order_date", "order_id"], kind="mergesort").reset_index(drop=True)
    return frame[SALES_COLUMNS]


def build_funnel() -> pd.DataFrame:
    rng = random.Random(SEED + 1)
    rows: list[dict[str, object]] = []
    for week in range(1, FUNNEL_WEEKS + 1):
        monday = date.fromisocalendar(2025, week, 1)
        week_label = f"{monday.isocalendar().year}-W{monday.isocalendar().week:02d}"
        seasonal = 1.22 if week >= 40 else 1.0 + 0.06 * ((week % 5) - 2)
        for channel in FUNNEL_CHANNELS:
            sessions = int(
                round(FUNNEL_BASE_SESSIONS[channel] * seasonal * rng.uniform(0.88, 1.12))
            )
            rate = FUNNEL_CONVERSION[channel] * rng.uniform(0.93, 1.07)
            orders = max(1, int(round(sessions * rate)))
            orders = min(orders, sessions - 1)
            revenue = round(orders * FUNNEL_AOV[channel] * rng.uniform(0.92, 1.08), 2)
            spend = round(sessions * FUNNEL_CPC[channel] * rng.uniform(0.90, 1.10), 2)
            rows.append(
                {
                    "week": week_label,
                    "channel": channel,
                    "sessions": sessions,
                    "orders": orders,
                    "spend": spend,
                    "revenue": revenue,
                }
            )
    return pd.DataFrame(
        rows, columns=["week", "channel", "sessions", "orders", "spend", "revenue"]
    )


def _pct_change(new: float, old: float) -> float:
    return (new / old - 1.0) * 100.0 if old else float("nan")


def compute_metrics(frame: pd.DataFrame) -> SalesMetrics:
    dated = frame.copy()
    dated["order_date"] = pd.to_datetime(dated["order_date"], errors="coerce")
    dated["month"] = dated["order_date"].dt.strftime("%Y-%m")

    september = dated[dated["month"] == "2025-09"]
    baseline = dated[dated["month"].isin(["2025-06", "2025-07", "2025-08"])]
    baseline_months = 3

    baseline_revenue = baseline["revenue"].sum() / baseline_months
    september_revenue = september["revenue"].sum()
    revenue_change = _pct_change(september_revenue, baseline_revenue)

    dtc_base_orders = len(baseline[baseline["channel"] == "DTC"]) / baseline_months
    dtc_sep_orders = len(september[september["channel"] == "DTC"])
    dtc_orders_change = _pct_change(dtc_sep_orders, dtc_base_orders)

    dtc_base_revenue = baseline.loc[baseline["channel"] == "DTC", "revenue"].sum() / baseline_months
    dtc_sep_revenue = september.loc[september["channel"] == "DTC", "revenue"].sum()
    total_decline = baseline_revenue - september_revenue
    contribution = (dtc_base_revenue - dtc_sep_revenue) / total_decline * 100.0

    home_base = baseline[baseline["product_category"] == "Home"]
    home_sep = september[september["product_category"] == "Home"]
    home_revenue_change = _pct_change(
        home_sep["revenue"].sum(), home_base["revenue"].sum() / baseline_months
    )
    home_profit_change = _pct_change(
        home_sep["gross_profit"].sum(), home_base["gross_profit"].sum() / baseline_months
    )

    outlet_base = baseline[baseline["channel"] == "Outlet"]["returns_flag"].mean()
    outlet_sep = september[september["channel"] == "Outlet"]["returns_flag"].mean()

    max_region_shift = 0.0
    for region in REGIONS:
        base_share = (
            baseline.loc[baseline["region"] == region, "revenue"].sum()
            / baseline["revenue"].sum()
        )
        sep_share = (
            september.loc[september["region"] == region, "revenue"].sum()
            / september["revenue"].sum()
        )
        max_region_shift = max(max_region_shift, abs(_pct_change(sep_share, base_share)))

    max_segment_shift = 0.0
    for segment in SEGMENTS:
        base_share = (
            baseline.loc[baseline["customer_segment"] == segment, "revenue"].sum()
            / baseline["revenue"].sum()
        )
        sep_share = (
            september.loc[september["customer_segment"] == segment, "revenue"].sum()
            / september["revenue"].sum()
        )
        max_segment_shift = max(max_segment_shift, abs(_pct_change(sep_share, base_share)))

    return SalesMetrics(
        row_count=len(frame),
        date_min=frame["order_date"].min(),
        date_max=frame["order_date"].max(),
        september_revenue=round(september_revenue, 2),
        baseline_monthly_revenue=round(baseline_revenue, 2),
        revenue_change_pct=round(revenue_change, 2),
        dtc_september_orders=dtc_sep_orders,
        dtc_baseline_monthly_orders=round(dtc_base_orders, 2),
        dtc_orders_change_pct=round(dtc_orders_change, 2),
        dtc_decline_contribution_pct=round(contribution, 2),
        home_revenue_change_pct=round(home_revenue_change, 2),
        home_gross_profit_change_pct=round(home_profit_change, 2),
        outlet_returns_september=round(outlet_sep * 100.0, 2),
        outlet_returns_baseline=round(outlet_base * 100.0, 2),
        null_region=int(frame["region"].isna().sum()),
        duplicate_order_ids=int(frame["order_id"].duplicated().sum()),
        zero_unit_price=int((frame["unit_price"] == 0).sum()),
        dates_2024=int(pd.to_datetime(frame["order_date"]).dt.year.eq(2024).sum()),
        discount_outliers=int((frame["discount_pct"] == DISCOUNT_OUTLIER_VALUE).sum()),
        max_region_share_shift_pct=round(max_region_shift, 2),
        max_segment_share_shift_pct=round(max_segment_shift, 2),
        home_discount_september=round(
            september.loc[september["product_category"] == "Home", "discount_pct"].mean(), 4
        ),
        home_discount_baseline=round(
            home_base["discount_pct"].mean(), 4
        ),
    )


def _validate(metrics: SalesMetrics, funnel: pd.DataFrame) -> None:
    errors: list[str] = []
    if not 7000 <= metrics.row_count <= 7400:
        errors.append(f"sales row_count {metrics.row_count} outside 7000-7400")
    if not 16.0 <= abs(metrics.revenue_change_pct) <= 20.0:
        errors.append(f"September revenue change {metrics.revenue_change_pct}% outside -16%..-20%")
    if metrics.dtc_orders_change_pct > -22.0 or metrics.dtc_orders_change_pct < -28.0:
        errors.append(f"DTC order change {metrics.dtc_orders_change_pct}% outside -22%..-28%")
    if metrics.dtc_decline_contribution_pct < 60.0:
        errors.append(f"DTC decline contribution {metrics.dtc_decline_contribution_pct}% < 60%")
    if metrics.home_revenue_change_pct >= 0 or metrics.home_gross_profit_change_pct >= 0:
        errors.append("Home revenue and gross profit must both decline")
    if metrics.home_gross_profit_change_pct >= metrics.home_revenue_change_pct:
        errors.append("Home gross profit decline must exceed revenue decline")
    if not 6.0 <= metrics.outlet_returns_september <= 8.0:
        errors.append(f"Outlet September return rate {metrics.outlet_returns_september}% not ~7%")
    if not 2.0 <= metrics.outlet_returns_baseline <= 4.0:
        errors.append(f"Outlet baseline return rate {metrics.outlet_returns_baseline}% not ~3%")
    if metrics.null_region != N_NULL_REGION:
        errors.append(f"null region count {metrics.null_region} != {N_NULL_REGION}")
    if metrics.duplicate_order_ids != N_DUPLICATE_ORDER_IDS:
        errors.append(
            f"duplicate order_id count {metrics.duplicate_order_ids} != {N_DUPLICATE_ORDER_IDS}"
        )
    if metrics.zero_unit_price != N_ZERO_UNIT_PRICE:
        errors.append(f"zero unit_price count {metrics.zero_unit_price} != {N_ZERO_UNIT_PRICE}")
    if metrics.dates_2024 != N_2024_ORDER_DATES:
        errors.append(f"2024 order_date count {metrics.dates_2024} != {N_2024_ORDER_DATES}")
    if metrics.discount_outliers != N_DISCOUNT_OUTLIERS:
        errors.append(
            f"0.95 discount count {metrics.discount_outliers} != {N_DISCOUNT_OUTLIERS}"
        )
    if metrics.max_region_share_shift_pct > 5.0:
        errors.append(f"region share shift {metrics.max_region_share_shift_pct}% > 5%")
    if metrics.max_segment_share_shift_pct > 5.0:
        errors.append(f"segment share shift {metrics.max_segment_share_shift_pct}% > 5%")
    if len(funnel) != 260:
        errors.append(f"funnel row_count {len(funnel)} != 260")
    if set(funnel["channel"]) != set(FUNNEL_CHANNELS):
        errors.append("funnel channels do not match the contract")
    if not (funnel["orders"] < funnel["sessions"]).all():
        errors.append("funnel has orders >= sessions")
    if errors:
        raise RuntimeError("sample data self-check failed: " + "; ".join(errors))


def _write_outputs(sales: pd.DataFrame, funnel: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sales.to_csv(
        SALES_PATH,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        float_format="%.2f",
    )
    funnel.to_csv(
        FUNNEL_PATH,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        float_format="%.2f",
    )

    registry = {
        "samples": [
            {
                "key": "sales",
                "name": "销售订单示例数据",
                "description": (
                    f"{len(sales)} 行、14 列的销售订单明细，主时间范围 2025-01-01 至 "
                    "2025-09-30（另含 8 行 2024-11 的异常日期，用于数据质量检验），"
                    "覆盖渠道、品类、地区与客户分层，可直接用于下降归因分析。"
                ),
                "filename": SALES_PATH.name,
                "row_count": len(sales),
                "recommended_questions": [
                    "为什么 2025 年 9 月销售额相比 6–8 月下降了？",
                    "各渠道的订单量和客单价有什么差异？",
                    "哪些品类贡献了大部分收入，9 月毛利率发生了什么变化？",
                ],
            },
            {
                "key": "marketing_funnel",
                "name": "营销漏斗示例数据",
                "description": (
                    f"{len(funnel)} 行、5 个渠道的周度营销漏斗数据，覆盖 2025-W01 至 "
                    "2025-W52，包含 sessions、orders、spend 与 revenue，可用于渠道转化率与投入产出比较。"
                ),
                "filename": FUNNEL_PATH.name,
                "row_count": len(funnel),
                "recommended_questions": [
                    "不同渠道的转化率（orders/sessions）有什么区别？",
                    "各渠道带来的订单量和收入贡献如何？",
                    "转化率在 2025 年各周是否有明显的季节性变化？",
                ],
            },
        ]
    }
    REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _print_self_check(sales: pd.DataFrame, funnel: pd.DataFrame, metrics: SalesMetrics) -> None:
    print("=" * 72)
    print("MetricMind sample data self-check")
    print("=" * 72)
    print(f"sales rows              : {metrics.row_count}")
    print(f"sales date range        : {metrics.date_min} .. {metrics.date_max}")
    print(f"2025-09 revenue         : {metrics.september_revenue:,.2f}")
    print(f"2025-06..08 avg revenue : {metrics.baseline_monthly_revenue:,.2f}")
    print(f"revenue change          : {metrics.revenue_change_pct:+.2f}%")
    print(
        f"DTC orders Sep / base   : {metrics.dtc_september_orders} / "
        f"{metrics.dtc_baseline_monthly_orders:.2f} "
        f"({metrics.dtc_orders_change_pct:+.2f}%)"
    )
    print(f"DTC decline contribution: {metrics.dtc_decline_contribution_pct:.2f}%")
    print(
        f"Home revenue / GP change: {metrics.home_revenue_change_pct:+.2f}% / "
        f"{metrics.home_gross_profit_change_pct:+.2f}%"
    )
    print(
        f"Home discount Sep / base: {metrics.home_discount_september:.4f} / "
        f"{metrics.home_discount_baseline:.4f}"
    )
    print(
        f"Outlet returns Sep/base : {metrics.outlet_returns_september:.2f}% / "
        f"{metrics.outlet_returns_baseline:.2f}%"
    )
    print(
        f"region share shift max  : {metrics.max_region_share_shift_pct:.2f}% | "
        f"segment share shift max: {metrics.max_segment_share_shift_pct:.2f}%"
    )
    print(
        "quality counts          : "
        f"null_region={metrics.null_region}, duplicate_order_id={metrics.duplicate_order_ids}, "
        f"zero_price={metrics.zero_unit_price}, dates_2024={metrics.dates_2024}, "
        f"discount_0.95={metrics.discount_outliers}"
    )
    print(f"funnel rows             : {len(funnel)}")
    print(
        "funnel conversion       : "
        + ", ".join(
            f"{channel}={funnel.loc[funnel['channel'] == channel, 'orders'].sum() / funnel.loc[funnel['channel'] == channel, 'sessions'].sum():.4%}"
            for channel in FUNNEL_CHANNELS
        )
    )
    print("=" * 72)


def main() -> None:
    random.seed(SEED)
    sales = build_sales()
    funnel = build_funnel()
    metrics = compute_metrics(sales)
    _validate(metrics, funnel)
    _write_outputs(sales, funnel)
    _print_self_check(sales, funnel, metrics)


if __name__ == "__main__":
    main()
