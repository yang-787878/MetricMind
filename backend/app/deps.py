"""请求级依赖：settings / store / request_id 只在这里装配，方便测试覆盖。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from .config import Settings, get_settings
from .services.store import Store, get_store


def settings_dep() -> Settings:
    return get_settings()


def store_dep() -> Store:
    return get_store()


def request_id_dep(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


SettingsDep = Annotated[Settings, Depends(settings_dep)]
StoreDep = Annotated[Store, Depends(store_dep)]
RequestIdDep = Annotated[str, Depends(request_id_dep)]
