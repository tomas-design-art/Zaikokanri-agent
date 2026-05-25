"""Application configuration via pydantic-settings.

All secrets MUST come from environment variables / .env (never hardcoded).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
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
    # Default to the legacy SQLite DB at repo root so we can run without setup.
    database_url: str = Field(
        default_factory=lambda: f"sqlite:///{(PROJECT_ROOT / 'inventory.db').as_posix()}"
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
    rate_limit_login: str = "5/minute"

    # ---- Business constants (legacy compat) ----
    outbound_max: int = 1000
    inbound_max: int = 10000
    warning_threshold: int = 100
    undo_minutes: int = 10

    # ---- Paths ----
    font_path: Path = BACKEND_DIR / "app" / "assets" / "fonts" / "NotoSansJP-Regular.ttf"
    font_name: str = "NotoSansJP"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @field_validator("jwt_secret")
    @classmethod
    def _warn_default_secret(cls, v: str) -> str:
        # Allow default in dev, but enforce strong secret in prod via runtime check below.
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    if s.is_production and (s.jwt_secret in {"change-me", "change-me-please-use-openssl-rand-hex-32"} or len(s.jwt_secret) < 32):
        raise RuntimeError("JWT_SECRET must be set to a strong value (>=32 chars) in production")
    return s


settings = get_settings()
