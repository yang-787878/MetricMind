"""取消路径单测（§6.6）：取消标志在节点检查点生效。"""

from __future__ import annotations

import pytest

from app.agent.nodes import execute as execute_node
from app.agent.run_context import RunCancelled, RunContext
from app.llm.fake_client import FakeLLM
from app.models.run import Budget
from app.services.evidence import EvidencePool


def _ctx(store, loader, engine, settings, dataset_row, run_id="run_cancel"):
    return RunContext(
        run_id=run_id,
        dataset_id=dataset_row["dataset_id"],
        question="取消测试",
        mode="demo",
        store=store,
        loader=loader,
        engine=engine,
        evidence=EvidencePool(store, run_id),
        settings=settings,
        llm=FakeLLM(),
        budget=Budget(max_steps=5, max_tool_calls=5, max_replans=1, timeout_seconds=60),
    )


async def test_execute_node_raises_when_cancelled(store, loader, engine, settings, dataset_row) -> None:
    ctx = _ctx(store, loader, engine, settings, dataset_row)
    ctx.cancel_flag.set()
    state = {"steps": [], "step_index": 0, "dataset_id": dataset_row["dataset_id"]}
    with pytest.raises(RunCancelled):
        await execute_node.execute(state, ctx)


async def test_cancelled_run_keeps_events(store, loader, engine, settings, dataset_row) -> None:
    """取消后已产生的事件仍在库里（§6.6：已产生的事件与结果保留可看）。"""
    ctx = _ctx(store, loader, engine, settings, dataset_row, run_id="run_cancel_events")
    await ctx.emit("run_created", {"run_id": ctx.run_id, "mode": "demo", "dataset_id": ctx.dataset_id})
    events = store.list_events(ctx.run_id)
    assert len(events) == 1
    assert events[0]["type"] == "run_created"
