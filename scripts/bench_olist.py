"""Measure MetricMind ingest cost on the Olist sample table.

Runs the real DatasetLoader (same code path as an upload) against a throwaway
data directory, so numbers are comparable to a first-time upload.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import pandas as pd  # noqa: E402

from app.config import Settings  # noqa: E402
from app.services.loader import DatasetLoader, profile_frame  # noqa: E402
from app.services.store import Store  # noqa: E402

CSV = Path(__file__).resolve().parents[1] / "data" / "sample_olist_orders.csv"


def main() -> None:
    payload = CSV.read_bytes()
    result: dict[str, object] = {"file_mb": round(len(payload) / 1024 / 1024, 2)}

    bench = Path(r"D:\work\bench_olist")
    settings = Settings(data_dir=str(bench), db_path=str(bench / "mm.db"))
    settings.ensure_dirs()
    store = Store(settings.db_file)
    store.init_schema()
    loader = DatasetLoader(store, settings)

    t0 = time.perf_counter()
    row = loader.create_from_upload(CSV.name, payload)
    result["ingest_s"] = round(time.perf_counter() - t0, 2)

    frame = pd.read_csv(CSV, encoding="utf-8")
    t0 = time.perf_counter()
    profile = profile_frame(frame)
    result["profile_s"] = round(time.perf_counter() - t0, 2)

    result.update(
        rows=row["row_count"],
        cols=row["column_count"],
        issues=len(profile["issues"]),
        issue_codes=sorted({i["code"] for i in profile["issues"]}),
    )

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()



