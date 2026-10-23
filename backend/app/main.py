"""FastAPI 装配：中间件、异常处理、路由挂载、启动自检。

启动顺序（lifespan）：配置日志 → 建目录 → 建表 → 清理上次进程遗留的
queued/running run（标记 failed，不伪造恢复）→ 打印一条自检日志。
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import api_router
from .config import Settings, get_settings
from .errors import AppError, ErrorBody, ErrorCode, ErrorEnvelope
from .logging_conf import configure_logging, get_logger
from .services.store import get_store

logger = get_logger(__name__)


def _envelope(code: str, message: str, details: dict | None = None, request_id: str | None = None):
    return ErrorEnvelope(
        error=ErrorBody(code=code, message=message, details=details or {}, request_id=request_id)
    ).model_dump(mode="json")


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        cfg.ensure_dirs()
        store = get_store()
        store.init_schema()
        interrupted = store.mark_interrupted_runs()
        logger.info(
            "app_startup",
            extra={
                "version": cfg.version,
                "llm_mode": cfg.resolved_llm_mode,
                "model": cfg.llm_model,
                "db": str(cfg.db_file),
                "interrupted_runs": interrupted,
            },
        )
        yield
        logger.info("app_shutdown")

    app = FastAPI(
        title="MetricMind API",
        version=cfg.version,
        description="AI Data Analyst Agent：受控工具计算 + 证据链 + 数字审计",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_crashed",
                extra={"request_id": request_id, "path": request.url.path},
            )
            raise
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response.headers["X-Request-ID"] = request_id
        if not request.url.path.startswith(("/docs", "/openapi")):
            logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": elapsed_ms,
                },
            )
        return response

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        logger.warning(
            "app_error",
            extra={"request_id": rid, "code": exc.code, "path": request.url.path},
        )
        return JSONResponse(status_code=exc.http_status, content=exc.to_envelope(rid).model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        fields = [
            {
                "loc": ".".join(str(part) for part in err.get("loc", [])),
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=400,
            content=_envelope(
                ErrorCode.VALIDATION_ERROR.value,
                "请求参数不合法",
                {"fields": fields},
                rid,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        code = ErrorCode.NOT_FOUND.value if exc.status_code == 404 else f"HTTP_{exc.status_code}"
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail), {}, rid),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        logger.exception("unhandled_error", extra={"request_id": rid, "path": request.url.path})
        return JSONResponse(
            status_code=500,
            content=_envelope(ErrorCode.INTERNAL_ERROR.value, "服务器内部错误", {}, rid),
        )

    app.include_router(api_router, prefix=cfg.api_prefix)
    return app


app = create_app()
