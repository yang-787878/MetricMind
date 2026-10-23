"""HTTP 契约单测（§10.1 第 8 条）：上传矩阵、run 生命周期、SSE、续播、取消、报告。"""

from __future__ import annotations

import json
import time

import pytest

from app.errors import AppError

CSV = (
    "region,channel,revenue,order_date\n"
    "North,DTC,120.5,2025-01-03\n"
    "South,Outlet,80.0,2025-01-04\n"
    "North,DTC,99.5,2025-02-11\n"
    "East,Wholesale,150.0,2025-02-12\n"
)
TERMINAL = {"succeeded", "partial", "failed", "cancelled"}


def _upload(client, name: str = "demo.csv", content: str = CSV):
    return client.post(
        "/api/datasets", files={"file": (name, content.encode("utf-8"), "text/csv")}
    )


def _wait_terminal(client, run_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        detail = client.get(f"/api/runs/{run_id}").json()
        if detail["status"] in TERMINAL:
            return detail
        time.sleep(0.15)
    raise AssertionError(f"run {run_id} 未在 {timeout}s 内结束")


def test_upload_success_and_preview(api_client) -> None:
    response = _upload(api_client)
    assert response.status_code == 201
    body = response.json()
    assert body["row_count"] == 4
    assert body["column_count"] == 4
    kinds = {column["name"]: column["semantic_type"] for column in body["columns"]}
    assert kinds["order_date"] == "temporal"
    assert kinds["revenue"] == "numeric"

    preview = api_client.get(f"/api/datasets/{body['dataset_id']}/preview?limit=2")
    assert preview.status_code == 200
    assert preview.json()["total_rows"] == 4
    assert len(preview.json()["rows"]) == 2


def test_upload_rejects_bad_inputs(api_client) -> None:
    bad_type = _upload(api_client, "notes.txt", "a,b\n1,2\n")
    assert bad_type.status_code == 415
    assert bad_type.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    empty = _upload(api_client, "empty.csv", "")
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "INVALID_DATASET"

    duplicate = _upload(api_client, "dup.csv", "revenue,revenue\n1,2\n")
    assert duplicate.status_code == 400
    assert duplicate.json()["error"]["code"] == "INVALID_DATASET"

    for response in (bad_type, empty, duplicate):
        body = response.json()["error"]
        assert body["request_id"]
        assert body["message"]


def test_dataset_not_found(api_client) -> None:
    assert api_client.get("/api/datasets/ds_missing").status_code == 404
    assert api_client.get("/api/datasets/ds_missing/preview").status_code == 404


def test_run_lifecycle_and_report(api_client) -> None:
    dataset = _upload(api_client).json()
    created = api_client.post(
        "/api/runs",
        json={"dataset_id": dataset["dataset_id"], "question": "各渠道收入有什么差异？", "mode": "demo"},
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]
    assert created.json()["mode"] == "demo"
    assert created.json()["stream_url"].endswith(f"/runs/{run_id}/stream")

    detail = _wait_terminal(api_client, run_id)
    assert detail["status"] in {"succeeded", "partial"}
    assert detail["plan"] is not None
    assert len(detail["steps"]) >= 2
    assert detail["steps"][0]["tool_calls"], "步骤里必须有真实工具调用记录"
    assert detail["usage"]["tool_calls_used"] >= 3

    report = api_client.get(f"/api/runs/{run_id}/report")
    assert report.status_code == 200
    body = report.json()
    assert body["run_id"] == run_id
    assert body["verification"]["coverage"] >= 0.9
    assert body["kpis"], "报告必须包含 KPI"

    events = api_client.get(f"/api/runs/{run_id}/events").json()
    assert events["events"]
    assert events["is_terminal"] is True
    seqs = [event["seq"] for event in events["events"]]
    assert seqs == list(range(1, len(seqs) + 1))

    resumed = api_client.get(f"/api/runs/{run_id}/events?after_seq={seqs[3]}").json()
    assert all(event["seq"] > seqs[3] for event in resumed["events"])

    listing = api_client.get("/api/runs").json()
    assert any(item["run_id"] == run_id for item in listing["items"])


def test_sse_stream_first_and_last_frame(api_client) -> None:
    dataset = _upload(api_client).json()
    run_id = api_client.post(
        "/api/runs",
        json={"dataset_id": dataset["dataset_id"], "question": "总收入是多少？", "mode": "demo"},
    ).json()["run_id"]
    _wait_terminal(api_client, run_id)

    frames: list[str] = []
    with api_client.stream("GET", f"/api/runs/{run_id}/stream") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line:
                frames.append(line)
            if len(frames) > 400:
                break

    assert frames[0].startswith("id: ")
    event_lines = [line for line in frames if line.startswith("event: ")]
    assert event_lines[0] == "event: run_created"
    assert event_lines[-1] in {"event: run_succeeded", "event: run_failed", "event: run_cancelled"}
    data_lines = [line for line in frames if line.startswith("data: ")]
    payload = json.loads(data_lines[0][len("data: "):])
    assert payload["type"] == "run_created"
    assert payload["seq"] == 1


def test_live_mode_without_key_returns_409(api_client, monkeypatch) -> None:
    """即使开发机的 .env 配了 Key，也要能验证"没有 Key 时 live 被拒"这条路。"""
    from app.config import Settings

    monkeypatch.setattr(Settings, "has_api_key", property(lambda self: False))

    dataset = _upload(api_client).json()
    response = api_client.post(
        "/api/runs",
        json={"dataset_id": dataset["dataset_id"], "question": "总收入是多少？", "mode": "live"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"


def test_cancel_finished_and_unknown(api_client) -> None:
    dataset = _upload(api_client).json()
    run_id = api_client.post(
        "/api/runs",
        json={"dataset_id": dataset["dataset_id"], "question": "总收入是多少？", "mode": "demo"},
    ).json()["run_id"]
    _wait_terminal(api_client, run_id)

    finished = api_client.post(f"/api/runs/{run_id}/cancel")
    assert finished.status_code == 409
    assert finished.json()["error"]["code"] == "RUN_ALREADY_FINISHED"

    unknown = api_client.post("/api/runs/run_missing/cancel")
    assert unknown.status_code == 404


def test_report_not_ready_for_queued_run(api_client) -> None:
    from app.services.store import get_store, utcnow_iso

    dataset = _upload(api_client).json()
    store = get_store()
    run_id = "run_queued_fixture"
    store.insert_run(
        {
            "run_id": run_id,
            "dataset_id": dataset["dataset_id"],
            "question": "等待中的运行",
            "mode": "demo",
            "model": "demo-template",
            "status": "queued",
            "plan_json": None,
            "state_json": None,
            "report_json": None,
            "verification_json": None,
            "usage_json": None,
            "error_json": None,
            "created_at": utcnow_iso(),
            "started_at": None,
            "finished_at": None,
        }
    )
    response = api_client.get(f"/api/runs/{run_id}/report")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REPORT_NOT_READY"


def test_cancel_queued_run(api_client) -> None:
    """排队中的 run 取消后立即进入 cancelled，并留下 run_cancelled 事件。"""
    from app.services.store import get_store, utcnow_iso

    dataset = _upload(api_client).json()
    store = get_store()
    run_id = "run_queued_cancel"
    store.insert_run(
        {
            "run_id": run_id,
            "dataset_id": dataset["dataset_id"],
            "question": "还没开始就被取消",
            "mode": "demo",
            "model": "demo-template",
            "status": "queued",
            "plan_json": None,
            "state_json": None,
            "report_json": None,
            "verification_json": None,
            "usage_json": None,
            "error_json": None,
            "created_at": utcnow_iso(),
            "started_at": None,
            "finished_at": None,
        }
    )
    response = api_client.post(f"/api/runs/{run_id}/cancel")
    assert response.status_code == 202
    assert response.json()["status"] == "cancelled"
    assert store.get_run(run_id)["status"] == "cancelled"
    events = store.list_events(run_id)
    assert events[-1]["type"] == "run_cancelled"
    assert events[-1]["payload"]["status"] == "cancelled"


def test_cancel_running_run(api_client, monkeypatch) -> None:
    """运行中取消：节点检查点生效，终态 cancelled，已产生事件保留。"""
    import time

    from app.services.loader import DatasetLoader

    original = DatasetLoader.load_frame

    def slow_load(self, row):  # noqa: ANN001 - 仅测试用
        time.sleep(1.2)
        return original(self, row)

    monkeypatch.setattr(DatasetLoader, "load_frame", slow_load)

    dataset = _upload(api_client).json()
    run_id = api_client.post(
        "/api/runs",
        json={"dataset_id": dataset["dataset_id"], "question": "运行中取消测试", "mode": "demo"},
    ).json()["run_id"]

    time.sleep(0.5)  # 让 run 进入 running
    response = api_client.post(f"/api/runs/{run_id}/cancel")
    assert response.status_code == 202

    detail = _wait_terminal(api_client, run_id)
    assert detail["status"] == "cancelled"
    events = api_client.get(f"/api/runs/{run_id}/events").json()["events"]
    assert events[-1]["type"] == "run_cancelled"
    assert len(events) > 1, "取消后已产生的事件必须保留"


def test_run_not_found(api_client) -> None:
    assert api_client.get("/api/runs/run_missing").status_code == 404
    assert api_client.get("/api/runs/run_missing/events").status_code == 404


def test_rate_limit_unit() -> None:
    from app.api.runs import _check_rate_limit, _rate_buckets

    _rate_buckets.clear()
    for _ in range(3):
        _check_rate_limit("10.0.0.9", 3)
    with pytest.raises(AppError) as info:
        _check_rate_limit("10.0.0.9", 3)
    assert info.value.code == "RATE_LIMITED"
    assert info.value.http_status == 429
