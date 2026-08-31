from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, configs, health, repos, research, scan, subscriptions
from app.config import get_settings
from app.db import init_db

logger = logging.getLogger("skillradar")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_hits: dict[str, deque[float]] = defaultdict(deque)


def create_app() -> FastAPI:
    settings = get_settings()
    settings.data_dir()
    init_db()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list() or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if request.url.path.endswith("/health"):
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = _hits[ip]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= settings.rate_limit_per_minute:
            return JSONResponse({"code": 429, "data": None, "message": "rate limited"}, status_code=429)
        window.append(now)
        return await call_next(request)

    @app.exception_handler(HTTPException)
    async def http_exc(_, exc: HTTPException):
        return JSONResponse(
            {"code": exc.status_code, "data": None, "message": str(exc.detail)},
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unhandled(_, exc: Exception):
        logger.exception("unhandled error: %s", exc)
        return JSONResponse({"code": 500, "data": None, "message": "internal error"}, status_code=500)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(scan.router)
    app.include_router(repos.router)
    app.include_router(subscriptions.router)
    app.include_router(configs.router)
    app.include_router(research.router)

    @app.on_event("startup")
    def _start_scheduler() -> None:
        try:
            from app.scheduler.beat import start_scheduler

            if os.environ.get("SKILLRADAR_DISABLE_SCHEDULER") == "1":
                return
            start_scheduler()
        except Exception as exc:
            logger.warning("scheduler not started: %s", exc)

    return app


app = create_app()
