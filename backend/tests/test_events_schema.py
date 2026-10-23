"""事件契约单测（§10.1 第 9 条）：payload 必须能过 Pydantic 模型，seq 严格递增无空洞。"""

from __future__ import annotations

import pytest

from app.models.events import PAYLOAD_MODELS, Event


async def test_all_events_validate_and_sequence_is_dense(harness) -> None:
    await harness.run(mode="demo")
    events = harness.events()

    assert events, "run 必须产生事件"

    for index, raw in enumerate(events):
        event = Event.model_validate(raw)
        assert event.seq == index + 1, f"seq 必须从 1 开始连续：{event.seq} != {index + 1}"
        assert event.type.value in PAYLOAD_MODELS
        assert event.run_id == harness.run_id
        assert event.ts is not None

    for event in events:
        assert isinstance(event["payload"], dict)


async def test_required_event_sequence(harness) -> None:
    await harness.run(mode="demo")
    types = harness.event_types()

    required = [
        "run_started",
        "dataset_inspected",
        "plan_created",
        "step_started",
        "tool_call_started",
        "tool_call_succeeded",
        "step_completed",
        "verification_completed",
        "report_created",
    ]
    for name in required:
        assert name in types, f"缺少事件 {name}"

    assert types[-1] in {"run_succeeded", "run_failed", "run_cancelled"}
    assert types.index("dataset_inspected") < types.index("plan_created")


async def test_tool_call_payload_has_result_id_for_evidence_tools(harness) -> None:
    await harness.run(mode="demo")
    succeeded = [raw for raw in harness.events() if raw["type"] == "tool_call_succeeded"]
    assert len(succeeded) >= 3
    for event in succeeded:
        payload = event["payload"]
        if payload["tool"] in {
            "inspect_dataset",
            "profile_dataset",
            "query_data",
            "calculate_metrics",
            "create_chart",
        }:
            assert payload["result_id"], f"{payload['tool']} 必须产出 result_id"
        assert payload["call_id"]


async def test_unknown_event_type_rejected() -> None:
    with pytest.raises(ValueError):
        Event.model_validate(
            {
                "seq": 1,
                "run_id": "run_x",
                "ts": "2026-10-22T10:00:00Z",
                "type": "unknown_event",
                "payload": {},
            }
        )


async def test_payload_extra_field_rejected() -> None:
    with pytest.raises(ValueError):
        Event.model_validate(
            {
                "seq": 1,
                "run_id": "run_x",
                "ts": "2026-10-22T10:00:00Z",
                "type": "dataset_inspected",
                "payload": {"row_count": 1, "column_count": 2, "unexpected": True},
            }
        )
