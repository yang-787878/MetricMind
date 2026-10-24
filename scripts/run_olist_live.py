"""Run one live analysis on the Olist sample through the real graph.

This is a smoke run, not a benchmark: it answers whether the deterministic tool
chain plus the live planner can handle a 112k-row table end to end.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import evals.run as runner  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.services.store import get_store  # noqa: E402

CASE = {
    "case_id": "olist_aug_drop",
    "dataset": "olist_orders",
    "question": "为什么 2018 年 8 月销售额相比 7 月下降了？",
    "mode": "live",
    "expect": {},
}


def main() -> int:
    settings = get_settings()
    summary = asyncio.run(
        runner.run_cases(
            settings=settings,
            store=get_store(),
            mode="live",
            cases=[CASE],
        )
    )
    item = summary["results"][0]
    keep = {
        key: item[key]
        for key in (
            "case_id",
            "status",
            "passed",
            "tools",
            "coverage",
            "unsupported_claims",
            "elapsed_s",
            "prompt_tokens",
            "completion_tokens",
            "actions",
            "error",
            "run_id",
        )
    }
    print(json.dumps(keep, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
