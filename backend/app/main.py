"""FastAPI entrypoint."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.middleware.security import SecurityHeadersMiddleware
from app.routers import adjust as adjust_router
from app.routers import ai as ai_router
from app.routers import alerts as alerts_router
from app.routers import approvals as approvals_router
from app.routers import auth as auth_router
from app.routers import categories as categories_router
from app.routers import demo as demo_router
from app.routers import departments as departments_router
from app.routers import disposal_requests as dr_router
from app.routers import history as history_router
from app.routers import inbound as inbound_router
from app.routers import inventory as inventory_router
from app.routers import items as items_router
from app.routers import maintenance as maintenance_router
from app.routers import orders as orders_router
from app.routers import outbound as outbound_router
from app.routers import purchase_requests as pr_router
from app.routers import stats as stats_router
from app.routers import stocktake as stocktake_router
from app.routers import users as users_router
from app.routers import vendors as vendors_router

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("app")

app = FastAPI(
    title="在庫管理 API",
    version="0.1.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
    openapi_url="/openapi.json",
)

# Rate limiter (from auth router)
app.state.limiter = auth_router.limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
    return {"ok": True, "env": settings.app_env}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


# Routers
app.include_router(auth_router.router)
app.include_router(items_router.router)
app.include_router(inventory_router.router)
app.include_router(history_router.router)
app.include_router(alerts_router.router)
app.include_router(outbound_router.router)
app.include_router(inbound_router.router)
app.include_router(adjust_router.router)
app.include_router(pr_router.router)
app.include_router(pr_router.candidates_router)
app.include_router(dr_router.router)
app.include_router(approvals_router.router)
app.include_router(vendors_router.router)
app.include_router(categories_router.router)
app.include_router(departments_router.router)
app.include_router(users_router.router)
app.include_router(stats_router.router)
app.include_router(stocktake_router.router)
app.include_router(ai_router.router)
app.include_router(maintenance_router.router)
app.include_router(demo_router.router)
app.include_router(orders_router.router)
