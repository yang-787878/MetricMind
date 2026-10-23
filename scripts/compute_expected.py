"""用纯 pandas 独立计算金标准答案（§9.2）。

刻意不 import 后端的任何模块：这是交叉验证手段——如果 Agent 工具算出的值
和这里差超过 0.5%，说明工具实现有 bug，而不是"两边都错得一样"。

运行：python scripts/compute_expected.py
输出：data/expected_answers.json
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SALES = ROOT / "data" / "sample_sales.csv"
FUNNEL = ROOT / "data" / "sample_marketing_funnel.csv"
OUT = ROOT / "data" / "expected_answers.json"

SEP = "2025-09"
BASE_MONTHS = ("2025-06", "2025-07", "2025-08")


def load_sales() -> pd.DataFrame:
    frame = pd.read_csv(SALES)
    frame["order_date"] = pd.to_datetime(frame["order_date"])
    frame["month"] = frame["order_date"].dt.strftime("%Y-%m")
    return frame


def metric(value: float | None, unit: str, method: str) -> dict[str, Any]:
    rounded = None if value is None else round(float(value), 4)
    return {"value": rounded, "unit": unit, "method": method}


def compute_sales(frame: pd.DataFrame) -> dict[str, Any]:
    monthly = frame.groupby("month")["revenue"].sum()
    total_revenue = float(frame["revenue"].sum())
    sep_revenue = float(monthly.get(SEP, 0.0))
    august_revenue = float(monthly.get(BASE_MONTHS[-1], 0.0))
    base_revenue = float(monthly.loc[list(BASE_MONTHS)].mean())

    dtc_orders = frame[frame["channel"] == "DTC"].groupby("month").size()
    dtc_revenue = frame[frame["channel"] == "DTC"].groupby("month")["revenue"].sum()
    dtc_sep_orders = float(dtc_orders.get(SEP, 0))
    dtc_base_orders = float(dtc_orders.loc[list(BASE_MONTHS)].mean())
    dtc_sep_revenue = float(dtc_revenue.get(SEP, 0.0))
    dtc_base_revenue = float(dtc_revenue.loc[list(BASE_MONTHS)].mean())

    home = frame[frame["product_category"] == "Home"].groupby("month").agg(
        revenue=("revenue", "sum"), gross_profit=("gross_profit", "sum")
    )
    home_sep_rev = float(home.loc[SEP, "revenue"])
    home_base_rev = float(home.loc[list(BASE_MONTHS), "revenue"].mean())
    home_sep_gp = float(home.loc[SEP, "gross_profit"])
    home_base_gp = float(home.loc[list(BASE_MONTHS), "gross_profit"].mean())
    home_sep_margin = home_sep_gp / home_sep_rev
    home_base_margin = home_base_gp / home_base_rev

    outlet = frame[frame["channel"] == "Outlet"].groupby("month")["returns_flag"].mean()
    outlet_sep = float(outlet.get(SEP, 0.0))
    outlet_base = float(outlet.loc[list(BASE_MONTHS)].mean())

    category = frame.groupby("product_category")["revenue"].sum().sort_values(ascending=False)
    top3_share = float(category.head(3).sum() / category.sum())

    aov = (frame.groupby("channel")["revenue"].sum() / frame.groupby("channel").size()).round(4)

    return {
        "total_revenue": metric(total_revenue, "CNY", "SUM(revenue) 全量"),
        "sep_revenue": metric(sep_revenue, "CNY", f"SUM(revenue) WHERE month='{SEP}'"),
        "sep_mom_change": metric(
            (sep_revenue - august_revenue) / august_revenue,
            "ratio",
            f"({SEP} - 2025-08) / 2025-08",
        ),
        "sep_vs_jun_aug_change": metric(
            (sep_revenue - base_revenue) / base_revenue,
            "ratio",
            f"({SEP} - mean(2025-06,2025-07,2025-08)) / 该均值",
        ),
        "dtc_orders_sep_change": metric(
            (dtc_sep_orders - dtc_base_orders) / dtc_base_orders,
            "ratio",
            "DTC 订单行数 9 月 vs 6–8 月均值",
        ),
        "dtc_revenue_sep_change": metric(
            (dtc_sep_revenue - dtc_base_revenue) / dtc_base_revenue,
            "ratio",
            "DTC 销售额 9 月 vs 6–8 月均值",
        ),
        "dtc_decline_contribution": metric(
            (dtc_base_revenue - dtc_sep_revenue) / (base_revenue - sep_revenue),
            "ratio",
            "DTC 降幅 / 总降幅（均为 6–8 月均值 - 9 月）",
        ),
        "home_revenue_change": metric(
            (home_sep_rev - home_base_rev) / home_base_rev,
            "ratio",
            "Home 销售额 9 月 vs 6–8 月均值",
        ),
        "home_gross_profit_change": metric(
            (home_sep_gp - home_base_gp) / home_base_gp,
            "ratio",
            "Home 毛利 9 月 vs 6–8 月均值",
        ),
        "home_gross_margin_sep": metric(home_sep_margin, "ratio", "Home 9 月毛利率 = 毛利/收入"),
        "home_gross_margin_change": metric(
            home_sep_margin - home_base_margin,
            "ratio",
            "Home 毛利率 9 月 - 6–8 月均值（百分点差，以比率计）",
        ),
        "outlet_return_rate_sep": metric(outlet_sep, "ratio", "Outlet 9 月 returns_flag 均值"),
        "outlet_return_rate_base": metric(
            outlet_base, "ratio", "Outlet 6–8 月 returns_flag 均值"
        ),
        "top3_category_share": metric(
            top3_share, "ratio", "收入前 3 品类 revenue 合计 / 全部品类 revenue"
        ),
        "aov_by_channel": {
            "unit": "CNY",
            "method": "SUM(revenue) / 订单行数，按 channel",
            "values": {str(k): float(v) for k, v in aov.items()},
        },
        "null_region_rows": metric(
            float(frame["region"].isna().sum()), "count", "region IS NULL 行数"
        ),
        "duplicate_order_ids": metric(
            float(frame["order_id"].duplicated().sum()), "count", "order_id 重复出现次数"
        ),
        "row_count": metric(float(len(frame)), "count", "全量行数"),
    }


def compute_funnel() -> dict[str, Any]:
    frame = pd.read_csv(FUNNEL)
    conversion = (frame.groupby("channel")["orders"].sum() / frame.groupby("channel")["sessions"].sum())
    return {
        "conversion_by_channel": {
            "unit": "ratio",
            "method": "SUM(orders) / SUM(sessions)，按 channel",
            "values": {str(k): round(float(v), 4) for k, v in conversion.items()},
        },
        "row_count": metric(float(len(frame)), "count", "全量行数"),
        "total_revenue": metric(float(frame["revenue"].sum()), "CNY", "SUM(revenue) 全量"),
        "total_orders": metric(float(frame["orders"].sum()), "count", "SUM(orders) 全量"),
        "total_sessions": metric(float(frame["sessions"].sum()), "count", "SUM(sessions) 全量"),
        "overall_conversion": metric(
            float(frame["orders"].sum() / frame["sessions"].sum()),
            "ratio",
            "SUM(orders) / SUM(sessions) 全量",
        ),
    }


def main() -> None:
    sales = load_sales()
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": str(SALES.relative_to(ROOT)).replace("\\", "/"),
        "sales": compute_sales(sales),
        "funnel": compute_funnel(),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"written: {OUT}")
    for name, item in payload["sales"].items():
        if "value" in item:
            print(f"  {name:32s} {item['value']!s:>18}  {item['unit']}")
        else:
            print(f"  {name:32s} {json.dumps(item['values'], ensure_ascii=False)}")
    for name, item in payload["funnel"].items():
        if "values" in item:
            print(f"  funnel.{name:23s} {json.dumps(item['values'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
