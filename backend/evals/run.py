"""评测运行器（§9.4）：逐例跑完整工作流，比对工具集与金标准指标。

两个模式：
- `--mode mock`（默认）：Demo 模式，不调用大模型，验证工具链与数字是否正确、证据是否齐全；
- `--mode live`：真实模型（需要 OPENAI_API_KEY），额外暴露模型遵循指令的能力差异。

为什么 mock 模式的问题不影响计划：Demo 的计划由字段结构决定（无模型），
所以 mock 评测衡量的是"确定性分析链"，而不是"模型理解问题"。这一点在 last_run.md 里写明。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 评测默认使用独立数据目录，避免污染演示数据库（backend/data/evals 已被 .gitignore 忽略）。
# 测试或 CI 已经显式设置 DATA_DIR 时保持不动（setdefault）。
EVAL_DATA_DIR = BACKEND_DIR / "data" / "evals"
os.environ.setdefault("DATA_DIR", str(EVAL_DATA_DIR))
os.environ.setdefault("DB_PATH", str(EVAL_DATA_DIR / "metricmind.db"))

from app.agent.graph import build_graph  # noqa: E402
from app.agent.run_context import RunContext  # noqa: E402
from app.agent.state import initial_state  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.llm.factory import build_llm  # noqa: E402
from app.models.enums import RunMode, RunStatus  # noqa: E402
from app.models.run import Budget  # noqa: E402
from app.services.engine import Engine  # noqa: E402
from app.services.evidence import EvidencePool  # noqa: E402
from app.services.loader import DatasetLoader  # noqa: E402
from app.services.store import Store, get_store, utcnow_iso  # noqa: E402

CASES_PATH = Path(__file__).resolve().parent / "cases.json"
REPORT_PATH = Path(__file__).resolve().parent / "last_run.md"


def load_cases(path: Path = CASES_PATH) -> list[dict[str, Any]]:
    # utf-8-sig 容忍 Windows 编辑器写入的 BOM
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload["cases"]


def _metric_value(results: list[dict[str, Any]], name: str) -> float | None:
    for item in results:
        if item["tool"] != "calculate_metrics":
            continue
        for metric in (item["payload"].get("data") or {}).get("metrics", []):
            if metric.get("name") == name and metric.get("value") is not None:
                return float(metric["value"])
    return None


async def run_case(
    case: dict[str, Any],
    *,
    settings: Settings,
    store: Store,
    engine: Engine,
    loader: DatasetLoader,
    mode: str,
) -> dict[str, Any]:
    expect = case.get("expect", {})
    dataset_row, _ = await asyncio.to_thread(loader.create_from_sample, case["dataset"])
    run_id = f"run_eval_{uuid.uuid4().hex[:12]}"
    store.insert_run(
        {
            "run_id": run_id,
            "dataset_id": dataset_row["dataset_id"],
            "question": case["question"],
            "mode": "demo" if mode == "mock" else "live",
            "model": "demo-template" if mode == "mock" else settings.llm_model,
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

    run_mode = RunMode.DEMO if mode == "mock" else RunMode.LIVE
    ctx = RunContext(
        run_id=run_id,
        dataset_id=dataset_row["dataset_id"],
        question=case["question"],
        mode=run_mode,
        store=store,
        loader=loader,
        engine=engine,
        evidence=EvidencePool(store, run_id),
        settings=settings,
        llm=build_llm(settings, run_mode.value),
        budget=Budget(
            max_steps=settings.max_steps,
            max_tool_calls=settings.max_tool_calls,
            max_replans=settings.max_replans,
            timeout_seconds=settings.run_timeout_s,
        ),
        model_name="demo-template" if mode == "mock" else settings.llm_model,
    )

    started = time.perf_counter()
    failure: str | None = None
    try:
        store.update_run(run_id, status="running", started_at=utcnow_iso())
        graph = build_graph(ctx)
        state = initial_state(
            run_id=run_id,
            dataset_id=dataset_row["dataset_id"],
            question=case["question"],
            mode=run_mode.value,
        )
        await asyncio.wait_for(graph.ainvoke(state, config={"recursion_limit": 80}), timeout=settings.run_timeout_s)
    except Exception as exc:  # 评测要记录失败原因，而不是让整批中断
        failure = f"{type(exc).__name__}: {exc}"
    elapsed_s = round(time.perf_counter() - started, 2)

    row = store.get_run(run_id) or {}
    events = store.list_events(run_id)
    tools = [
        str(event["payload"].get("tool"))
        for event in events
        if event["type"] == "tool_call_started"
    ]
    report = json.loads(row["report_json"]) if row.get("report_json") else None
    verification = report.get("verification") if report else None
    claims = (report or {}).get("claims", [])
    results = store.list_results(run_id)

    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    status = row.get("status", "failed")
    allowed = {"succeeded"} | ({"partial"} if expect.get("allow_partial") else set())
    check("status", status in allowed, f"status={status}, allowed={sorted(allowed)}")
    check("no_exception", failure is None, failure or "")

    required = set(expect.get("required_tools", []))
    forbidden = set(expect.get("forbidden_tools", []))
    check("required_tools", required <= set(tools), f"missing={sorted(required - set(tools))}")
    check("forbidden_tools", not (forbidden & set(tools)), f"called={sorted(forbidden & set(tools))}")

    if expect.get("must_cite_evidence"):
        cited = bool(claims) and all(claim.get("evidence_ids") for claim in claims)
        supported = bool(verification) and verification.get("unsupported", 1) == 0
        check("must_cite_evidence", cited, f"claims={len(claims)}")
        check("no_unsupported_claim", supported, f"verification={verification}")

    if expect.get("require_limitations"):
        limitations = (report or {}).get("limitations") or []
        check("require_limitations", len(limitations) > 0, f"limitations={len(limitations)}")

    metric_details: list[str] = []
    for expected_metric in expect.get("expected_metrics", []):
        name = expected_metric["name"]
        target = float(expected_metric["value"])
        tolerance = float(expected_metric.get("tolerance", 0.005))
        actual = _metric_value(results, name)
        if actual is None:
            check(f"metric:{name}", False, "未找到该指标")
            continue
        relative = abs(actual - target) / abs(target) if target else abs(actual - target)
        check(f"metric:{name}", relative <= tolerance, f"actual={actual:.6f} target={target:.6f} rel={relative:.2e}")
        metric_details.append(f"{name}={actual:.4f}")

    return {
        "case_id": case["case_id"],
        "dataset": case["dataset"],
        "status": status,
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "tools": tools,
        "coverage": (verification or {}).get("coverage"),
        "unsupported_claims": (verification or {}).get("unsupported"),
        "elapsed_s": elapsed_s,
        "prompt_tokens": ctx.usage.prompt_tokens,
        "completion_tokens": ctx.usage.completion_tokens,
        "replans": ctx.usage.replans_used,
        "actions": len(ctx.evidence.all_ids()),
        "metrics": metric_details,
        "error": failure,
        "run_id": run_id,
    }


async def run_cases(
    *,
    settings: Settings,
    store: Store,
    mode: str = "mock",
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    engine = Engine()
    loader = DatasetLoader(store, settings)
    selected = cases if cases is not None else load_cases()
    results: list[dict[str, Any]] = []
    try:
        for case in selected:
            results.append(
                await run_case(
                    case,
                    settings=settings,
                    store=store,
                    engine=engine,
                    loader=loader,
                    mode=mode,
                )
            )
    finally:
        engine.close_all()

    passed = sum(1 for item in results if item["passed"])
    return {
        "mode": mode,
        "model": "demo-template" if mode == "mock" else settings.llm_model,
        "ran_at": utcnow_iso(),
        "total": len(results),
        "passed": passed,
        "pass_rate": round(passed / len(results), 4) if results else 0.0,
        "results": results,
    }


def write_report(summary: dict[str, Any], path: Path = REPORT_PATH) -> None:
    lines = [
        "# 评测结果（自动生成，请勿手工编辑）",
        "",
        f"- 运行时间：{summary['ran_at']}",
        f"- 模式：**{summary['mode']}**（{'无模型，Demo 模板计划' if summary['mode'] == 'mock' else '真实模型'}）",
        f"- 模型：`{summary['model']}`",
        f"- 通过率：**{summary['passed']}/{summary['total']}（{summary['pass_rate'] * 100:.1f}%）**",
        "",
        "> mock 模式下计划由字段结构确定性生成，因此这里衡量的是「工具链与数字的正确性、证据完整性」；",
        "> 模型对问题的理解力需要 `--mode live` 才能评估。",
        "",
        "| 用例 | 数据集 | 状态 | 通过 | 工具数 | 覆盖率 | 未通过结论 | 耗时 | 备注 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for item in summary["results"]:
        coverage = "—" if item["coverage"] is None else f"{item['coverage'] * 100:.0f}%"
        failed = [check["name"] for check in item["checks"] if not check["passed"]]
        note = "全部通过" if not failed else ", ".join(failed)
        lines.append(
            f"| {item['case_id']} | {item['dataset']} | {item['status']} | "
            f"{'✅' if item['passed'] else '❌'} | {len(item['tools'])} | {coverage} | "
            f"{item['unsupported_claims'] if item['unsupported_claims'] is not None else '—'} | "
            f"{item['elapsed_s']}s | {note} |"
        )
    lines.append("")
    lines.append("## 逐例明细")
    for item in summary["results"]:
        lines.append("")
        lines.append(f"### {item['case_id']}")
        lines.append("")
        lines.append(f"- run_id：`{item['run_id']}`")
        lines.append(f"- 工具调用：{', '.join(item['tools']) or '无'}")
        if item["metrics"]:
            lines.append(f"- 关键指标：{', '.join(item['metrics'])}")
        for check in item["checks"]:
            mark = "PASS" if check["passed"] else "FAIL"
            detail = f" — {check['detail']}" if check["detail"] else ""
            lines.append(f"- [{mark}] {check['name']}{detail}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="MetricMind 评测运行器")
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--cases", type=Path, default=CASES_PATH)
    parser.add_argument("--out", type=Path, default=REPORT_PATH)
    parser.add_argument("--json", action="store_true", help="只输出 JSON 摘要")
    args = parser.parse_args()

    settings = get_settings()
    if args.mode == "live" and not settings.has_api_key:
        print("live 模式需要 OPENAI_API_KEY，请先在 .env 中配置", file=sys.stderr)
        return 2

    store = get_store()
    summary = asyncio.run(
        run_cases(settings=settings, store=store, mode=args.mode, cases=load_cases(args.cases))
    )
    write_report(summary, args.out)

    if args.json:
        print(json.dumps({key: value for key, value in summary.items() if key != "results"}, ensure_ascii=False))
    else:
        print(f"mode={summary['mode']} model={summary['model']}")
        print(f"{'case_id':32s} {'status':10s} {'pass':5s} {'tools':5s} {'cov':5s} {'elapsed':7s}")
        for item in summary["results"]:
            coverage = "-" if item["coverage"] is None else f"{item['coverage'] * 100:.0f}%"
            print(
                f"{item['case_id']:32s} {item['status']:10s} {'PASS' if item['passed'] else 'FAIL':5s} "
                f"{len(item['tools']):<5d} {coverage:5s} {item['elapsed_s']:>6}s"
            )
        print(f"passed {summary['passed']}/{summary['total']} ({summary['pass_rate'] * 100:.1f}%)")
        print(f"report: {args.out}")

    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
