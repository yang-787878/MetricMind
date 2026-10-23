# Agent 工作流

> 图装配在 `app/agent/graph.py`，节点实现在 `app/agent/nodes/*.py`，运行期依赖在 `app/agent/run_context.py`。

## 1. 图结构

```text
START → intake → inspect → plan → execute
execute ↺（逐步骤）
execute ─失败可修复→ repair_step → execute（重试或跳过）
execute ─不可恢复→ fail → finalize
execute ─全部完成→ verify
verify ─有失败/无证据 且 重规划有余量→ replan → execute
verify ─否则→ report → audit
audit ─覆盖率 0.6–0.9 且首次→ report（重写）
audit ─覆盖率 ≥0.9 或 二次仍不足→ finalize
finalize → END
```

`AgentState`（`app/agent/state.py`）字段：
`run_id / dataset_id / question / mode / dataset_meta / field_summary / plan / plan_version / step_index /
steps / step_results / evidence_pool / replan_count / repair_count / audit_attempts / warnings /
verification / draft / report / status / error / routing / failed_step / token_usage`。

节点只返回增量 dict；列表字段返回完整新列表（不依赖 reducer）。

## 2. 节点输入输出

| 节点 | 读 | 写 | 副作用（事件） |
|---|---|---|---|
| `intake` | run/dataset 记录、question | `dataset_meta`、`status` | `run_started` |
| `inspect` | `dataset_id` | `dataset_meta.columns/candidate_*`、`quality`、`field_summary` | `tool_call_*`（inspect/profile）、`dataset_inspected` |
| `plan` | `dataset_meta`、工具 schema、预算 | `plan`、`steps`、`step_index=0` | `plan_created` |
| `execute` | `steps[step_index]`、`step_results` | `steps`（状态/工具调用记录）、`step_index`、`step_results` | `step_started`、`tool_call_*`、`step_completed` |
| `repair_step` | 失败步骤 + error | 修正后的 `tool_args_hint` 或标记 skipped | —（结果由下一次 execute 反映） |
| `verify` | steps 状态、证据数量 | `routing` | — |
| `replan` | 失败步骤列表、预算 | 新 `plan`（plan_version+1）、新 `steps` | `replan_requested`（余额用尽时 `budget_warning`） |
| `report` | 证据池、质量问题、审计反馈 | `draft` | — |
| `audit` | `draft.claims` | `verification`、`routing`、`status` | `verification_completed` |
| `finalize` | 全部状态 + 证据 | `report`、`status` | `report_created` + 终态事件 |
| `fail` | `error`、失败步骤 | `status=failed` | — |

## 3. 提示词全文

三份提示词在 `app/llm/prompts/*.md`，由 `app/llm/prompt_loader.py` 读取；动态内容（字段、工具 schema、证据）
由代码序列化成 JSON 放进 user message，**提示词里不写死任何业务数据**。

### 3.1 `plan.md`

```markdown
# 角色

你是 MetricMind 的分析规划器。你的唯一任务是：根据数据集字段摘要与可用工具，产出一个**可执行的结构化分析计划**。

# 输入

用户消息是一段 JSON，包含：
- `question`：用户的分析问题；
- `dataset`：数据集行数、列数与每列的 `name / dtype / semantic_type / null_rate / distinct_count / sample_values`；
- `tools`：可用工具的 JSON Schema（参数必须严格符合）；
- `budget`：`max_steps` / `max_tool_calls` / `max_replans`。

# 输出

只输出一个 JSON 对象，不要 Markdown 代码块，不要解释文字。结构：

{
  "objective": "一句话说明这次分析要回答什么",
  "required_fields": ["真正用到的列名"],
  "assumptions": ["口径假设"],
  "steps": [
    {
      "step_id": "s1",
      "title": "步骤标题（不超过 40 字）",
      "intent": "这一步想确认什么",
      "tool": "工具名，必须是给定工具之一",
      "tool_args_hint": { 严格符合该工具的参数 schema },
      "expected_output": "预期产出",
      "validation": "如何验证这一步的数值可信"
    }
  ],
  "risks": ["可能失败的点"],
  "out_of_scope": ["问题要求但数据不支持的部分"]
}

# 硬性要求

1. `step_id` 从 `s1` 连续编号，最多 `max_steps` 个步骤。
2. `tool` 只能取给定工具名；`tool_args_hint` 必须能被该工具的 schema 校验通过（不要臆造字段，不要用 dataset 里不存在的列）。
3. 至少一步使用 `calculate_metrics`，并把关键指标算法（kind / column / group_by / date_column / period / agg）写清楚。
4. 需要图表时使用 `create_chart`，其 `from_result_id` 写占位符：`"$step:s1"` 表示引用 s1 步骤的结果，`"$last_result"` 表示引用最近一次成功的工具结果。
5. 若问题需要的字段在 `dataset` 中不存在，必须写进 `out_of_scope` 并降低目标，**不得虚构字段**。
6. 数值必须由工具计算；不要在计划里写任何具体数字结论。

# 禁止事项

- 禁止输出 Markdown 代码块、注释、前后缀说明。
- 禁止编造字段名、工具名、参数名。
- 禁止在计划中给出未计算的数字（例如"下降 18%"）。
- 禁止假设具体业务领域（不要预设这是销售数据）。
```

### 3.2 `repair.md`

```markdown
# 角色

你是 MetricMind 的步骤修复器。某一步工具调用失败，你要把它的参数改成**可执行**的形式。

# 输入

用户消息是 JSON：`step`（原步骤）、`tool_schema`（该工具的参数 schema）、`error`（错误码、消息、hint）、`dataset`（真实字段清单）、`available_results`（已有 result_id 列表）。

# 输出

只输出一个 JSON 对象：`{"step_id": "...", "tool": "...", "tool_args_hint": {...}, "reason": "一句话说明改了什么"}`。

# 硬性要求

1. 列名必须来自 `dataset.columns`，不得虚构；错误为 `INVALID_COLUMN` 时优先改用 `error.available` 中的列。
2. 参数必须符合 `tool_schema`，不要新增未知字段。
3. 错误为 `SQL_REJECTED` 时，改写成对视图 `data` 的单条只读 SELECT。
4. 错误为 `EMPTY_RESULT` 时，放宽筛选条件或改用其它维度，不要编造数据。
5. 若该步骤确实无法修复，输出 `{"step_id": "...", "tool": null, "reason": "无法修复的原因"}`。

# 禁止事项

- 禁止输出 Markdown 代码块或解释性文字。
- 禁止把失败原因掩盖成"成功"。
- 禁止在参数里写具体统计结果。
```

### 3.3 `report.md`

```markdown
# 角色

你是 MetricMind 的报告撰写者。你只能使用给定的证据写作，**不能自己算数**。

# 输入

用户消息是 JSON：
- `question`：用户问题；
- `objective`：本次分析目标；
- `evidence`：证据池，每项含 `result_id`、`tool`、`step_id`、`numbers`、`tables`；
- `data_quality`：数据质量问题清单；
- `unsupported_claims`：上一轮审计未通过的数字（如有）；
- `business_context`：无（保持数据集无关性，不要假设行业）。

# 输出

只输出一个 JSON 对象：

{
  "title": "报告标题",
  "headline": "一句话结论，包含关键数字并标注证据编号",
  "sections": [
    {"heading": "小标题", "body": "结论正文，数字后带 [e1] 形式的证据编号", "evidence_ids": ["res_xxx"]}
  ],
  "claims": [
    {"claim_id": "c1", "text": "一条可核验的数字结论", "numbers": [{"value": 12.3, "unit": "%"}], "evidence_ids": ["res_xxx"]}
  ],
  "limitations": ["数据或方法上的限制"],
  "next_steps": ["下一步建议"]
}

# 硬性要求

1. 每个数字必须能在 `evidence.numbers` 中找到，且必须带 `evidence_ids`。
2. `claims` 至少包含 headline 里的数字；`numbers[].value` 用证据里的原始数值（比率用小数或百分数皆可，但要与证据一致）。
3. 无法用证据支撑的判断，只能写成定性假设并放进 `limitations`。
4. 数据质量问题会影响结论时，要在 `limitations` 里明确说明影响。

# 禁止事项

- 禁止编造 `result_id`。
- 禁止输出 Markdown 代码块、HTML 或任何解释性前后缀。
- 禁止写入证据中不存在的数字（包括四舍五入后的"差不多"数字）。
- 禁止假设数据集属于某个行业；只能使用字段本身的含义。
```

## 4. 预算策略

| 预算 | 默认 | 检查点 | 耗尽行为 |
|---|---|---|---|
| `max_steps` | 10 | `execute` 每步开始前 | `budget_warning(max_steps)` → `finalize(partial)` |
| `max_tool_calls` | 16 | `RunContext.call_tool` 每次调用前 | `budget_warning(max_tool_calls)` → 抛 `BudgetExhausted` → `finalize(partial)` |
| `max_replans` | 2 | `verify` / `replan` | 不再重规划，直接报告（`partial`） |
| 单工具次数 | 见 TOOLS | `registry.execute_tool` | `BUDGET_EXCEEDED` 信封，节点按失败处理 |
| 单工具超时 | 15–30s | `asyncio.wait_for` | `TOOL_TIMEOUT`（可重试） |
| 整体超时 | 240s | `runner._execute` | `failed(RUN_TIMEOUT)` |
| 计划步骤数 | — | `plan._validate_steps` | 截断并 warning，不整体失败 |

计划步骤数超过 `max_steps` 时是**截断**而不是失败：预算的意义是限制执行量，不是让分析直接崩掉。

## 5. 重规划触发条件

`verify` 节点在以下任一情况进入 `replan`（且 `replan_count < max_replans`）：

1. 存在 `status in {failed, skipped}` 的步骤；
2. 整个运行没有产生任何证据（`evidence.all_ids()` 为空）。

`replan` 的产出：

- Demo 模式：用同一套字段规则重建计划，并**移除失败步骤使用的工具**，避免同样的失败再来一次；
- Live 模式：把失败步骤（step_id / tool / error）作为反馈重新请求计划。

若重规划后没有可执行步骤，或余额用尽，直接进入 `report` 并标记 `partial`。

## 6. 失败降级路径

| 场景 | 行为 | 代码位置 |
|---|---|---|
| 计划输出非法 JSON | 回喂校验错误重试 1 次；仍失败 → `LLM_INVALID_OUTPUT` | `nodes/plan.py::llm_plan` |
| 单步参数错误 | `repair_step` 用错误原文修正 1 次；失败则跳过该步并记 warning | `nodes/repair_step.py` |
| 查询 0 行 | 工具返回 `ok=true` + warning；计划可重规划 | `tools/query_data.py` |
| SQL 被拦截 | `SQL_REJECTED` 信封 + hint；repair 可改写 | `services/sql_guard.py` |
| 工具崩溃 | `INTERNAL_TOOL_ERROR`（可重试），run 不会崩 | `agent/registry.py` |
| LLM 超时/429/5xx | 0.5/1.5/4s 退避 + 抖动，最多 2 次；最终 `failed(LLM_UNAVAILABLE)` | `llm/openai_client.py` |
| 报告叙述失败 | 退回 `demo_planner` 模板，状态 `partial`，limitations 注明 | `nodes/report.py` |
| 审计覆盖率 0.6–0.9 | 带失败清单重写一次报告 | `nodes/audit.py` |
| 审计仍 <0.9 或 <0.6 | 未通过 claim 降级进 limitations，状态 `partial` | `services/report_builder.py` |
| 用户取消 | 节点间检查点抛 `RunCancelled`，runner 写 `cancelled`，事件/证据保留 | `agent/run_context.py` |
| 进程重启 | 遗留 `queued/running` → `failed(RUN_INTERRUPTED)` | `services/store.py::mark_interrupted_runs` |

## 7. 审计判定（与任务书字面差异见 DECISIONS D18）

- 从 `evidence_ids` 对应 payload 递归取数（含分组值、KPI、表格单元格）；
- 归一化：去千分位、`%` 与小数互认、保留 6 位；
- `|claimed - v| ≤ max(0.5%·|v|, 1e-9)` → `supported`；
- 有候选值但都不满足 → `unsupported`，附最接近值；
- 证据存在但没有任何数值 → `unverifiable`；
- 无 `evidence_ids` / 证据不存在 → `unsupported`；
- 同一 claim 任一数字失败 → 整条 `unsupported`，取第一个失败数字。
