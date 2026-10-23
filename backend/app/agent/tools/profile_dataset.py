"""profile_dataset（§5.2(2)）：与 loader 共用 profile_frame，保证口径一致。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ...models.tool import ToolEnvelope, ToolMeta
from ...services.loader import profile_frame
from ..context import ToolContext

NAME = "profile_dataset"
DESCRIPTION = (
    "对数据集做质量剖析：行数、重复行、每列空值/唯一值/极值/均值/中位数/P95/零值/负值/异常值，"
    "以及固定错误码集合的质量问题清单（NULL_VALUES / DUPLICATE_ROWS / OUTLIERS_IQR 等）。"
)
TIMEOUT_S = 25.0
MAX_CALLS = 2


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    columns: list[str] | None = None
    include_outliers: bool = True


async def run(ctx: ToolContext, args: Input) -> ToolEnvelope:
    frame = await ctx.frame(args.dataset_id)
    if args.columns:
        missing = [name for name in args.columns if name not in frame.columns]
        if missing:
            return ToolEnvelope.failure(
                tool=NAME,
                code="INVALID_COLUMN",
                message=f"列不存在：{missing}",
                hint="请从 inspect_dataset 返回的字段中选列",
            )
    profile = profile_frame(frame, args.columns, args.include_outliers)
    return ToolEnvelope.success(
        tool=NAME,
        data=profile,
        meta=ToolMeta(
            tool=NAME,
            rows_returned=profile["row_count"],
            warnings=[f"共 {len(profile['issues'])} 个质量问题"] if profile["issues"] else [],
        ),
    )
