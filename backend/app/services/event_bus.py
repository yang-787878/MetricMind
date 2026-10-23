"""进程内事件总线：SSE 订阅者与后台 run 之间的解耦点。

运行由后台 task 持有，客户端断开不影响运行；订阅者只是把已落库的事件实时推过去。
事件本身以 SQLite 为准（`after_seq` 续播从库里读），总线只负责"实时"这一层。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self, queue_size: int = 500) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._queue_size = queue_size

    def subscribe(self, run_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers[run_id].add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subscribers = self._subscribers.get(run_id)
        if not subscribers:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(run_id, None)

    def publish(self, run_id: str, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(run_id, ())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover - 慢客户端不阻塞运行
                continue

    def subscriber_count(self, run_id: str) -> int:
        return len(self._subscribers.get(run_id, ()))


bus = EventBus()
