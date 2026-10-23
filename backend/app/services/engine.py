"""DuckDB 会话管理：每个 run 独立 in-memory 连接，只注册视图 data（§2.2 / §5.2(3)）。

执行隔离三件套在连接创建后立刻设置：
`enable_external_access=false` + 禁止自动安装/加载扩展。
这样即使守卫漏掉某个外部读取函数，DuckDB 自身也读不到文件系统与网络。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import duckdb
import pandas as pd

from ..errors import AppError, ErrorCode
from ..logging_conf import get_logger
from .jsonable import to_jsonable
from . import sql_guard

logger = get_logger(__name__)

QUERY_TIMEOUT_S = 30.0


@dataclass
class QueryOutcome:
    columns: list[dict[str, str]]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    sql_executed: str
    duration_ms: int
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "truncated": self.truncated,
            "sql_executed": self.sql_executed,
            "duration_ms": self.duration_ms,
            "warnings": self.warnings,
        }


class DuckDBSession:
    def __init__(self, frame: pd.DataFrame, dataset_id: str) -> None:
        self.dataset_id = dataset_id
        self.conn = duckdb.connect(database=":memory:")
        self.conn.execute("SET enable_external_access=false")
        self.conn.execute("SET autoinstall_known_extensions=false")
        self.conn.execute("SET autoload_known_extensions=false")
        self.conn.register("data", frame)
        self.columns = [str(name) for name in frame.columns]

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:  # pragma: no cover - 关闭失败不影响结果
            logger.warning("duckdb_close_failed", extra={"dataset_id": self.dataset_id})

    def interrupt(self) -> None:
        try:
            self.conn.interrupt()
        except Exception:  # pragma: no cover - 已结束的查询无需中断
            logger.warning("duckdb_interrupt_failed", extra={"dataset_id": self.dataset_id})

    def execute(self, sql: str, max_rows: int = 200) -> QueryOutcome:
        """同步执行（由 to_thread 调用）：守卫 → 外层 LIMIT → 截断判定。"""
        started = time.perf_counter()
        wrapped = sql_guard.wrap_with_limit(sql, max_rows)
        try:
            cursor = self.conn.execute(wrapped)
            raw_columns = cursor.description or []
            rows = cursor.fetchall()
        except duckdb.Error as exc:
            message = str(exc).strip().splitlines()[0][:400]
            raise AppError(
                ErrorCode.SQL_EXECUTION_ERROR,
                f"SQL 执行失败：{message}",
                details={"sql": sql[:2000]},
                hint="请检查列名、函数与语法；只能查询视图 data",
            ) from exc

        truncated = len(rows) > max_rows
        trimmed = rows[:max_rows]
        columns = [{"name": str(item[0]), "type": str(item[1])} for item in raw_columns]
        duration_ms = int((time.perf_counter() - started) * 1000)
        warnings = ["结果已截断，结论可能不完整"] if truncated else []
        return QueryOutcome(
            columns=columns,
            rows=[[to_jsonable(value) for value in row] for row in trimmed],
            row_count=len(trimmed),
            truncated=truncated,
            sql_executed=wrapped,
            duration_ms=duration_ms,
            warnings=warnings,
        )


class Engine:
    """按 (run_id, dataset_id) 缓存会话；run 结束或取消时统一关闭。"""

    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], DuckDBSession] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def session(self, run_id: str, dataset_id: str, frame_factory) -> DuckDBSession:
        key = (run_id, dataset_id)
        if key in self._sessions:
            return self._sessions[key]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if key not in self._sessions:
                session = await asyncio.to_thread(self._build, frame_factory, dataset_id)
                self._sessions[key] = session
                logger.info(
                    "duckdb_session_created",
                    extra={"run_id": run_id, "dataset_id": dataset_id},
                )
            return self._sessions[key]

    @staticmethod
    def _build(frame_factory, dataset_id: str) -> DuckDBSession:
        frame = frame_factory()
        return DuckDBSession(frame=frame, dataset_id=dataset_id)

    async def execute(
        self,
        run_id: str,
        dataset_id: str,
        frame_factory,
        sql: str,
        max_rows: int,
        timeout_s: float = QUERY_TIMEOUT_S,
    ) -> QueryOutcome:
        session = await self.session(run_id, dataset_id, frame_factory)
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(session.execute, sql, max_rows),
                timeout=timeout_s,
            )
        except (TimeoutError, asyncio.TimeoutError) as exc:
            session.interrupt()
            raise AppError(
                ErrorCode.TOOL_TIMEOUT,
                f"查询超过 {timeout_s:.0f}s 未返回，已中断",
                details={"sql": sql[:2000]},
                hint="请缩小扫描范围或先聚合",
            ) from exc

    def close_run(self, run_id: str) -> None:
        for (rid, dataset_id), session in list(self._sessions.items()):
            if rid == run_id:
                session.close()
                self._sessions.pop((rid, dataset_id), None)
                self._locks.pop((rid, dataset_id), None)

    def close_all(self) -> None:
        for session in list(self._sessions.values()):
            session.close()
        self._sessions.clear()
        self._locks.clear()
