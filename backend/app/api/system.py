"""系统自检端点：/api/health 与 /api/config（§8）。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter

from ..deps import SettingsDep, StoreDep
from ..logging_conf import get_logger
from ..models.run import ConfigResponse, HealthResponse, Limits

router = APIRouter(tags=["system"])
logger = get_logger(__name__)


def load_samples(settings: SettingsDep) -> list[dict[str, Any]]:
    """读取 data/samples.json。文件尚未生成时返回空列表——不编造示例数据。"""
    path = settings.samples_registry
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("samples_registry_unreadable", extra={"error": str(exc)})
        return []
    samples = payload.get("samples", payload) if isinstance(payload, dict) else payload
    return samples if isinstance(samples, list) else []


@router.get("/health", response_model=HealthResponse, summary="启动自检")
def health(settings: SettingsDep, store: StoreDep) -> HealthResponse:
    db_ok = store.ping()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version=settings.version,
        db="ok" if db_ok else "error",
        llm_mode=settings.resolved_llm_mode,
        model=settings.llm_model,
    )


@router.get("/config", response_model=ConfigResponse, summary="限额与示例数据入口")
def config(settings: SettingsDep) -> ConfigResponse:
    return ConfigResponse(
        llm_mode=settings.resolved_llm_mode,
        model=settings.llm_model,
        limits=Limits(
            max_upload_mb=settings.max_upload_mb,
            max_rows=settings.max_rows,
            max_steps=settings.max_steps,
            max_tool_calls=settings.max_tool_calls,
            max_replans=settings.max_replans,
            run_timeout_s=settings.run_timeout_s,
        ),
        samples=load_samples(settings),
    )
