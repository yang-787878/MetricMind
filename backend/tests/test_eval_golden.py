"""评测集进 CI（§10.1 第 10 条）：以 mock 模式跑 cases.json，断言全部通过。"""

from __future__ import annotations

from evals.run import load_cases, run_cases


async def test_eval_cases_all_pass(store, settings) -> None:
    cases = load_cases()
    assert len(cases) >= 6, "评测集至少 6 个用例"

    summary = await run_cases(settings=settings, store=store, mode="mock", cases=cases)

    failed = [item for item in summary["results"] if not item["passed"]]
    detail = "\n".join(
        f"{item['case_id']}: " + ", ".join(check["name"] for check in item["checks"] if not check["passed"])
        for item in failed
    )
    assert summary["passed"] == summary["total"], f"评测未全部通过：\n{detail}"
    assert summary["pass_rate"] == 1.0

    # 每条用例都必须真的调用工具并产出证据
    for item in summary["results"]:
        assert item["tools"], f"{item['case_id']} 没有调用任何工具"
        assert item["coverage"] is not None, f"{item['case_id']} 没有覆盖率"
        assert item["coverage"] >= 0.9, f"{item['case_id']} 覆盖率不足：{item['coverage']}"
