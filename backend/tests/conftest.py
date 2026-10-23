"""Pytest 共通フィクスチャ。

- 独立した一時 SQLite DB を作成
- FastAPI の `get_db` 依存をオーバーライド
- admin/user/guest ユーザーをシードし、ロールごとにログイン済みの TestClient を提供
- 受け入れ条件の番号（例 B-01）は docs/REVIEW_2026-10-23.md を参照
"""
from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Callable, Iterator

# テスト用環境変数（settings 読み込み前に設定）
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-do-not-use")
os.environ.setdefault("RATE_LIMIT_LOGIN", "10000/minute")
# TEST_DATABASE_URL を渡すと PostgreSQL（本番と同じ DB）で流せる。未指定なら一時 SQLite。
_PG_URL = os.environ.get("TEST_DATABASE_URL")
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
_TMP_DB.close()
os.environ["DATABASE_URL"] = _PG_URL or f"sqlite:///{_TMP_DB.name}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.auth.hashing import hash_password  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, Department, Inventory, Item, User, Vendor  # noqa: E402
from app.routers.auth import limiter as _login_limiter  # noqa: E402

PASSWORDS = {"admin": "admin123", "taro": "user1234", "guest": "guest123", "hanako": "user5678"}


@pytest.fixture(scope="session")
def engine():
    if _PG_URL:
        from app.db.engine import _normalize_url

        eng = create_engine(_normalize_url(_PG_URL), future=True)
        Base.metadata.drop_all(eng)
    else:
        eng = create_engine(
            f"sqlite:///{_TMP_DB.name}",
            future=True,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(eng, "connect")
        def _fk(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON;")
            cur.close()

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()
    with contextlib.suppress(OSError):
        os.unlink(_TMP_DB.name)


@pytest.fixture
def db(engine) -> Iterator[Session]:
    """各テスト前に全テーブルを空にして基本マスタをシード。"""
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with engine.begin() as conn:
        for t in reversed(Base.metadata.sorted_tables):
            conn.execute(t.delete())

    session = SessionLocal()
    dept = Department(name="検査科")
    dept2 = Department(name="看護部")
    session.add_all([dept, dept2])
    session.flush()
    session.add_all(
        [
            Category(name="消耗品"),
            Category(name="薬品"),
            Vendor(vendor_code="V001", vendor_name="テスト商事"),
            User(
                username="admin", password_hash=hash_password(PASSWORDS["admin"]),
                display_name="管理者", user_role="ADMIN", department="検査科",
                department_id=dept.id, is_active=1,
            ),
            User(
                username="taro", password_hash=hash_password(PASSWORDS["taro"]),
                display_name="山田太郎", user_role="USER", department="検査科",
                department_id=dept.id, is_active=1,
            ),
            User(
                username="hanako", password_hash=hash_password(PASSWORDS["hanako"]),
                display_name="佐藤花子", user_role="USER", department="看護部",
                department_id=dept2.id, is_active=1,
            ),
            User(
                username="guest", password_hash=hash_password(PASSWORDS["guest"]),
                display_name="ゲスト", user_role="GUEST", department="看護部",
                department_id=dept2.id, is_active=1,
            ),
        ]
    )
    session.commit()
    item = Item(
        item_name="手袋", item_code="G001", category="消耗品", vendor_name="テスト商事",
        unit_price=100.0, reorder_point=10, location_text="棚A",
    )
    session.add(item)
    session.flush()
    session.add(Inventory(item_id=item.id, quantity=50, threshold=10))
    session.commit()
    yield session
    session.close()


@pytest.fixture
def _override_db(db, engine) -> Iterator[None]:
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _override() -> Iterator[Session]:
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    with contextlib.suppress(Exception):
        _login_limiter.reset()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def make_client(_override_db) -> Iterator[Callable[[str | None], TestClient]]:
    """ロールごとに独立した Cookie を持つ TestClient を作る。"""
    opened: list[TestClient] = []

    def _make(username: str | None = None) -> TestClient:
        c = TestClient(app)
        c.__enter__()
        opened.append(c)
        if username:
            r = c.post("/auth/login", json={"username": username, "password": PASSWORDS[username]})
            assert r.status_code == 200, r.text
        return c

    yield _make
    for c in opened:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client(None)


@pytest.fixture
def admin_client(make_client) -> TestClient:
    return make_client("admin")


@pytest.fixture
def user_client(make_client) -> TestClient:
    return make_client("taro")


@pytest.fixture
def guest_client(make_client) -> TestClient:
    return make_client("guest")


@pytest.fixture
def item_id(db) -> int:
    return db.query(Item).filter(Item.item_code == "G001").one().id


def stock_of(client: TestClient, iid: int) -> int:
    rows = client.get("/inventory", params={"per_page": 500}).json()["items"]
    return next(r for r in rows if r["item_id"] == iid)["quantity"]
