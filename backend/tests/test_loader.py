"""数据接入单测（§10.1）：编码探测、超限、空文件、重复列名、扩展名、xlsx、语义类型。"""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.services.loader import DatasetLoader, infer_semantic_type, normalize_columns


def _settings(work_root, **overrides) -> Settings:
    cfg = Settings(
        data_dir=str(work_root / "data2"),
        db_path=str(work_root / "data2" / "metricmind.db"),
        llm_mode="demo",
        **overrides,
    )
    cfg.ensure_dirs()
    return cfg


def _csv(rows: list[dict[str, object]]) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")


def test_upload_csv_success(loader, dataset_row) -> None:
    detail = loader.dataset_detail(dataset_row)
    assert detail["row_count"] == 60
    assert detail["column_count"] == 9
    assert detail["source"] == "upload"
    assert detail["checksum"].startswith("sha256:")
    names = [column["name"] for column in detail["columns"]]
    assert "order_date" in names


def test_semantic_types(loader, dataset_row) -> None:
    detail = loader.dataset_detail(dataset_row)
    kinds = {column["name"]: column["semantic_type"] for column in detail["columns"]}
    assert kinds["order_id"] == "identifier"
    assert kinds["order_date"] == "temporal"
    assert kinds["channel"] == "categorical"
    assert kinds["revenue"] == "numeric"
    assert kinds["returns_flag"] == "numeric" or kinds["returns_flag"] == "boolean"


def test_rejects_unsupported_extension(loader) -> None:
    with pytest.raises(AppError) as info:
        loader.create_from_upload("notes.txt", b"a,b\n1,2\n")
    assert info.value.code == ErrorCode.UNSUPPORTED_FILE_TYPE.value


def test_rejects_empty_file(loader) -> None:
    with pytest.raises(AppError) as info:
        loader.create_from_upload("empty.csv", b"")
    assert info.value.code == ErrorCode.INVALID_DATASET.value


def test_rejects_header_only_file(loader) -> None:
    with pytest.raises(AppError) as info:
        loader.create_from_upload("header.csv", b"a,b,c\n")
    assert info.value.code == ErrorCode.INVALID_DATASET.value


def test_rejects_duplicate_headers(loader) -> None:
    with pytest.raises(AppError) as info:
        loader.create_from_upload("dup.csv", b"revenue,revenue\n1,2\n")
    assert info.value.code == ErrorCode.INVALID_DATASET.value
    assert "revenue" in info.value.message


def test_rejects_file_too_large(work_root, store) -> None:
    cfg = _settings(work_root, max_upload_mb=1)
    loader = DatasetLoader(store, cfg)
    payload = b"a,b\n" + b"1,2\n" * 400_000
    with pytest.raises(AppError) as info:
        loader.create_from_upload("big.csv", payload)
    assert info.value.code == ErrorCode.FILE_TOO_LARGE.value


def test_rejects_too_many_rows(work_root, store) -> None:
    cfg = _settings(work_root, max_rows=10)
    loader = DatasetLoader(store, cfg)
    payload = _csv([{"a": i, "b": i * 2} for i in range(30)])
    with pytest.raises(AppError) as info:
        loader.create_from_upload("many.csv", payload)
    assert info.value.code == ErrorCode.DATASET_TOO_LARGE.value


def test_detects_gb18030_encoding(loader) -> None:
    payload = "订单编号,金额\nA001,100\nA002,250\n".encode("gb18030")
    row = loader.create_from_upload("gb.csv", payload)
    assert row["encoding"] in {"gb18030", "latin-1"}
    detail = loader.dataset_detail(row)
    assert "订单编号" in [column["original_name"] for column in detail["columns"]]


def test_parses_xlsx(loader) -> None:
    buffer = io.BytesIO()
    pd.DataFrame({"region": ["North", "South"], "revenue": [10.0, 20.5]}).to_excel(
        buffer, index=False
    )
    row = loader.create_from_upload("book.xlsx", buffer.getvalue())
    assert row["row_count"] == 2
    detail = loader.dataset_detail(row)
    assert [column["name"] for column in detail["columns"]] == ["region", "revenue"]


def test_column_normalization() -> None:
    normalized, originals = normalize_columns(["Order ID", "金额（元）", "", "Order_ID", "金额(元)"])
    assert normalized[0] == "Order_ID"
    assert normalized[1] == "金额_元"
    assert normalized[2] == "col_2"
    assert normalized[3] == "Order_ID_2"
    assert originals["金额_元"] == "金额（元）"


def test_infer_semantic_type_rules() -> None:
    assert infer_semantic_type("order_id", pd.Series([f"o{i}" for i in range(30)])) == "identifier"
    assert (
        infer_semantic_type("created_at", pd.Series([f"2025-01-{i % 28 + 1:02d}" for i in range(30)]))
        == "temporal"
    )
    assert infer_semantic_type("channel", pd.Series(["DTC", "Outlet"] * 15)) == "categorical"
    assert infer_semantic_type("revenue", pd.Series([1.5, 2.5, 3.5])) == "numeric"
    assert infer_semantic_type("paid", pd.Series([1, 2, 3, 4, 5])) == "numeric"


def test_quality_issues_reported(loader) -> None:
    rows = [
        {
            "order_date": "2025-01-01",
            "region": None,
            "order_id": "o1",
            "unit_price": 0,
            "amount": 100,
        },
        {
            "order_date": "2025-01-01",
            "region": None,
            "order_id": "o1",
            "unit_price": 0,
            "amount": 100,
        },
        {
            "order_date": "2025-01-02",
            "region": None,
            "order_id": "o2",
            "unit_price": 0,
            "amount": 100,
        },
        {
            "order_date": "2025-01-03",
            "region": "North",
            "order_id": "o3",
            "unit_price": 10,
            "amount": 100,
        },
        {
            "order_date": "not-a-date",
            "region": "South",
            "order_id": "o4",
            "unit_price": 10,
            "amount": 100,
        },
    ]
    row = loader.create_from_upload("issues.csv", _csv(rows))
    detail = loader.dataset_detail(row)
    codes = {issue["code"] for issue in detail["quality"]["issues"]}
    assert "NULL_VALUES" in codes
    assert "DUPLICATE_ROWS" in codes
    assert "ZERO_OR_NEGATIVE" in codes
    assert detail["quality"]["duplicate_row_count"] >= 1
