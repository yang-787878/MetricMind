"""事件端点（§6.5）：SSE 实时流 + after_seq 续播 + 轮询兜底。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse

from ..deps import StoreDep
from ..errors import run_not_found
from ..logging_conf import get_logger
from ..models.enums import TERMINAL_RUN_STATUSES
from ..models.events import Event
from ..services.event_bus import bus

router = APIRouter(prefix="/runs", tags=["events"])
logger = get_logger(__name__)

TERMINAL_EVENTS = {"run_succeeded", "run_failed", "run_cancelled"}
HEARTBEAT_S = 15.0


def format_sse(event: dict[str, Any]) -> str:
    payload = json.dumps(event, ensure_ascii=False, default=str)
    return f"id: {event['seq']}\nevent: {event['type']}\ndata: {payload}\n\n"


@router.get("/{run_id}/events", summary="事件轮询（SSE 兜底）")
def list_events(
    run_id: str,
    store: StoreDep,
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    row = store.get_run(run_id)
    if row is None:
        raise run_not_found(run_id)
    events = store.list_events(run_id, after_seq=after_seq, limit=limit)
    validated = [Event.model_validate(event).model_dump(mode="json") for event in events]
    return {
        "events": validated,
        "run_id": run_id,
        "status": row["status"],
        "is_terminal": row["status"] in {status.value for status in TERMINAL_RUN_STATUSES},
    }


@router.get("/{run_id}/stream", summary="SSE 事件流")
async def stream_events(
    run_id: str,
    request: Request,
    store: StoreDep,
    after_seq: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    row = store.get_run(run_id)
    if row is None:
        raise run_not_found(run_id)

    start_seq = after_seq
    if last_event_id:
        try:
            start_seq = max(start_seq, int(last_event_id))
        except ValueError:
            pass

    async def generator():
        last_seq = start_seq
        for event in store.list_events(run_id, after_seq=start_seq, limit=500):
            last_seq = event["seq"]
            yield format_sse(event)
            if event["type"] in TERMINAL_EVENTS:
                return

        # 终态但事件已读完：直接关闭，不让客户端空等
        current = store.get_run(run_id)
        if current and current["status"] in {status.value for status in TERMINAL_RUN_STATUSES}:
            if store.last_seq(run_id) <= last_seq:
                return

        queue = bus.subscribe(run_id)
        try:
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_S)
                except (TimeoutError, asyncio.TimeoutError):
                    yield ": ping\n\n"
                    continue
                if event["seq"] <= last_seq:
                    continue
                last_seq = event["seq"]
                yield format_sse(event)
                if event["type"] in TERMINAL_EVENTS:
                    return
        finally:
            bus.unsubscribe(run_id, queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
