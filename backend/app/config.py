"""Application configuration via pydantic-settings.

All secrets MUST come from environment variables / .env (never hardcoded).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- App ----
    app_env: str = "development"
    app_name: str = "zaikokanri-backend"
    log_level: str = "INFO"
    demo_mode: bool = False

    # ---- Database ----
    # 未設定なら backend/zaiko_app.db（SQLite）。本番は DATABASE_URL で PostgreSQL を渡す。
    database_url: str = Field(
        default_factory=lambda: f"sqlite:///{(BACKEND_DIR / 'zaiko_app.db').as_posix()}"
    )

    # ---- JWT ----
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_min: int = 30
    jwt_refresh_ttl_days: int = 14
    cookie_domain: str = ""
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    # ---- CORS ----
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ---- AI ----
    ai_enabled: bool = False
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # ---- Rate Limit ----
    # 会社のネットワークでは全員が同じIPに見えるため、IP単位の制限は緩めにする（A-07）
    rate_limit_login: str = "30/minute"
    # 同じアカウントで続けて失敗したらロックする（G-02）
    login_max_failures: int = 10
    login_lock_minutes: int = 15

    # ---- Business constants (legacy compat) ----
    outbound_max: int = 1000
    inbound_max: int = 10000
    warning_threshold: int = 100
    undo_minutes: int = 10

    # ---- Paths ----
    font_path: Path = BACKEND_DIR / "fonts" / "NotoSansJP-Regular.ttf"
    font_name: str = "NotoSansJP"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}


WEAK_SECRETS = {"change-me", "change-me-please-use-openssl-rand-hex-32"}


def validate_settings(s: Settings) -> Settings:
    """本番設定の確認（G-09）。危険なら起動しない、注意が要るなら警告する。"""
    if s.is_production:
        if s.jwt_secret in WEAK_SECRETS or len(s.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be set to a strong value (>=32 chars) in production")
        if not s.cookie_secure:
            logging.getLogger("security").warning(
                "APP_ENV=production but COOKIE_SECURE=false: login cookies are sent without HTTPS. "
                "Use HTTPS and set COOKIE_SECURE=true unless this is a closed on-premise network."
            )
    return s


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return validate_settings(Settings())


settings = get_settings()
