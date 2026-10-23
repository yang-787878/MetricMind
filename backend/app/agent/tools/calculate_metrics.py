"""calculate_metrics（§5.2(4)）：把结构化指标定义交给 metrics.py 确定性计算。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ...models.tool import ToolEnvelope, ToolMeta
from ...services.metrics import MetricSpec, compute_metrics
from ..context import ToolContext

NAME = "calculate_metrics"
DESCRIPTION = (
    "按结构化定义计算指标：sum/mean/median/count/count_distinct/min/max/ratio/share/rate/"
    "growth_rate，支持 filters、group_by/period（真实列名或 day/week/month 周期）、sort、limit。"
    "limit 可写在顶层（对所有未单独设置 limit 的指标生效）或每个 metric 内。"
    "所有算法在服务端确定性执行，除零返回 null 并附 warning。"
)
TIMEOUT_S = 25.0
MAX_CALLS = 8


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    metrics: list[MetricSpec] = Field(min_length=1, max_length=6)
    # 兼容模型把 limit 写在调用层：作为所有指标的统一默认条数上限
    limit: int | None = Field(default=None, ge=1, le=500)


async def run(ctx: ToolContext, args: Input) -> ToolEnvelope:
    frame = await ctx.frame(args.dataset_id)
    metrics = args.metrics
    if args.limit is not None:
        metrics = [
            metric if metric.limit is not None else metric.model_copy(update={"limit": args.limit})
            for metric in metrics
        ]
    result = compute_metrics(frame, metrics)
    warnings: list[str] = []
    for metric in result["metrics"]:
        for warning in metric.get("warnings") or []:
            warnings.append(f"{metric['name']}: {warning}")
    rows = sum(len(metric.get("groups") or []) for metric in result["metrics"])
    return ToolEnvelope.success(
        tool=NAME,
        data=result,
        meta=ToolMeta(tool=NAME, rows_returned=rows or len(result["metrics"]), warnings=warnings),
    )
