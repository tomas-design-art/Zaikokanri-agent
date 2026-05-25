"""SQLAlchemy engine and session helpers."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _make_engine(url: str) -> Engine:
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    eng = create_engine(
        url,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    if url.startswith("sqlite"):
        # Enforce FKs on SQLite
        @event.listens_for(eng, "connect")
        def _fk_pragma(dbapi_conn, _):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON;")
            cur.close()
    return eng


engine: Engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a session and ensures cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
