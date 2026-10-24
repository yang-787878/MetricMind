"""步骤占位符解析单测：$dataset_id / $step: / $last_result。"""

from __future__ import annotations

from app.agent.nodes._steps import resolve_placeholders, with_dataset_id


def test_resolve_dataset_placeholder() -> None:
    state = {"dataset_id": "ds_real", "step_results": []}
    assert resolve_placeholders({"dataset_id": "$dataset_id"}, state, None) == {
        "dataset_id": "ds_real"
    }
    assert resolve_placeholders("$dataset_id", state, None) == "ds_real"


def test_resolve_dataset_placeholder_without_dataset_keeps_literal() -> None:
    assert resolve_placeholders("$dataset_id", {}, None) == "$dataset_id"


def test_resolve_step_and_last_result_placeholders() -> None:
    state = {
        "dataset_id": "ds_real",
        "step_results": [{"step_id": "s2", "result_id": "res_s2", "tool": "query_data"}],
    }
    assert resolve_placeholders({"from_result_id": "$step:s2"}, state, None) == {
        "from_result_id": "res_s2"
    }
    assert resolve_placeholders("$last_result", state, "res_last") == "res_last"


def test_with_dataset_id_only_touches_dataset_tools() -> None:
    assert with_dataset_id("query_data", {"sql": "SELECT 1"}, "ds_real") == {
        "sql": "SELECT 1",
        "dataset_id": "ds_real",
    }
    assert with_dataset_id("create_chart", {"title": "x"}, "ds_real") == {"title": "x"}
