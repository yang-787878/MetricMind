"""export_report（§5.2(7)）：把已完成 run 的报告导出为自包含 HTML / Markdown。"""

from __future__ import annotations

import asyncio
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ...errors import AppError, ErrorCode
from ...models.report import ReportModel
from ...models.tool import ToolEnvelope, ToolMeta
from ...services.exporter import export_run
from ..context import ToolContext

NAME = "export_report"
DESCRIPTION = (
    "把当前运行已生成的报告导出为文件：html = 完全自包含单文件（内联 CSS + 内联 SVG，无外链无 JS），"
    "md = GFM 表格版（图表以数据表呈现）。返回 artifact_id 与下载地址。只在运行结束后可用。"
)
TIMEOUT_S = 20.0
MAX_CALLS = 2
PRODUCES_RESULT = False
PLANNER_VISIBLE = False


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    format: Literal["html", "md"]


async def run(ctx: ToolContext, args: Input) -> ToolEnvelope:
    if args.run_id != ctx.run_id:
        raise AppError(
            ErrorCode.RUN_NOT_FOUND,
            f"运行 {args.run_id} 与当前 run 不一致",
            details={"run_id": args.run_id, "current_run_id": ctx.run_id},
        )
    row = await asyncio.to_thread(ctx.store.get_run, ctx.run_id)
    if row is None:
        raise AppError(ErrorCode.RUN_NOT_FOUND, "运行不存在", details={"run_id": ctx.run_id})
    if not row.get("report_json"):
        raise AppError(
            ErrorCode.REPORT_NOT_READY,
            "报告尚未生成，无法导出",
            details={"status": row.get("status")},
            hint="请等待运行结束后再导出",
        )

    report = ReportModel.model_validate(json.loads(row["report_json"]))
    dataset = await asyncio.to_thread(ctx.store.get_dataset, row["dataset_id"])
    result = await asyncio.to_thread(
        export_run,
        store=ctx.store,
        settings=ctx.settings,
        run_id=ctx.run_id,
        report=report,
        fmt=args.format,
        dataset_name=dataset["name"] if dataset else None,
    )
    data = {
        "artifact_id": result["artifact_id"],
        "format": result["format"],
        "size_bytes": result["size_bytes"],
        "download_url": result["download_url"],
        "generated_at": result["generated_at"],
    }
    return ToolEnvelope.success(
        tool=NAME,
        data=data,
        meta=ToolMeta(tool=NAME, rows_returned=result["chart_count"]),
    )
