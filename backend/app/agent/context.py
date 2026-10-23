"""工具执行上下文：一次 run 内共享的 dataset / 引擎 / 证据池 / 预算计数。

工具函数只依赖这个对象，不自己去碰全局状态，因此可以直接在单测里构造：
`ToolContext(run_id=..., dataset_id=..., store=..., loader=..., engine=..., evidence=...)`。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..config import Settings
from ..errors import dataset_not_found
from ..models.enums import RunMode
from ..services.engine import Engine
from ..services.evidence import EvidencePool
from ..services.loader import DatasetLoader
from ..services.store import Store


@dataclass
class ToolContext:
    run_id: str
    dataset_id: str
    store: Store
    loader: DatasetLoader
    engine: Engine
    evidence: EvidencePool
    settings: Settings
    mode: RunMode = RunMode.DEMO
    step_id: str | None = None
    calls: dict[str, int] = field(default_factory=dict)
    _frame: pd.DataFrame | None = None
    _row: dict[str, Any] | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def assert_dataset(self, dataset_id: str | None) -> str:
        """一个 run 只能访问自己的数据集，防止跨数据集引用。"""
        if dataset_id and dataset_id != self.dataset_id:
            raise dataset_not_found(dataset_id)
        return self.dataset_id

    async def dataset_row(self, dataset_id: str | None = None) -> dict[str, Any]:
        target = self.assert_dataset(dataset_id)
        if self._row is not None and self._row.get("dataset_id") == target:
            return self._row
        row = await asyncio.to_thread(self.store.get_dataset, target)
        if row is None:
            raise dataset_not_found(target)
        self._row = row
        return row

    async def frame(self, dataset_id: str | None = None) -> pd.DataFrame:
        target = self.assert_dataset(dataset_id)
        async with self._lock:
            if self._frame is not None and self._row and self._row.get("dataset_id") == target:
                return self._frame
            row = await self.dataset_row(target)
            frame = await asyncio.to_thread(self.loader.load_frame, row)
            self._frame = frame
            return frame

    def count_call(self, tool: str) -> int:
        self.calls[tool] = self.calls.get(tool, 0) + 1
        return self.calls[tool]

    @property
    def tool_calls_used(self) -> int:
        return sum(self.calls.values())
