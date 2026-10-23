"""pytest 公共夹具：临时工作目录、独立 SQLite、loader/engine/工具上下文。

不使用 pytest 的 tmp_path：它的临时目录权限在受限环境下不可写；
这里统一在 tests/_work/<随机> 下建目录，由 .gitignore 忽略。
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

WORK_ROOT = BACKEND_DIR / "tests" / "_work"

# API 测试共用一套真实的全局单例（store / runner），因此必须在 import app 之前
# 把数据目录指到工作区内的临时位置，保证不会写到仓库的 backend/data。
API_DATA_DIR = WORK_ROOT / "api"
os.environ.setdefault("DATA_DIR", str(API_DATA_DIR / "data"))
os.environ.setdefault("DB_PATH", str(API_DATA_DIR / "data" / "metricmind.db"))
os.environ.setdefault("LLM_MODE", "auto")
os.environ.pop("OPENAI_API_KEY", None)

from app.config import Settings  # noqa: E402
from app.services.engine import Engine  # noqa: E402
from app.services.evidence import EvidencePool  # noqa: E402
from app.services.loader import DatasetLoader  # noqa: E402
from app.services.store import Store  # noqa: E402


@pytest.fixture(scope="session")
def work_root() -> Path:
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORK_ROOT / uuid.uuid4().hex[:8]
    path.mkdir()
    yield path


@pytest.fixture
def settings(work_root: Path) -> Settings:
    cfg = Settings(
        data_dir=str(work_root / "data"),
        db_path=str(work_root / "data" / "metricmind.db"),
        llm_mode="demo",
    )
    cfg.ensure_dirs()
    return cfg


@pytest.fixture
def store(settings: Settings) -> Store:
    instance = Store(settings.db_file)
    instance.init_schema()
    return instance


@pytest.fixture
def loader(store: Store, settings: Settings) -> DatasetLoader:
    return DatasetLoader(store, settings)


def _sales_rows(rows: int = 60) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for index in range(rows):
        month = index % 3 + 1
        day = index % 27 + 1
        records.append(
            {
                "order_id": f"o{index:04d}",
                "order_date": f"2025-{month:02d}-{day:02d}",
                "region": ["North", "South", "East"][index % 3],
                "channel": ["DTC", "Wholesale", "Outlet"][index % 3],
                "category": ["Home", "Apparel"][index % 2],
                "units": index % 5 + 1,
                "revenue": float((index + 1) * 10),
                "cost": float((index + 1) * 6),
                "returns_flag": 1 if index % 7 == 0 else 0,
            }
        )
    return records


@pytest.fixture
def sales_frame() -> pd.DataFrame:
    return pd.DataFrame(_sales_rows())


@pytest.fixture
def dataset_row(loader: DatasetLoader, sales_frame: pd.DataFrame) -> dict:
    csv_bytes = sales_frame.to_csv(index=False).encode("utf-8")
    return loader.create_from_upload("fixture_sales.csv", csv_bytes)


@pytest.fixture
def engine() -> Engine:
    instance = Engine()
    yield instance
    instance.close_all()


@pytest.fixture
def evidence(store: Store) -> EvidencePool:
    return EvidencePool(store, "run_test")


@pytest.fixture
def ctx(store, loader, engine, evidence, settings, dataset_row):
    from app.agent.context import ToolContext

    return ToolContext(
        run_id="run_test",
        dataset_id=dataset_row["dataset_id"],
        store=store,
        loader=loader,
        engine=engine,
        evidence=evidence,
        settings=settings,
    )


@pytest.fixture(scope="session")
def real_sample_csv() -> Path:
    path = BACKEND_DIR.parent / "data" / "sample_sales.csv"
    if not path.exists():
        pytest.skip("示例数据未生成，先运行 scripts/generate_sample_data.py")
    return path


@pytest.fixture(scope="session")
def expected_answers() -> dict:
    path = BACKEND_DIR.parent / "data" / "expected_answers.json"
    if not path.exists():
        pytest.skip("金标准未生成，先运行 scripts/compute_expected.py")
    return json.loads(path.read_text(encoding="utf-8"))


class GraphHarness:
    """直接驱动 LangGraph（不经过 HTTP），用于图/事件/确定性测试。"""

    def __init__(self, *, store: Store, loader: DatasetLoader, settings: Settings, dataset_row: dict):
        from app.services.engine import Engine

        self.store = store
        self.loader = loader
        self.settings = settings
        self.dataset = dataset_row
        self.dataset_id = dataset_row["dataset_id"]
        self.run_id = f"run_{uuid.uuid4().hex[:12]}"
        self.engine = Engine()
        self.context = None
        self.final_state: dict | None = None
        self.store.insert_run(
            {
                "run_id": self.run_id,
                "dataset_id": self.dataset_id,
                "question": "为什么销售额下降了？",
                "mode": "demo",
                "model": "demo-template",
                "status": "queued",
                "plan_json": None,
                "state_json": None,
                "report_json": None,
                "verification_json": None,
                "usage_json": None,
                "error_json": None,
                "created_at": "2026-10-22T10:00:00.000Z",
                "started_at": None,
                "finished_at": None,
            }
        )

    async def run(
        self,
        *,
        mode: str = "demo",
        llm=None,
        question: str = "为什么销售额下降了？",
        budget=None,
    ) -> dict:
        from app.agent.graph import build_graph
        from app.agent.run_context import RunContext
        from app.agent.state import initial_state
        from app.models.run import Budget

        if llm is None:
            from app.llm.factory import build_llm

            llm = build_llm(self.settings, mode)

        self.store.update_run(self.run_id, status="running", started_at="2026-10-22T10:00:00.000Z")
        self.context = RunContext(
            run_id=self.run_id,
            dataset_id=self.dataset_id,
            question=question,
            mode=mode,
            store=self.store,
            loader=self.loader,
            engine=self.engine,
            evidence=EvidencePool(self.store, self.run_id),
            settings=self.settings,
            llm=llm,
            budget=budget
            or Budget(
                max_steps=self.settings.max_steps,
                max_tool_calls=self.settings.max_tool_calls,
                max_replans=self.settings.max_replans,
                timeout_seconds=self.settings.run_timeout_s,
            ),
            model_name="demo-template" if mode == "demo" else "fake-llm",
        )
        graph = build_graph(self.context)
        state = initial_state(
            run_id=self.run_id, dataset_id=self.dataset_id, question=question, mode=mode
        )
        self.final_state = await graph.ainvoke(state, config={"recursion_limit": 80})
        self.engine.close_all()
        return self.final_state

    def events(self) -> list[dict]:
        return self.store.list_events(self.run_id)

    def event_types(self) -> list[str]:
        return [event["type"] for event in self.events()]

    def report(self) -> dict | None:
        row = self.store.get_run(self.run_id) or {}
        return json.loads(row["report_json"]) if row.get("report_json") else None

    def run_row(self) -> dict:
        return self.store.get_run(self.run_id) or {}


@pytest.fixture
def harness(store, loader, settings, dataset_row) -> GraphHarness:
    return GraphHarness(store=store, loader=loader, settings=settings, dataset_row=dataset_row)


@pytest.fixture
def api_client(monkeypatch):
    """真实 ASGI 客户端：使用全局 store / runner，但数据目录被 conftest 指到 tests/_work。"""
    import shutil

    from app.config import get_settings
    from app.runner import reset_run_manager
    from app.services.store import reset_store

    if API_DATA_DIR.exists():
        shutil.rmtree(API_DATA_DIR, ignore_errors=True)
    settings = get_settings()
    settings.ensure_dirs()
    reset_store()
    reset_run_manager()

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client
    reset_store()
    reset_run_manager()
