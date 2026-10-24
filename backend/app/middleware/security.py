"""Security middleware: 他サイトからの書き込みの拒否（G-07）と、セキュリティヘッダー（CSP, HSTS, X-Frame-Options 等）。"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # CSRF の二重の備え：ブラウザが「他サイトからの送信」と示した書き込みは受け付けない。
        # 画面は Next.js の rewrites 経由（同じオリジン）なので same-origin になる。ヘッダーを送らない
        # 古いブラウザ・サーバー間の呼び出しは対象外（SameSite=Lax の Cookie で守る）。
        if request.method in WRITE_METHODS and request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse(status_code=403, content={"detail": "外部のサイトからの操作は受け付けません"})
        response = await call_next(request)
        # OWASP recommended headers
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault("Cache-Control", "no-store")
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
            # API serves JSON only — strict CSP.
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        return response
