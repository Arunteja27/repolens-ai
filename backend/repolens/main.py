from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from repolens.api.routes import router as api_router
from repolens.container import build_context
from repolens.core.config import Settings
from repolens.core.logging import configure_logging, get_logger, log_event
from repolens.core.rate_limit import RateLimitDecision

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    app.state.context = build_context(settings)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="RepoLens AI", version="0.1.0", lifespan=lifespan)
    settings = Settings.from_env()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api")

    @app.middleware("http")
    async def request_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", uuid4().hex)
        request.state.request_id = request_id
        started_at = time.perf_counter()
        context = request.app.state.context
        rate_limit_decision = _check_rate_limit(request)

        if rate_limit_decision is not None and rate_limit_decision.retry_after_seconds > 0:
            response = JSONResponse(
                status_code=429,
                content=_rate_limit_payload(rate_limit_decision),
            )
            _apply_cors_headers(request, response)
            _apply_rate_limit_headers(response, rate_limit_decision)
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            response.headers["X-Request-ID"] = request_id
            context.metrics.increment(
                "rate_limit_rejections_total",
                labels={
                    "path": request.url.path,
                    "policy": rate_limit_decision.policy_name,
                },
            )
            context.metrics.increment(
                "http_requests_total",
                labels={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": "429",
                },
            )
            context.metrics.observe(
                "http_request_latency_ms",
                duration_ms,
                labels={"method": request.method, "path": request.url.path},
            )
            log_event(
                logger,
                logging.WARNING,
                "http_rate_limited",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=429,
                latency_ms=duration_ms,
                rate_limit_policy=rate_limit_decision.policy_name,
                retry_after_seconds=rate_limit_decision.retry_after_seconds,
            )
            return response

        try:
            response = await call_next(request)
        except Exception as exc:  # pragma: no cover - error path
            response = JSONResponse(status_code=500, content={"detail": str(exc)})
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        response.headers["X-Request-ID"] = request_id
        if rate_limit_decision is not None:
            _apply_rate_limit_headers(response, rate_limit_decision)
        metrics = context.metrics
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


def _check_rate_limit(request: Request) -> RateLimitDecision | None:
    context = request.app.state.context
    if context.rate_limiter is None:
        return None
    return context.rate_limiter.check(request)


def _apply_rate_limit_headers(response: Response, decision: RateLimitDecision) -> None:
    response.headers["X-RateLimit-Limit"] = str(decision.limit)
    response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
    response.headers["X-RateLimit-Policy"] = decision.policy_name
    if decision.retry_after_seconds > 0:
        response.headers["Retry-After"] = str(decision.retry_after_seconds)


def _apply_cors_headers(request: Request, response: Response) -> None:
    context = request.app.state.context
    origin = request.headers.get("Origin")
    if not origin:
        return
    allowed_origins = context.settings.cors_allowed_origins
    if "*" in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = "*"
        return
    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"


def _rate_limit_payload(decision: RateLimitDecision) -> dict[str, str | int]:
    return {
        "detail": (
            f"Rate limit exceeded for {decision.policy_name} requests. "
            f"Try again in {decision.retry_after_seconds} seconds."
        ),
        "policy": decision.policy_name,
        "retry_after_seconds": decision.retry_after_seconds,
    }
