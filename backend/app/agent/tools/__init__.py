"""七个工具（§5.2）各自的实现文件。

每个模块暴露一致的结构，registry 只按约定装配：
`NAME / DESCRIPTION / Input / TIMEOUT_S / MAX_CALLS / PRODUCES_RESULT / run(ctx, args)`。
"""

from __future__ import annotations

from . import (
    calculate_metrics,
    create_chart,
    export_report,
    inspect_dataset,
    profile_dataset,
    query_data,
    verify_result,
)

__all__ = [
    "inspect_dataset",
    "profile_dataset",
    "query_data",
    "calculate_metrics",
    "create_chart",
    "verify_result",
    "export_report",
]
