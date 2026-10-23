"""LangGraph 装配（§6.2）：只负责节点与条件边，业务逻辑都在 nodes/ 里。

状态机概览：
START → intake → inspect → plan → execute ↺
execute ─失败可修复→ repair_step → execute
execute ─失败不可修复→ fail → finalize
execute ─全部完成→ verify ─需重规划→ replan → execute
                            └─否则→ report → audit ─覆盖不足且首次→ report
                                                     └─否则→ finalize → END
"""

from __future__ import annotations

from functools import partial
from typing import Any

from langgraph.graph import END, START, StateGraph

from .nodes import audit, execute, fail, finalize, inspect, intake, plan, repair_step, replan, report, verify
from .run_context import RunContext
from .state import AgentState

EXECUTE_ROUTES = {
    "execute": "execute",
    "repair_step": "repair_step",
    "verify": "verify",
    "fail": "fail",
    "finalize": "finalize",
    "report": "report",
}
AUDIT_ROUTES = {"report": "report", "finalize": "finalize"}


def _route_after_execute(state: AgentState) -> str:
    routing = str(state.get("routing") or "continue")
    if routing == "finalize":
        return "finalize"
    # 预算耗尽也要出一份"部分结果报告"，而不是直接收口成空报告
    if routing == "budget":
        return "report"
    if routing == "fail" or state.get("error"):
        return "fail"
    if state.get("failed_step"):
        return "repair_step"
    steps = state.get("steps") or []
    if int(state.get("step_index") or 0) >= len(steps):
        return "verify"
    return "execute"


def _route_after_repair(state: AgentState) -> str:
    if state.get("error") or str(state.get("routing")) == "fail":
        return "fail"
    return "execute"


def _route_after_verify(state: AgentState) -> str:
    return "replan" if str(state.get("routing")) == "replan" else "report"


def _route_after_replan(state: AgentState) -> str:
    return "execute" if str(state.get("routing")) == "execute" else "report"


def _route_after_audit(state: AgentState) -> str:
    return "report" if str(state.get("routing")) == "report" else "finalize"


def build_graph(ctx: RunContext) -> Any:
    builder: StateGraph = StateGraph(AgentState)

    builder.add_node("intake", partial(intake.intake, ctx=ctx))
    builder.add_node("inspect", partial(inspect.inspect, ctx=ctx))
    builder.add_node("plan", partial(plan.plan, ctx=ctx))
    builder.add_node("execute", partial(execute.execute, ctx=ctx))
    builder.add_node("repair_step", partial(repair_step.repair_step, ctx=ctx))
    builder.add_node("verify", partial(verify.verify, ctx=ctx))
    builder.add_node("replan", partial(replan.replan, ctx=ctx))
    builder.add_node("report", partial(report.report, ctx=ctx))
    builder.add_node("audit", partial(audit.audit, ctx=ctx))
    builder.add_node("finalize", partial(finalize.finalize, ctx=ctx))
    builder.add_node("fail", partial(fail.fail, ctx=ctx))

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "inspect")
    builder.add_edge("inspect", "plan")
    builder.add_edge("plan", "execute")
    builder.add_conditional_edges("execute", _route_after_execute, EXECUTE_ROUTES)
    builder.add_conditional_edges("repair_step", _route_after_repair, {"execute": "execute", "fail": "fail"})
    builder.add_conditional_edges("verify", _route_after_verify, {"replan": "replan", "report": "report"})
    builder.add_conditional_edges("replan", _route_after_replan, {"execute": "execute", "report": "report"})
    builder.add_edge("report", "audit")
    builder.add_conditional_edges("audit", _route_after_audit, AUDIT_ROUTES)
    builder.add_edge("fail", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile()
