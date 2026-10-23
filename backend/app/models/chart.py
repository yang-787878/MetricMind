"""ChartSpec：后端是图表数据的唯一来源，前端只负责把 data 渲染成图形（§4.2）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import ChartType, SemanticType

__all__ = ["ChartType", "ChartAxis", "ChartSeriesRef", "ChartSource", "ChartSpec"]


class ChartAxis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    type: SemanticType


class ChartSeriesRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str


class ChartSource(BaseModel):
    """证据链锚点：图表必须能回溯到某个真实工具结果集。"""

    model_config = ConfigDict(extra="forbid")

    result_id: str
    tool: str
    step_id: str | None = None
    row_count: int = 0
    truncated: bool = False


class ChartSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chart_id: str
    type: ChartType
    title: str = Field(max_length=120)
    subtitle: str | None = None
    unit: str | None = None
    x: ChartAxis
    y: ChartAxis
    series: ChartSeriesRef | None = None
    data: list[dict[str, Any]] = Field(default_factory=list)
    source: ChartSource
    notes: list[str] = Field(default_factory=list)
