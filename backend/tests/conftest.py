"""Pytest 共通フィクスチャ。

- 独立した一時 SQLite DB を作成
- FastAPI の `get_db` 依存をオーバーライド
- admin/user/guest ユーザーをシードし、ログイン済み TestClient を提供
"""
from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterator

# テスト用環境変数（settings 読み込み前に設定）
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-do-not-use")
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
_TMP_DB.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.name}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.auth.hashing import hash_password  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, Department, Inventory, Item, User, Vendor  # noqa: E402
from app.routers.auth import limiter as _login_limiter  # noqa: E402


@pytest.fixture(scope="session")
def engine():
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
def db(engine) -> Iterator:
    """各テスト前に全テーブルを TRUNCATE → 基本マスタをシード。"""
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    # クリーンスレート
    with engine.begin() as conn:
        for t in reversed(Base.metadata.sorted_tables):
            conn.execute(t.delete())

    session = SessionLocal()
    dept = Department(name="検査科")
    session.add(dept)
    session.flush()
    session.add_all(
        [
            Category(name="消耗品"),
            Vendor(vendor_code="V001", vendor_name="テスト商事"),
            User(
                username="admin", password_hash=hash_password("admin123"),
                display_name="管理者", user_role="ADMIN", department_id=dept.id, is_active=1,
            ),
            User(
                username="taro", password_hash=hash_password("user123"),
                display_name="山田太郎", user_role="USER", department_id=dept.id, is_active=1,
            ),
            User(
                username="guest", password_hash=hash_password("guest123"),
                display_name="ゲスト", user_role="GUEST", department_id=dept.id, is_active=1,
            ),
        ]
    )
    session.commit()
    # サンプル物品 + 在庫
    item = Item(item_name="手袋", item_code="G001", category="消耗品", vendor_name="テスト商事", unit_price=100.0)
    session.add(item)
    session.flush()
    session.add(Inventory(item_id=item.id, quantity=50, threshold=10))
    session.commit()
    yield session
    session.close()


@pytest.fixture
def client(db, engine) -> Iterator[TestClient]:
    """`get_db` をテスト DB に差し替えた TestClient。"""
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _override() -> Iterator:
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    # slowapi のレート制限を各テスト前にリセット
    with contextlib.suppress(Exception):
        _login_limiter.reset()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(client) -> TestClient:
    r = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def user_client(client) -> TestClient:
    client.post("/auth/login", json={"username": "taro", "password": "user123"})
    return client


@pytest.fixture
def guest_client(client) -> TestClient:
    client.post("/auth/login", json={"username": "guest", "password": "guest123"})
    return client
