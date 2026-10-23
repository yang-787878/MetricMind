"""inspect_dataset（§5.2(1)）：鲁棒的字段探查，必须真的读数据。"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from ...models.tool import ToolEnvelope, ToolMeta
from ..context import ToolContext

NAME = "inspect_dataset"
DESCRIPTION = (
    "读取数据集结构：每列的 dtype/语义类型/缺失率/唯一值/样例值，行数列数，时间范围，"
    "以及候选指标列、候选维度列、候选时间列。用于在规划前确认真实字段。"
)
TIMEOUT_S = 20.0
MAX_CALLS = 2


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    sample_rows: int = Field(default=3, ge=0, le=5)


def _time_range(frame: pd.DataFrame, column: str) -> dict[str, Any] | None:
    parsed = pd.to_datetime(frame[column], errors="coerce")
    valid = parsed.dropna()
    if valid.empty:
        return None
    return {
        "column": column,
        "min": valid.min().isoformat(),
        "max": valid.max().isoformat(),
    }


async def run(ctx: ToolContext, args: Input) -> ToolEnvelope:
    row = await ctx.dataset_row(args.dataset_id)
    frame = await ctx.frame(args.dataset_id)
    schema: list[dict[str, Any]] = json.loads(row["schema_json"])

    columns: list[dict[str, Any]] = []
    for column in schema:
        samples = [] if args.sample_rows == 0 else list(column.get("sample_values") or [])[: args.sample_rows]
        columns.append(
            {
                "name": column["name"],
                "dtype": column["dtype"],
                "semantic_type": column["semantic_type"],
                "null_rate": column["null_rate"],
                "distinct_count": column["distinct_count"],
                "sample_values": samples,
            }
        )

    warnings: list[str] = []
    date_columns = [c for c in schema if c["semantic_type"] == "temporal"]
    time_range = None
    if date_columns:
        time_range = _time_range(frame, date_columns[0]["name"])
        if time_range is None:
            warnings.append(f"时间列 {date_columns[0]['name']} 存在但无法解析为日期")
    else:
        warnings.append("未识别到可解析的时间列，无法计算趋势与环比")

    candidate_metrics = [c["name"] for c in schema if c["semantic_type"] == "numeric"]
    candidate_dimensions = [
        c["name"]
        for c in schema
        if c["semantic_type"] in {"categorical", "boolean"} and 1 < int(c["distinct_count"]) <= 50
    ]

    data = {
        "columns": columns,
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "time_range": time_range,
        "candidate_metrics": candidate_metrics,
        "candidate_dimensions": candidate_dimensions,
        "candidate_date_column": time_range["column"] if time_range else None,
    }
    return ToolEnvelope.success(
        tool=NAME,
        data=data,
        meta=ToolMeta(tool=NAME, rows_returned=len(frame), warnings=warnings),
    )
