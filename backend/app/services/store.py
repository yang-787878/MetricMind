"""SQLite 仓储层（stdlib sqlite3，WAL，无 ORM）。

为什么不用 ORM：表结构就 5 张、查询都是按主键/按 run 取整行，ORM 只会带来
一层难调试的映射。这里把"写入必须走这里"作为纪律，事件 seq 在事务内生成。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..errors import ErrorCode, AppError
from ..logging_conf import get_logger

logger = get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id        TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    source            TEXT NOT NULL,
    stored_path       TEXT NOT NULL,
    row_count         INTEGER NOT NULL,
    column_count      INTEGER NOT NULL,
    size_bytes        INTEGER NOT NULL,
    checksum          TEXT,
    schema_json       TEXT NOT NULL,
    quality_json      TEXT NOT NULL,
    encoding          TEXT,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id            TEXT PRIMARY KEY,
    dataset_id        TEXT NOT NULL REFERENCES datasets(dataset_id),
    question          TEXT NOT NULL,
    mode              TEXT NOT NULL,
    model             TEXT,
    status            TEXT NOT NULL,
    plan_json         TEXT,
    state_json        TEXT,
    report_json       TEXT,
    verification_json TEXT,
    usage_json        TEXT,
    error_json        TEXT,
    created_at        TEXT NOT NULL,
    started_at        TEXT,
    finished_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_dataset ON runs(dataset_id, created_at DESC);

CREATE TABLE IF NOT EXISTS events (
    run_id       TEXT NOT NULL,
    seq          INTEGER NOT NULL,
    ts           TEXT NOT NULL,
    type         TEXT NOT NULL,
    step_id      TEXT,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);

CREATE TABLE IF NOT EXISTS results (
    result_id    TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL,
    tool         TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    format      TEXT NOT NULL,
    path        TEXT NOT NULL,
    size_bytes  INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id);
"""


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Store:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._write_lock = threading.Lock()

    # ---------------- 连接与建表 ----------------
    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
        logger.info("db_schema_ready", extra={"db": str(self.db_path)})

    def ping(self) -> bool:
        try:
            with self.connect() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error as exc:  # pragma: no cover - 仅在磁盘/权限异常时
            logger.error("db_ping_failed", extra={"error": str(exc)})
            return False

    def mark_interrupted_runs(self) -> int:
        """进程重启后把遗留的 queued/running 标记为 failed（§6.6 诚实处理）。"""
        now = utcnow_iso()
        error = json.dumps(
            {
                "code": ErrorCode.RUN_INTERRUPTED.value,
                "message": "服务重启，运行被中断",
                "hint": "可重新发起同一问题的分析",
            },
            ensure_ascii=False,
        )
        with self.connect() as conn:
            cur = conn.execute(
                """UPDATE runs SET status='failed', finished_at=?, error_json=?
                   WHERE status IN ('queued','running')""",
                (now, error),
            )
            count = cur.rowcount or 0
        if count:
            logger.warning("runs_marked_interrupted", extra={"count": count})
        return count

    # ---------------- datasets ----------------
    def insert_dataset(self, row: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO datasets(dataset_id,name,original_filename,source,stored_path,
                       row_count,column_count,size_bytes,checksum,schema_json,quality_json,
                       encoding,created_at)
                   VALUES(:dataset_id,:name,:original_filename,:source,:stored_path,:row_count,
                       :column_count,:size_bytes,:checksum,:schema_json,:quality_json,
                       :encoding,:created_at)""",
                row,
            )

    def get_dataset(self, dataset_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM datasets WHERE dataset_id=?", (dataset_id,)).fetchone()
        return dict(row) if row else None

    def list_datasets(self, limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM datasets ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) AS c FROM datasets").fetchone()["c"]
        return [dict(r) for r in rows], int(total)

    def count_dataset_runs(self, dataset_id: str) -> int:
        with self.connect() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM runs WHERE dataset_id=?", (dataset_id,)
                ).fetchone()["c"]
            )

    def delete_dataset(self, dataset_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM datasets WHERE dataset_id=?", (dataset_id,))

    def find_dataset_by_checksum(self, checksum: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM datasets WHERE checksum=? ORDER BY created_at LIMIT 1", (checksum,)
            ).fetchone()
        return dict(row) if row else None

    # ---------------- runs ----------------
    def insert_run(self, row: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO runs(run_id,dataset_id,question,mode,model,status,plan_json,
                       state_json,report_json,verification_json,usage_json,error_json,
                       created_at,started_at,finished_at)
                   VALUES(:run_id,:dataset_id,:question,:mode,:model,:status,:plan_json,
                       :state_json,:report_json,:verification_json,:usage_json,:error_json,
                       :created_at,:started_at,:finished_at)""",
                row,
            )

    def update_run(self, run_id: str, **fields: Any) -> None:
        if not fields:
            return
        allowed = {
            "status", "model", "plan_json", "state_json", "report_json", "verification_json",
            "usage_json", "error_json", "started_at", "finished_at",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported run fields: {sorted(unknown)}")
        sets = ", ".join(f"{key}=:{key}" for key in fields)
        with self.connect() as conn:
            conn.execute(f"UPDATE runs SET {sets} WHERE run_id=:run_id", {**fields, "run_id": run_id})

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_runs(
        self, dataset_id: str | None = None, status: str | None = None, limit: int = 20
    ) -> tuple[list[dict[str, Any]], int]:
        clauses: list[str] = []
        params: list[Any] = []
        if dataset_id:
            clauses.append("r.dataset_id=?")
            params.append(dataset_id)
        if status:
            clauses.append("r.status=?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT r.*, d.name AS dataset_name FROM runs r "
            "LEFT JOIN datasets d ON d.dataset_id = r.dataset_id "
            f"{where} ORDER BY r.created_at DESC LIMIT ?"
        )
        with self.connect() as conn:
            rows = conn.execute(sql, (*params, limit)).fetchall()
            total = int(
                conn.execute(f"SELECT COUNT(*) AS c FROM runs r {where}", tuple(params)).fetchone()[
                    "c"
                ]
            )
        return [dict(r) for r in rows], total

    # ---------------- events ----------------
    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
        step_id: str | None = None,
        ts: str | None = None,
    ) -> dict[str, Any]:
        """seq 在写事务内由 MAX(seq)+1 生成，保证同一 run 内严格递增无空洞。"""
        with self._write_lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS m FROM events WHERE run_id=?", (run_id,)
            ).fetchone()
            seq = int(row["m"]) + 1
            stamp = ts or utcnow_iso()
            conn.execute(
                "INSERT INTO events(run_id,seq,ts,type,step_id,payload_json) VALUES(?,?,?,?,?,?)",
                (run_id, seq, stamp, event_type, step_id, json.dumps(payload, ensure_ascii=False)),
            )
        return {
            "seq": seq,
            "run_id": run_id,
            "ts": stamp,
            "type": event_type,
            "step_id": step_id,
            "payload": payload,
        }

    def list_events(self, run_id: str, after_seq: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq ASC LIMIT ?",
                (run_id, after_seq, limit),
            ).fetchall()
        return [
            {
                "seq": r["seq"],
                "run_id": r["run_id"],
                "ts": r["ts"],
                "type": r["type"],
                "step_id": r["step_id"],
                "payload": json.loads(r["payload_json"]),
            }
            for r in rows
        ]

    def last_seq(self, run_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq),0) AS m FROM events WHERE run_id=?", (run_id,)
            ).fetchone()
        return int(row["m"])

    # ---------------- results（证据池） ----------------
    def save_result(self, result_id: str, run_id: str, tool: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO results(result_id,run_id,tool,payload_json,created_at)"
                " VALUES(?,?,?,?,?)",
                (result_id, run_id, tool, json.dumps(payload, ensure_ascii=False), utcnow_iso()),
            )

    def get_result(self, result_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM results WHERE result_id=?", (result_id,)).fetchone()
        if not row:
            return None
        return {
            "result_id": row["result_id"],
            "run_id": row["run_id"],
            "tool": row["tool"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        }

    def list_results(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM results WHERE run_id=? ORDER BY created_at ASC", (run_id,)
            ).fetchall()
        return [
            {
                "result_id": r["result_id"],
                "run_id": r["run_id"],
                "tool": r["tool"],
                "payload": json.loads(r["payload_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    # ---------------- artifacts ----------------
    def save_artifact(self, row: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO artifacts(artifact_id,run_id,kind,format,path,size_bytes,"
                "created_at) VALUES(:artifact_id,:run_id,:kind,:format,:path,:size_bytes,:created_at)",
                row,
            )

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM artifacts WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE run_id=? ORDER BY created_at ASC", (run_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def find_artifact(self, run_id: str, fmt: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM artifacts WHERE run_id=? AND format=? ORDER BY created_at DESC LIMIT 1",
                (run_id, fmt),
            ).fetchone()
        return dict(row) if row else None


_store: Store | None = None


def get_store() -> Store:
    """进程级单例；测试里可替换 app.deps 中的依赖。"""
    global _store
    if _store is None:
        from ..config import get_settings

        settings = get_settings()
        settings.ensure_dirs()
        _store = Store(settings.db_file)
        _store.init_schema()
    return _store


def reset_store() -> None:
    global _store
    _store = None


__all__ = ["Store", "get_store", "reset_store", "utcnow_iso", "AppError"]
