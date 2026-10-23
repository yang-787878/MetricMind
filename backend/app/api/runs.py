"""运行端点（§8）：创建 / 列表 / 详情 / 取消 / 报告。"""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import FileResponse

from ..config import Settings
from ..deps import SettingsDep, StoreDep
from ..errors import AppError, ErrorCode, run_not_found
from ..logging_conf import get_logger
from ..models.enums import TERMINAL_RUN_STATUSES, RunStatus
from ..models.report import ReportModel
from ..models.run import (
    ArtifactInfo,
    Budget,
    CancelResponse,
    CreateRunRequest,
    CreateRunResponse,
    RunDetail,
    RunError,
    RunListResponse,
    RunSummary,
    Usage,
)
from ..runner import get_run_manager
from ..services.exporter import FORMATS, existing_artifact, export_run
from ..services.store import Store, utcnow_iso

router = APIRouter(prefix="/runs", tags=["runs"])
logger = get_logger(__name__)

_rate_buckets: dict[str, deque[float]] = defaultdict(deque)
RATE_WINDOW_S = 60.0


def _check_rate_limit(client_ip: str, limit: int) -> None:
    now = time.monotonic()
    bucket = _rate_buckets[client_ip]
    while bucket and now - bucket[0] > RATE_WINDOW_S:
        bucket.popleft()
    if len(bucket) >= limit:
        retry_after = int(RATE_WINDOW_S - (now - bucket[0])) + 1
        raise AppError(
            ErrorCode.RATE_LIMITED,
            f"请求过于频繁，{RATE_WINDOW_S:.0f}s 内最多 {limit} 次",
            details={"retry_after_s": retry_after},
            hint=f"请 {retry_after}s 后重试",
            http_status=429,
        )
    bucket.append(now)


def _load_json(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def _duration_ms(row: dict[str, Any]) -> int | None:
    from datetime import datetime

    started = row.get("started_at") or row.get("created_at")
    finished = row.get("finished_at") or utcnow_iso()
    if not started:
        return None
    try:
        begin = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
    except ValueError:  # pragma: no cover
        return None
    return max(int((end - begin).total_seconds() * 1000), 0)


def build_run_detail(row: dict[str, Any], settings: Settings) -> RunDetail:
    state = _load_json(row.get("state_json")) or {}
    usage = _load_json(row.get("usage_json")) or {}
    error = _load_json(row.get("error_json"))
    verification = _load_json(row.get("verification_json"))
    plan = _load_json(row.get("plan_json"))
    report = _load_json(row.get("report_json"))
    steps = state.get("steps") if isinstance(state, dict) else None

    return RunDetail(
        run_id=row["run_id"],
        dataset_id=row["dataset_id"],
        dataset_name=row.get("dataset_name"),
        question=row["question"],
        status=RunStatus(row["status"]),
        mode=row["mode"],
        model=row.get("model"),
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        duration_ms=_duration_ms(row),
        usage=Usage.model_validate(usage) if usage else Usage(),
        budget=Budget(
            max_steps=settings.max_steps,
            max_tool_calls=settings.max_tool_calls,
            max_replans=settings.max_replans,
            timeout_seconds=settings.run_timeout_s,
        ),
        plan=plan,
        steps=steps or [],
        verification=verification,
        report=report,
        error=RunError.model_validate(error) if isinstance(error, dict) and error.get("message") else None,
        warnings=list(state.get("warnings") or []) if isinstance(state, dict) else [],
    )


@router.post(
    "",
    response_model=CreateRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建一次分析运行",
)
async def create_run(
    payload: CreateRunRequest,
    request: Request,
    settings: SettingsDep,
    store: StoreDep,
) -> CreateRunResponse:
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip, settings.rate_limit_per_minute)
    manager = get_run_manager(settings)
    result = await manager.create_run(
        dataset_id=payload.dataset_id,
        question=payload.question,
        requested=payload.mode,
    )
    return CreateRunResponse(**result)


@router.get("", response_model=RunListResponse, summary="运行列表")
def list_runs(
    settings: SettingsDep,
    store: StoreDep,
    dataset_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
) -> RunListResponse:
    rows, total = store.list_runs(dataset_id=dataset_id, status=status_filter, limit=limit)
    items = [
        RunSummary(
            run_id=row["run_id"],
            dataset_id=row["dataset_id"],
            dataset_name=row.get("dataset_name"),
            question=row["question"],
            status=RunStatus(row["status"]),
            mode=row["mode"],
            model=row.get("model"),
            created_at=row["created_at"],
            started_at=row.get("started_at"),
            finished_at=row.get("finished_at"),
            duration_ms=_duration_ms(row) if row.get("finished_at") else None,
        )
        for row in rows
    ]
    return RunListResponse(items=items, total=total)


@router.get("/{run_id}", response_model=RunDetail, summary="运行详情（轮询兜底）")
def get_run(run_id: str, settings: SettingsDep, store: StoreDep) -> RunDetail:
    row = store.get_run(run_id)
    if row is None:
        raise run_not_found(run_id)
    dataset = store.get_dataset(row["dataset_id"])
    row["dataset_name"] = dataset["name"] if dataset else None
    return build_run_detail(row, settings)


@router.post("/{run_id}/cancel", response_model=CancelResponse, status_code=202, summary="取消运行")
async def cancel_run(run_id: str, settings: SettingsDep) -> CancelResponse:
    manager = get_run_manager(settings)
    state_value = await manager.cancel(run_id)
    return CancelResponse(status=state_value, run_id=run_id)


@router.get("/{run_id}/report", response_model=ReportModel, summary="报告模型")
def get_report(run_id: str, settings: SettingsDep, store: StoreDep) -> ReportModel:
    row = store.get_run(run_id)
    if row is None:
        raise run_not_found(run_id)
    if row["status"] in {RunStatus.QUEUED.value, RunStatus.RUNNING.value}:
        raise AppError(
            ErrorCode.REPORT_NOT_READY,
            "报告尚未生成",
            details={"status": row["status"]},
            hint="请等待运行结束",
        )
    report = _load_json(row.get("report_json"))
    if not report:
        raise AppError(
            ErrorCode.REPORT_NOT_READY,
            "本次运行没有产出报告",
            details={"status": row["status"]},
            hint="请查看运行错误详情后重试",
        )
    return ReportModel.model_validate(report)


@router.get("/{run_id}/export", summary="下载报告（html / md）")
def export_report_file(
    run_id: str,
    settings: SettingsDep,
    store: StoreDep,
    fmt: str = Query(default="html", alias="format"),
) -> FileResponse:
    row = store.get_run(run_id)
    if row is None:
        raise run_not_found(run_id)
    if fmt not in FORMATS:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"不支持的导出格式 {fmt}",
            details={"available": sorted(FORMATS)},
            hint="format 只支持 html 或 md",
        )

    artifact = existing_artifact(store, run_id, fmt)
    if artifact is None:
        stored_report = _load_json(row.get("report_json"))
        if not stored_report:
            raise AppError(
                ErrorCode.REPORT_NOT_READY,
                "本次运行没有产出报告，无法导出",
                details={"status": row["status"]},
            )
        dataset = store.get_dataset(row["dataset_id"])
        result = export_run(
            store=store,
            settings=settings,
            run_id=run_id,
            report=ReportModel.model_validate(stored_report),
            fmt=fmt,
            dataset_name=dataset["name"] if dataset else None,
        )
        path = Path(result["path"])
    else:
        path = Path(artifact["path"])

    extension, media_type = FORMATS[fmt]
    return FileResponse(
        path,
        media_type=media_type,
        filename=f"metricmind-{run_id}.{extension}",
    )


@router.get("/{run_id}/artifacts", summary="导出产物列表")
def list_artifacts(run_id: str, settings: SettingsDep, store: StoreDep) -> dict[str, Any]:
    row = store.get_run(run_id)
    if row is None:
        raise run_not_found(run_id)
    items = [
        ArtifactInfo(
            artifact_id=item["artifact_id"],
            run_id=item["run_id"],
            kind=item["kind"],
            format=item["format"],
            size_bytes=item["size_bytes"],
            download_url=f"{settings.api_prefix}/runs/{run_id}/export?format={item['format']}",
            created_at=item["created_at"],
        )
        for item in store.list_artifacts(run_id)
    ]
    return {"items": [item.model_dump(mode="json") for item in items], "total": len(items)}
