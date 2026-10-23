"""证据池：每次工具调用产出的结果集，以 result_id 编号并持久化（§1.2 证据链）。

只要 result_id 存在，图表与结论就必须引用它；池子按 run 隔离，跨 run 引用直接拒绝。
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from ..logging_conf import get_logger
from .store import Store

logger = get_logger(__name__)

RESULT_ID_PREFIX = "res_"
NUMERIC_STRING = ("%", ".")


def new_result_id() -> str:
    return f"{RESULT_ID_PREFIX}{uuid.uuid4().hex[:12]}"


def _walk_numbers(node: Any, out: list[float]) -> None:
    if isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        out.append(float(node))
        return
    if isinstance(node, str):
        text = node.strip().replace(",", "")
        if not text or len(text) > 32:
            return
        stripped = text.rstrip("%")
        try:
            value = float(stripped)
        except ValueError:
            return
        if text.endswith("%"):
            value = value / 100
        out.append(value)
        return
    if isinstance(node, dict):
        for value in node.values():
            _walk_numbers(value, out)
        return
    if isinstance(node, (list, tuple)):
        for value in node:
            _walk_numbers(value, out)


def extract_numbers(payload: Any) -> list[float]:
    """递归提取证据中的所有数值（含分组值、KPI、表格单元格）。"""
    numbers: list[float] = []
    _walk_numbers(payload, numbers)
    return numbers


def extract_tables(payload: Any) -> list[dict[str, Any]]:
    """把证据里的表格型数据抽出来，供 create_chart 引用与报告渲染。"""
    tables: list[dict[str, Any]] = []
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        columns = data.get("columns")
        rows = data.get("rows")
        if isinstance(columns, list) and isinstance(rows, list):
            tables.append({"columns": columns, "rows": rows})
    return tables


class EvidencePool:
    def __init__(self, store: Store, run_id: str) -> None:
        self.store = store
        self.run_id = run_id
        self._cache: dict[str, dict[str, Any]] = {}

    def record(
        self,
        *,
        tool: str,
        data: Any,
        meta: dict[str, Any] | None = None,
        step_id: str | None = None,
    ) -> str:
        result_id = new_result_id()
        payload = {"data": data, "meta": meta or {}, "step_id": step_id, "tool": tool}
        self.store.save_result(
            result_id=result_id, run_id=self.run_id, tool=tool, payload=payload
        )
        self._cache[result_id] = payload
        logger.info(
            "evidence_recorded",
            extra={"run_id": self.run_id, "result_id": result_id, "tool": tool},
        )
        return result_id

    def get(self, result_id: str) -> dict[str, Any] | None:
        if result_id in self._cache:
            return self._cache[result_id]
        row = self.store.get_result(result_id)
        if not row or row["run_id"] != self.run_id:
            return None
        payload = row["payload"]
        self._cache[result_id] = payload
        return payload

    def exists(self, result_id: str) -> bool:
        return self.get(result_id) is not None

    def summary(self, result_id: str) -> dict[str, Any]:
        payload = self.get(result_id) or {}
        numbers = extract_numbers(payload.get("data"))
        return {
            "result_id": result_id,
            "tool": payload.get("tool"),
            "step_id": payload.get("step_id"),
            "numbers": numbers[:200],
            "tables": extract_tables(payload),
        }

    def all_ids(self) -> list[str]:
        return [item["result_id"] for item in self.store.list_results(self.run_id)]

    def dump(self) -> dict[str, Any]:
        """证据池的紧凑快照，写入 runs.state_json 便于取消后查看中间态。"""
        return {
            result_id: self.summary(result_id)
            for result_id in self.all_ids()
        }

    def to_json(self) -> str:
        return json.dumps(self.dump(), ensure_ascii=False)
