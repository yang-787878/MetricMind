"""API 路由聚合：main.py 只挂一个 router，保持装配职责单一。"""

from __future__ import annotations

from fastapi import APIRouter

from . import datasets, events, runs, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(datasets.router)
api_router.include_router(runs.router)
api_router.include_router(events.router)

__all__ = ["api_router"]
