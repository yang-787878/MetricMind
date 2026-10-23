# 高频追问与答法（每条都指向真实代码）

> 回答原则：先说机制，再指文件和函数，最后给证据（测试名 / 数字）。不知道的就说不知道，并说明怎么补。

### 1. 怎么防止模型编数字？

三道程序化关卡，不依赖模型自觉：

1. `app/agent/nodes/plan.py::_plan_payload` 只把字段摘要与样例值给模型，不给 DataFrame；
2. `app/agent/tools/create_chart.py::run` 只接受 `from_result_id`，没有数据数组入口；
3. `app/services/verifier.py::verify_claims` 把每个 claim 的每个数字与证据比对（0.5% 容差），
   `app/services/report_builder.py::build_report` 把 KPI/claim 的展示值用证据值重新格式化，
   未通过的 claim 会被降级写进 `limitations`（`report_builder` 里 `unsupported` 分支）。

证据：`tests/test_verifier.py`（9 例）、`tests/test_graph_happy_path.py` 断言 KPI 等于金标准。

### 2. SQL 越权怎么防？

四层：`app/services/sql_guard.py::validate_sql`（sqlglot AST：单语句、顶层 SELECT、写节点黑名单、
表名必须为 `data`、函数黑名单、系统对象、外层 LIMIT 包装）+ `app/services/engine.py::DuckDBSession.__init__`
（`SET enable_external_access=false`、禁自动安装/加载扩展、只 `register('data', frame)`）+
`app/tools/query_data.py` 先守卫后执行 + 超时 `interrupt()`。

证据：`tests/test_sql_guard.py` 39 例，含 `read_csv('/etc/passwd')`、`ATTACH`、`COPY`、注释注入、CTE/UNION 放行。

### 3. 为什么不用 AutoGen / CrewAI 这类多 Agent 框架？

需求是“单条有状态、可审计的工作流”，不是“多角色协作”。多 Agent 互评会引入不可控与非确定性，
与“每个数字可回溯”目标冲突。LangGraph 的 `StateGraph` 提供节点 + 条件边 + 状态，
正好表达 execute → repair → verify → replan 的循环；节点是普通 async 函数（`app/agent/graph.py`），
单测可直接 `await`（`tests/test_graph_replan.py`）。

### 4. 工具调用失败怎么恢复？

分层：

- 参数错误/列不存在/空结果 → `app/agent/nodes/repair_step.py`（Demo 模板或 repair 提示词）修正一次，重试同一步；
- 修不好 → 标记 `skipped` 并记 warning，`verify` 节点看到失败步骤触发 `replan`；
- 重规划余额用完 → 带着已有证据直接出报告，状态 `partial`；
- 不可恢复（`DATASET_NOT_FOUND`）→ `fail` → `finalize(failed)`。

证据：`tests/test_graph_replan.py::test_replan_recovers_from_invalid_column`、
`test_unrecoverable_failure_marks_failed`、`tests/test_tools.py` 的失败矩阵。

### 5. 如何评估 Agent 效果？

`backend/evals/cases.json` 7 条用例（归因/结构/对比/质量/不可答/越权/第二数据集），
`backend/evals/run.py` 逐例跑完整图，比对：必需工具 ⊆ 已调用工具、禁用工具未调用、
`expected_metrics` 与工具值相对误差 ≤0.5%、必须引用证据且无 `unsupported`。
mock 模式 7/7（100%），结果写在 `backend/evals/last_run.md`；live 模式需 Key（本环境未跑，README 已注明）。

补充：`scripts/compute_expected.py` 用纯 pandas 独立算金标准（不 import 后端），
交叉验证工具算得对不对——阶段 2 做过 19 项比对，最大相对差 4e-4。

### 6. 0.5% 的误差阈值怎么来的？

工具结果在 `app/services/metrics.py` 里 round 到 6 位；报告展示层会四舍五入到 1 位小数（`format_value`）。
0.5% 能容忍展示层舍入（例如 18.935% → 18.9%），又能拦住“编一个看起来差不多的数”。
常量在 `app/services/verifier.py::RELATIVE_TOLERANCE = 0.005`，与文档里的 0.5% 同名同值。
2% 超差仍判 `unsupported`（附最接近值），这是 `docs/DECISIONS.md` D18 记录的取舍。

### 7. 预算超了怎么办？

`app/agent/context.py` 管工具调用，`app/agent/run_context.py::call_tool` 在每次调用前检查
`max_tool_calls`，`execute` 节点检查 `max_steps`，`verify`/`replan` 检查 `max_replans`。
任一超限：发 `budget_warning` 事件 → 走 `finalize(partial)`，并在 `limitations` 写入
“因执行预算耗尽，分析未覆盖全部维度”。证据：`tests/test_graph_replan.py::test_budget_exhaustion_is_partial`。

### 8. 怎么扩展到多表？

当前约束是单表（视图 `data`）。扩展点：

1. `loader` 支持多文件 → 每张表注册为 `data_<name>`；
2. `sql_guard.ALLOWED_TABLE` 改为白名单集合（`ALLOWED_SCHEMAS`/`allowed_tables`），
   并在 `DuckDBSession` 里 `register` 多张视图；
3. `inspect_dataset` 与计划提示词带表关系（join key 发现）；
4. `result_id` 与报告链路不需要改。

代价：SQL 守卫的“只允许 data”要变成“只允许登记过的表”，白名单要来自会话而非常量。

### 9. 怎么降低延迟与成本？

- 计划/修复/报告三处 LLM 调用，其余全是本地计算；Demo 模式 0 次模型调用（约 0.7s 完成全流程）。
- 证据池只给摘要（`numbers` / `tables` 截断），不把 200 行表格塞进上下文（`nodes/report.py::_evidence_items`）。
- 单工具调用有独立上限（防止模型反复重试烧预算），预算耗尽立刻收口。
- 前端图表用 SVG/Recharts 本地渲染，无服务端图片生成。

### 10. 如何保证可复现？

- 示例数据固定 seed，两次生成 sha256 一致（`scripts/generate_sample_data.py`）；
- 金标准用纯 pandas 独立计算（`scripts/compute_expected.py` → `data/expected_answers.json`）；
- Demo 模式无模型参与，同一数据集同一问题两次运行报告逐字段一致（除时间戳）：
  `tests/test_demo_deterministic.py`；
- 事件 `seq` 事务内自增，重放顺序确定（`services/store.py::append_event`）。

### 11. 图表数据可信吗？

`create_chart` 只能引用当前 run 证据池里的 `result_id`（不存在 → `RESULT_NOT_FOUND`），
`x/y/series` 必须是该结果集真实列（否则 `INVALID_COLUMN` 并列出可选列）。
前端 `ChartCard` 只渲染 `ChartSpec.data`，导出侧 `render_svg` 用同一份数据。
测试：`tests/test_tools.py::test_create_chart_requires_existing_result`、
`test_create_chart_invalid_column`；导出：`tests/test_report_export.py` 断言 SVG 数 = 图表数。

### 12. 并发怎么处理？

`app/runner.py::RunManager` 用 `asyncio.Semaphore(max_concurrent_runs=2)`，超出进 `queued`；
每个 run 一条后台 task，取消用 `asyncio.Event` 在节点间检查；DuckDB 会话按 `(run_id, dataset_id)` 隔离，
run 结束 `close_run`。SQLite 用 WAL + `BEGIN IMMEDIATE` 保证 `seq` 不自增冲突。
请求侧 `POST /runs` 有 6 次/分钟限流（`app/api/runs.py::_check_rate_limit`）。

### 13. SSE 断线怎么办？

服务端：事件先落库再发布（`run_context.emit`），所以任何时刻都可以用 `after_seq` 续播；
`GET /runs/{id}/events` 是轮询兜底。前端：`src/hooks/useRunStream.ts` 连续两次错误后切轮询，
顶栏提示“实时连接已断开，正在轮询”，并按 `seq` 去重（`src/lib/sse.ts`）。
测试：`frontend/tests/use-run-stream.test.tsx`（去重 + 降级）。

### 14. Demo 模式是不是在造假？

不是。Demo 模式仍然**真实调用工具**：计划由字段结构生成、计算在 DuckDB/pandas、
证据链与数字审计完全一致，只是“叙述”来自模板而不是模型。
`tests/test_demo_deterministic.py::test_demo_mode_uses_real_tools` 断言 `tool_call_succeeded ≥ 3`
且 `results` 表有记录；报告的 `narrative_source="template"` 会显示在数据里，前端标注 Demo mode。

### 15. 如何加一个新工具？

三步（详见 `docs/ARCHITECTURE.md` 第 5 节）：在 `app/agent/tools/` 新增模块并暴露
`NAME/DESCRIPTION/Input/TIMEOUT_S/MAX_CALLS/PRODUCES_RESULT/run(ctx,args)`；在 `tools/__init__.py`
与 `agent/registry.py` 各加一行；补 `tests/test_tools.py` 用例。计划提示词会自动带上新工具的 JSON Schema
（`registry.tool_schemas()` 由 Pydantic 生成，不手写第二份）。
