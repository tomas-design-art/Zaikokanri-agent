"""FastAPI entrypoint."""
from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.errors import GENERIC_ERROR_MESSAGE, integrity_error_handler, validation_error_handler
from app.middleware.security import SecurityHeadersMiddleware
from app.routers import (
    adjust,
    ai,
    alerts,
    approvals,
    auth,
    disposal_requests,
    history,
    inbound,
    inventory,
    items,
    maintenance,
    orders,
    outbound,
    purchase_requests,
    stats,
    stocktake,
    users,
    vendors,
)
from app.routers import demo as demo_router

__all__ = ["app", "GENERIC_ERROR_MESSAGE"]

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("app")

app = FastAPI(
    title="在庫管理 API",
    version="0.2.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)

app.state.limiter = auth.limiter
async def rate_limit_handler(_request, _exc) -> JSONResponse:  # noqa: ANN001
    return JSONResponse(status_code=429, content={"detail": "ログインの試行が多すぎます。1分ほど待ってからもう一度お試しください"})


app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(IntegrityError, integrity_error_handler)

# CORS — explicit allow list, credentials required for cookie auth
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(SecurityHeadersMiddleware)


@app.get("/healthz", tags=["meta"])
def healthz() -> dict:
    """生存確認（プロセスが応答するか）。Render の healthCheckPath に使う。"""
    return {"ok": True, "env": settings.app_env}


@app.get("/readyz", tags=["meta"])
def readyz(db: Session = Depends(get_db)) -> JSONResponse:
    """DB まで含めて使える状態か（E-05）。"""
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        log.exception("readyz: DB check failed")
        return JSONResponse(status_code=503, content={"ok": False, "db": "error"})
    return JSONResponse(content={"ok": True, "db": "ok"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": GENERIC_ERROR_MESSAGE})


for module in (
    auth, items, inventory, history, alerts, outbound, inbound, adjust, purchase_requests,
    disposal_requests, approvals, users, stats, stocktake, ai, maintenance, demo_router, orders,
):
    app.include_router(module.router)
app.include_router(purchase_requests.candidates_router)
app.include_router(vendors.vendors_router)
app.include_router(vendors.categories_router)
app.include_router(vendors.departments_router)
