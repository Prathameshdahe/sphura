"""Sphura API entry point. Run: uvicorn app.main:app --reload --port 8000 (from backend/)."""
from __future__ import annotations

import importlib
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.db.base import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sphura")

app = FastAPI(
    title="Sphura API",
    version=settings.version,
    docs_url="/api/docs" if settings.environment != "production" else None,
    openapi_url="/api/openapi.json" if settings.environment != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,  # explicit list — never "*" with credentials
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_log(request: Request, call_next):  # noqa: ANN001
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["x-request-id"] = rid
    if request.url.path.startswith("/api"):
        log.info("%s %s %s %.0fms rid=%s", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - start) * 1000, rid)
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # Contract: errors are always {"detail": "<string>"}
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []) if p not in ("body", "query", "path"))
        parts.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
    return JSONResponse(status_code=422, content={"detail": "; ".join(parts) or "Invalid request"})


@app.exception_handler(Exception)
async def unhandled_error(_request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Routers are discovered by module name so independent modules can be added without editing this file.
ROUTER_MODULES = [
    "app.api.auth",
    "app.api.health",
    "app.api.models",
    "app.api.conversations",
    "app.api.chat",
    "app.api.documents",
    # finance build
    "app.api.agent",
    "app.api.market",
    "app.api.voice",
    "app.api.memory",
    "app.api.ml",
    "app.api.finance",
    "app.api.feedback",
    "app.api.verify",
]

for module_name in ROUTER_MODULES:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            continue  # not built yet
        raise
    app.include_router(module.router, prefix="/api")
    log.info("router loaded: %s", module_name)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    from app.api.auth import bootstrap_admin

    bootstrap_admin()
    log.info("Sphura API %s ready (db=%s)", settings.version, settings.sqlalchemy_url.split("://")[0])


@app.on_event("startup")
async def _agent_startup() -> None:
    # The finance graph's SQLite checkpointer and the local-model warm-up (app/agent/lifecycle.py).
    from app.agent import lifecycle

    try:
        await lifecycle.startup()
    except Exception:  # noqa: BLE001 — the agent must never stop the API from starting
        log.exception("agent lifecycle startup failed")


@app.on_event("shutdown")
async def _agent_shutdown() -> None:
    from app.agent import lifecycle

    await lifecycle.shutdown()
