from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from repolens.api.routes import router as api_router
from repolens.container import build_context
from repolens.core.config import Settings
from repolens.core.logging import configure_logging, get_logger, log_event


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    app.state.context = build_context(settings)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="RepoLens AI", version="0.1.0", lifespan=lifespan)
    app.include_router(api_router, prefix="/api")

    @app.middleware("http")
    async def request_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", uuid4().hex)
        request.state.request_id = request_id
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:  # pragma: no cover - error path
            response = JSONResponse(status_code=500, content={"detail": str(exc)})
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        response.headers["X-Request-ID"] = request_id
        metrics = request.app.state.context.metrics
        metrics.increment(
            "http_requests_total",
            labels={
                "method": request.method,
                "path": request.url.path,
                "status_code": str(response.status_code),
            },
        )
        metrics.observe(
            "http_request_latency_ms",
            duration_ms,
            labels={"method": request.method, "path": request.url.path},
        )
        log_event(
            logger,
            logging.INFO,
            "http_request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=duration_ms,
        )
        return response

    @app.get("/health")
    def health():
        context = app.state.context
        return {
            "status": "ok",
            "app": context.settings.app_name,
            "embedding_provider": context.settings.embedding_provider,
            "vector_store_provider": context.settings.vector_store_provider,
            "answer_provider": context.settings.answer_provider,
        }

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics():
        return app.state.context.metrics.render_prometheus()

    return app


app = create_app()

