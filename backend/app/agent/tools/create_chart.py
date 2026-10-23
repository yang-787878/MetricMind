"""create_chart（§5.2(5)）：只接受 result_id，数据来自证据池，模型无法凭空造数。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ...errors import result_not_found
from ...models.enums import ChartType
from ...models.tool import ToolEnvelope, ToolMeta
from ...services.charts import build_chart_spec
from ..context import ToolContext

NAME = "create_chart"
DESCRIPTION = (
    "基于已有结果集（result_id）生成图表规格 ChartSpec。必须指定该结果集中真实存在的 x/y 列，"
    "可选 series 分组。不接受任何外部数据数组——这是'图表必须基于真实数据'的代码级保证。"
)
TIMEOUT_S = 15.0
MAX_CALLS = 5


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_result_id: str = Field(min_length=1)
    type: ChartType
    x: str = Field(min_length=1)
    y: str = Field(min_length=1)
    series: str | None = None
    title: str = Field(min_length=1, max_length=80)
    subtitle: str | None = Field(default=None, max_length=200)
    unit: str | None = Field(default=None, max_length=20)
    sort_by: Literal["x_asc", "x_desc", "y_asc", "y_desc"] | None = None
    limit_points: int = Field(default=200, ge=1, le=500)


async def run(ctx: ToolContext, args: Input) -> ToolEnvelope:
    payload = ctx.evidence.get(args.from_result_id)
    if payload is None:
        raise result_not_found(args.from_result_id)

    spec = build_chart_spec(
        result_id=args.from_result_id,
        payload=payload,
        chart_type=args.type,
        x=args.x,
        y=args.y,
        series=args.series,
        title=args.title,
        subtitle=args.subtitle,
        unit=args.unit,
        sort_by=args.sort_by,
        limit_points=args.limit_points,
    )
    return ToolEnvelope.success(
        tool=NAME,
        data=spec.model_dump(mode="json"),
        meta=ToolMeta(
            tool=NAME,
            rows_returned=len(spec.data),
            truncated=bool(spec.source.truncated),
            warnings=list(spec.notes),
        ),
    )
