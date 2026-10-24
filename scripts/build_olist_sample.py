"""Build the Olist sample table used by MetricMind.

Source: Olist Brazilian E-Commerce Public Dataset (Kaggle, CC BY-NC-SA 4.0),
mirrored on HuggingFace as `bulutttt/olist-raw-data`. Raw CSVs live in
`data/olist_raw/` and are not vendored into git (they are large); this script
turns them into one analysis-ready table at order-item grain.

输出：data/sample_olist_orders.csv
  - 约 11 万行、15 列、~14MB，落在单表 20 万行 / 60 列 / 25MB 的限制内
  - 列名英文，便于通用 SQL；描述与推荐问题用中文写在 samples.json
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "olist_raw"
OUT = ROOT / "data" / "sample_olist_orders.csv"
TRANS_URL = (
    "https://huggingface.co/datasets/bulutttt/olist-raw-data/resolve/main/"
    "product_category_name_translation.csv"
)


def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(RAW / name, encoding="utf-8")


def build() -> pd.DataFrame:
    orders = _read("olist_orders_dataset.csv")
    items = _read("olist_order_items_dataset.csv")
    products = _read("olist_products_dataset.csv")
    payments = _read("olist_order_payments_dataset.csv")
    customers = _read("olist_customers_dataset.csv")

    trans_path = RAW / "product_category_name_translation.csv"
    if not trans_path.exists():
        urllib.request.urlretrieve(TRANS_URL, trans_path)
    trans = pd.read_csv(trans_path, encoding="utf-8")

    for col in (
        "order_purchase_timestamp",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ):
        orders[col] = pd.to_datetime(orders[col], errors="coerce")

    pay = (
        payments.groupby("order_id")
        .agg(
            payment_value=("payment_value", "sum"),
            payment_installments=("payment_installments", "max"),
        )
        .reset_index()
    )
    pay_type = (
        payments.sort_values("payment_sequential")
        .groupby("order_id")["payment_type"]
        .first()
        .reset_index()
    )
    pay = pay.merge(pay_type, on="order_id", how="left")

    prod = products[["product_id", "product_category_name"]].merge(
        trans, on="product_category_name", how="left"
    )
    prod["product_category"] = (
        prod["product_category_name_english"]
        .fillna(prod["product_category_name"])
        .fillna("unknown")
    )

    df = (
        items.merge(orders, on="order_id", how="inner")
        .merge(prod[["product_id", "product_category"]], on="product_id", how="left")
        .merge(
            customers[["customer_id", "customer_state", "customer_city"]],
            on="customer_id",
            how="left",
        )
        .merge(pay, on="order_id", how="left")
    )

    df["order_date"] = df["order_purchase_timestamp"].dt.date
    df["order_month"] = df["order_purchase_timestamp"].dt.strftime("%Y-%m")
    df["delivery_days"] = (
        df["order_delivered_customer_date"] - df["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400
    late = df["order_delivered_customer_date"] > df["order_estimated_delivery_date"]
    df["is_late"] = late.astype("Int64").mask(
        df["order_delivered_customer_date"].isna()
    )
    df["item_total"] = df["price"] + df["freight_value"]

    out = df[
        [
            "order_id",
            "order_item_id",
            "order_date",
            "order_month",
            "order_status",
            "customer_state",
            "customer_city",
            "product_category",
            "price",
            "freight_value",
            "item_total",
            "payment_value",
            "payment_type",
            "delivery_days",
            "is_late",
        ]
    ].rename(columns={"order_item_id": "item_id"})

    out["price"] = out["price"].round(2)
    out["freight_value"] = out["freight_value"].round(2)
    out["item_total"] = out["item_total"].round(2)
    out["payment_value"] = out["payment_value"].round(2)
    out["delivery_days"] = out["delivery_days"].round(1)
    out["customer_city"] = out["customer_city"].str.replace("_", " ", regex=False)
    out["product_category"] = out["product_category"].str.replace("_", " ", regex=False)
    return out.sort_values(["order_date", "order_id", "item_id"]).reset_index(drop=True)


if __name__ == "__main__":
    frame = build()
    frame.to_csv(OUT, index=False, encoding="utf-8")
    size_mb = OUT.stat().st_size / 1024 / 1024
    print(f"rows={len(frame)} cols={len(frame.columns)} size={size_mb:.2f}MB")
    print(f"date range: {frame.order_date.min()} -> {frame.order_date.max()}")
    print(f"revenue={frame.item_total.sum():,.2f} orders={frame.order_id.nunique():,}")
    print(frame.head(3).to_string())

