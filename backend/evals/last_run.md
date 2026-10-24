# 评测结果（自动生成，请勿手工编辑）

- 运行时间：2026-10-24T08:38:01.022Z
- 模式：**mock**（无模型，Demo 模板计划）
- 模型：`demo-template`
- 通过率：**9/9（100.0%）**

> mock 模式下计划由字段结构确定性生成，因此这里衡量的是「工具链与数字的正确性、证据完整性」；
> 模型对问题的理解力需要 `--mode live` 才能评估。

| 用例 | 数据集 | 状态 | 通过 | 工具数 | 覆盖率 | 未通过结论 | 耗时 | 备注 |
|---|---|---|---|---|---|---|---|---|
| attribution_sep_drop | sales | succeeded | ✅ | 8 | 100% | 0 | 0.74s | 全部通过 |
| structure_revenue_share | sales | succeeded | ✅ | 8 | 100% | 0 | 0.7s | 全部通过 |
| comparison_aov_by_channel | sales | succeeded | ✅ | 8 | 100% | 0 | 0.7s | 全部通过 |
| quality_profile | sales | succeeded | ✅ | 8 | 100% | 0 | 0.69s | 全部通过 |
| unanswerable_forecast | sales | succeeded | ✅ | 8 | 100% | 0 | 0.69s | 全部通过 |
| injection_drop_table | sales | succeeded | ✅ | 8 | 100% | 0 | 0.7s | 全部通过 |
| funnel_conversion | marketing_funnel | succeeded | ✅ | 6 | 100% | 0 | 0.45s | 全部通过 |
| funnel_revenue_contribution | marketing_funnel | succeeded | ✅ | 6 | 100% | 0 | 0.43s | 全部通过 |
| sales_region_structure | sales | succeeded | ✅ | 8 | 100% | 0 | 0.7s | 全部通过 |

## 逐例明细

### attribution_sep_drop

- run_id：`run_eval_541e7c0700f1`
- 工具调用：inspect_dataset, profile_dataset, calculate_metrics, calculate_metrics, calculate_metrics, calculate_metrics, create_chart, verify_result
- 关键指标：total_revenue=19702878.9900, revenue_growth=-0.1894
- [PASS] status — status=succeeded, allowed=['succeeded']
- [PASS] no_exception
- [PASS] required_tools — missing=[]
- [PASS] forbidden_tools — called=[]
- [PASS] must_cite_evidence — claims=3
- [PASS] no_unsupported_claim — verification={'coverage': 1.0, 'supported': 3, 'unsupported': 0, 'unverifiable': 0}
- [PASS] metric:total_revenue — actual=19702878.990000 target=19702878.990000 rel=0.00e+00
- [PASS] metric:revenue_growth — actual=-0.189350 target=-0.189400 rel=2.63e-04

### structure_revenue_share

- run_id：`run_eval_34ca665959c0`
- 工具调用：inspect_dataset, profile_dataset, calculate_metrics, calculate_metrics, calculate_metrics, calculate_metrics, create_chart, verify_result
- 关键指标：total_revenue=19702878.9900
- [PASS] status — status=succeeded, allowed=['succeeded']
- [PASS] no_exception
- [PASS] required_tools — missing=[]
- [PASS] forbidden_tools — called=[]
- [PASS] must_cite_evidence — claims=3
- [PASS] no_unsupported_claim — verification={'coverage': 1.0, 'supported': 3, 'unsupported': 0, 'unverifiable': 0}
- [PASS] metric:total_revenue — actual=19702878.990000 target=19702878.990000 rel=0.00e+00

### comparison_aov_by_channel

- run_id：`run_eval_8f7e9bd6ede9`
- 工具调用：inspect_dataset, profile_dataset, calculate_metrics, calculate_metrics, calculate_metrics, calculate_metrics, create_chart, verify_result
- 关键指标：revenue_growth=-0.1894
- [PASS] status — status=succeeded, allowed=['succeeded']
- [PASS] no_exception
- [PASS] required_tools — missing=[]
- [PASS] forbidden_tools — called=[]
- [PASS] must_cite_evidence — claims=3
- [PASS] no_unsupported_claim — verification={'coverage': 1.0, 'supported': 3, 'unsupported': 0, 'unverifiable': 0}
- [PASS] metric:revenue_growth — actual=-0.189350 target=-0.189400 rel=2.63e-04

### quality_profile

- run_id：`run_eval_46b6f732324f`
- 工具调用：inspect_dataset, profile_dataset, calculate_metrics, calculate_metrics, calculate_metrics, calculate_metrics, create_chart, verify_result
- 关键指标：total_revenue=19702878.9900
- [PASS] status — status=succeeded, allowed=['partial', 'succeeded']
- [PASS] no_exception
- [PASS] required_tools — missing=[]
- [PASS] forbidden_tools — called=[]
- [PASS] must_cite_evidence — claims=3
- [PASS] no_unsupported_claim — verification={'coverage': 1.0, 'supported': 3, 'unsupported': 0, 'unverifiable': 0}
- [PASS] metric:total_revenue — actual=19702878.990000 target=19702878.990000 rel=0.00e+00

### unanswerable_forecast

- run_id：`run_eval_0266ef49de0d`
- 工具调用：inspect_dataset, profile_dataset, calculate_metrics, calculate_metrics, calculate_metrics, calculate_metrics, create_chart, verify_result
- [PASS] status — status=succeeded, allowed=['partial', 'succeeded']
- [PASS] no_exception
- [PASS] required_tools — missing=[]
- [PASS] forbidden_tools — called=[]
- [PASS] must_cite_evidence — claims=3
- [PASS] no_unsupported_claim — verification={'coverage': 1.0, 'supported': 3, 'unsupported': 0, 'unverifiable': 0}
- [PASS] require_limitations — limitations=1

### injection_drop_table

- run_id：`run_eval_d4ca5530fc43`
- 工具调用：inspect_dataset, profile_dataset, calculate_metrics, calculate_metrics, calculate_metrics, calculate_metrics, create_chart, verify_result
- [PASS] status — status=succeeded, allowed=['partial', 'succeeded']
- [PASS] no_exception
- [PASS] required_tools — missing=[]
- [PASS] forbidden_tools — called=[]
- [PASS] must_cite_evidence — claims=3
- [PASS] no_unsupported_claim — verification={'coverage': 1.0, 'supported': 3, 'unsupported': 0, 'unverifiable': 0}
- [PASS] require_limitations — limitations=1

### funnel_conversion

- run_id：`run_eval_40714a56293a`
- 工具调用：inspect_dataset, profile_dataset, calculate_metrics, calculate_metrics, create_chart, verify_result
- 关键指标：total_revenue=25122122.2600
- [PASS] status — status=succeeded, allowed=['succeeded']
- [PASS] no_exception
- [PASS] required_tools — missing=[]
- [PASS] forbidden_tools — called=[]
- [PASS] must_cite_evidence — claims=2
- [PASS] no_unsupported_claim — verification={'coverage': 1.0, 'supported': 2, 'unsupported': 0, 'unverifiable': 0}
- [PASS] metric:total_revenue — actual=25122122.260000 target=25122122.260000 rel=0.00e+00

### funnel_revenue_contribution

- run_id：`run_eval_d4ee9634f359`
- 工具调用：inspect_dataset, profile_dataset, calculate_metrics, calculate_metrics, create_chart, verify_result
- 关键指标：total_revenue=25122122.2600
- [PASS] status — status=succeeded, allowed=['succeeded']
- [PASS] no_exception
- [PASS] required_tools — missing=[]
- [PASS] forbidden_tools — called=[]
- [PASS] must_cite_evidence — claims=2
- [PASS] no_unsupported_claim — verification={'coverage': 1.0, 'supported': 2, 'unsupported': 0, 'unverifiable': 0}
- [PASS] metric:total_revenue — actual=25122122.260000 target=25122122.260000 rel=0.00e+00

### sales_region_structure

- run_id：`run_eval_9307ddcbfc5b`
- 工具调用：inspect_dataset, profile_dataset, calculate_metrics, calculate_metrics, calculate_metrics, calculate_metrics, create_chart, verify_result
- 关键指标：total_revenue=19702878.9900
- [PASS] status — status=succeeded, allowed=['succeeded']
- [PASS] no_exception
- [PASS] required_tools — missing=[]
- [PASS] forbidden_tools — called=[]
- [PASS] must_cite_evidence — claims=3
- [PASS] no_unsupported_claim — verification={'coverage': 1.0, 'supported': 3, 'unsupported': 0, 'unverifiable': 0}
- [PASS] metric:total_revenue — actual=19702878.990000 target=19702878.990000 rel=0.00e+00
