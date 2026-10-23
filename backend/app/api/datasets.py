"""数据集端点（§8）：上传、示例、列表、详情、预览、删除。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile, status

from ..deps import SettingsDep, StoreDep
from ..errors import AppError, ErrorCode, dataset_not_found
from ..logging_conf import get_logger
from ..models.dataset import (
    DatasetDetail,
    DatasetListResponse,
    DatasetPreview,
    DatasetSummary,
    SampleDatasetResponse,
)
from ..services.loader import DatasetLoader

router = APIRouter(prefix="/datasets", tags=["datasets"])
logger = get_logger(__name__)

MAX_PREVIEW_ROWS = 100


def _loader(settings: SettingsDep, store: StoreDep) -> DatasetLoader:
    return DatasetLoader(store, settings)


def _summary(row: dict) -> DatasetSummary:
    return DatasetSummary(
        dataset_id=row["dataset_id"],
        name=row["name"],
        original_filename=row["original_filename"],
        source=row["source"],
        row_count=row["row_count"],
        column_count=row["column_count"],
        size_bytes=row["size_bytes"],
        created_at=row["created_at"],
        checksum=row["checksum"],
    )


def _detail(loader: DatasetLoader, row: dict, reused: bool = False) -> DatasetDetail:
    return DatasetDetail.model_validate({**loader.dataset_detail(row), "reused": reused})


@router.post("", response_model=DatasetDetail, status_code=status.HTTP_201_CREATED, summary="上传数据集")
async def upload_dataset(
    settings: SettingsDep,
    store: StoreDep,
    file: UploadFile = File(..., description="CSV 或 XLSX 文件"),
) -> DatasetDetail:
    content = await file.read()
    loader = _loader(settings, store)
    row = await asyncio.to_thread(
        loader.create_from_upload, file.filename or "upload.csv", content
    )
    return _detail(loader, row)


@router.post(
    "/samples/{key}",
    response_model=SampleDatasetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="载入内置示例数据（幂等）",
)
async def load_sample(key: str, settings: SettingsDep, store: StoreDep) -> SampleDatasetResponse:
    loader = _loader(settings, store)
    row, reused = await asyncio.to_thread(loader.create_from_sample, key)
    detail = _detail(loader, row, reused)
    return SampleDatasetResponse(**{**detail.model_dump(exclude={"reused"}), "reused": reused})


@router.get("", response_model=DatasetListResponse, summary="数据集列表")
def list_datasets(
    settings: SettingsDep,
    store: StoreDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DatasetListResponse:
    rows, total = store.list_datasets(limit=limit, offset=offset)
    return DatasetListResponse(items=[_summary(row) for row in rows], total=total)


@router.get("/{dataset_id}", response_model=DatasetDetail, summary="数据集详情")
def get_dataset(dataset_id: str, settings: SettingsDep, store: StoreDep) -> DatasetDetail:
    row = store.get_dataset(dataset_id)
    if row is None:
        raise dataset_not_found(dataset_id)
    return _detail(_loader(settings, store), row)


@router.get("/{dataset_id}/preview", response_model=DatasetPreview, summary="数据预览")
async def preview_dataset(
    dataset_id: str,
    settings: SettingsDep,
    store: StoreDep,
    limit: int = Query(default=50, ge=1, le=MAX_PREVIEW_ROWS),
) -> DatasetPreview:
    row = store.get_dataset(dataset_id)
    if row is None:
        raise dataset_not_found(dataset_id)
    loader = _loader(settings, store)
    payload = await asyncio.to_thread(loader.preview, row, limit)
    return DatasetPreview.model_validate(payload)


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除数据集")
async def delete_dataset(dataset_id: str, settings: SettingsDep, store: StoreDep) -> None:
    row = store.get_dataset(dataset_id)
    if row is None:
        raise dataset_not_found(dataset_id)
    runs = store.count_dataset_runs(dataset_id)
    if runs:
        raise AppError(
            ErrorCode.DATASET_IN_USE,
            f"数据集仍被 {runs} 个分析运行引用，无法删除",
            details={"dataset_id": dataset_id, "run_count": runs},
            hint="历史报告依赖该数据集，请先保留或导出报告",
        )
    store.delete_dataset(dataset_id)
    stored_path = Path(row["stored_path"])
    stored_path.unlink(missing_ok=True)
    logger.info("dataset_deleted", extra={"dataset_id": dataset_id})
