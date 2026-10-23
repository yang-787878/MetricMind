"""数据集领域模型（§4.2 Dataset / §8 上传校验产物）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import IssueSeverity, SemanticType, SourceKind

__all__ = [
    "SemanticType",
    "ColumnStats",
    "ColumnProfile",
    "QualityIssue",
    "DatasetQuality",
    "DatasetSummary",
    "DatasetDetail",
    "DatasetPreview",
    "SampleDataset",
]


class ColumnStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: float | None = None
    max: float | None = None
    mean: float | None = None
    median: float | None = None


class ColumnProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    original_name: str | None = None
    dtype: str
    semantic_type: SemanticType
    null_rate: float = Field(ge=0.0, le=1.0)
    distinct_count: int = Field(ge=0)
    sample_values: list[Any] = Field(default_factory=list, max_length=5)
    stats: ColumnStats | None = None


class QualityIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    column: str | None = None
    severity: IssueSeverity = IssueSeverity.WARNING
    message: str
    affected_rows: int | None = None


class DatasetQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duplicate_row_count: int = 0
    row_count_after_dedup: int = 0
    issues: list[QualityIssue] = Field(default_factory=list)


class DatasetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    name: str
    original_filename: str
    source: SourceKind
    row_count: int
    column_count: int
    size_bytes: int
    created_at: datetime
    checksum: str | None = None


class DatasetDetail(DatasetSummary):
    columns: list[ColumnProfile] = Field(default_factory=list)
    quality: DatasetQuality = Field(default_factory=DatasetQuality)
    encoding: str | None = None
    reused: bool = False


class SampleDatasetResponse(DatasetDetail):
    """示例数据入口的响应：reused 表示命中了同名/同内容数据集（幂等）。"""

    reused: bool = False


class DatasetPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[dict[str, str]]
    rows: list[list[Any]]
    total_rows: int


class SampleDataset(BaseModel):
    """data/samples.json 的一项：给前端渲染示例入口与推荐问题。"""

    model_config = ConfigDict(extra="forbid")

    key: str
    name: str
    description: str
    filename: str
    row_count: int | None = None
    recommended_questions: list[str] = Field(default_factory=list)


class DatasetListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DatasetSummary]
    total: int
