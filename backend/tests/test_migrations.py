"""起動テスト：空の DB にマイグレーションを流してアプリが動くか（受け入れ条件 F-03, A-03, B-01）。

本番（Render）は `alembic upgrade head` → uvicorn の順で起動する。
テストは create_all で表を作るので、ここでマイグレーション側のずれを捕まえる。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.db import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _cfg(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture
def fresh_url(tmp_path) -> str:
    return f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"


def test_F03_upgrade_head_creates_every_model_column(fresh_url):
    command.upgrade(_cfg(fresh_url), "head")
    eng = create_engine(fresh_url)
    insp = inspect(eng)
    missing = []
    for table in Base.metadata.sorted_tables:
        assert insp.has_table(table.name), f"table {table.name} missing"
        cols = {c["name"] for c in insp.get_columns(table.name)}
        missing += [f"{table.name}.{c.name}" for c in table.columns if c.name not in cols]
    assert missing == [], f"マイグレーションに無い列: {missing}"
    # H-11：0003 で足した列は NOT NULL（モデルと同じ）
    for table, col in [("items", "unit"), ("users", "must_change_password"), ("users", "failed_login_count"), ("users", "token_version")]:
        info = next(c for c in insp.get_columns(table) if c["name"] == col)
        assert info["nullable"] is False, f"{table}.{col} が NULL 可"
    eng.dispose()


def test_F03_no_pending_schema_additions(fresh_url):
    """モデルにあってマイグレーションに無い表・列・インデックスが無いこと（型・既定値の差は対象外）。"""
    from alembic.autogenerate import compare_metadata

    command.upgrade(_cfg(fresh_url), "head")
    eng = create_engine(fresh_url)
    with eng.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    adds = [d for d in diffs if isinstance(d, tuple) and d[0] in {"add_table", "add_column"}]
    assert adds == []
    eng.dispose()


def test_F03_downgrade_and_reupgrade(fresh_url):
    cfg = _cfg(fresh_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0002_seed_defaults")
    command.upgrade(cfg, "head")


def test_B01_A03_data_migration(fresh_url):
    cfg = _cfg(fresh_url)
    command.upgrade(cfg, "0002_seed_defaults")
    eng = create_engine(fresh_url)
    with eng.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO items (item_name, category, expiry_date, item_code, reorder_point, unit_price, is_active) "
                "VALUES ('古い物品', '消耗品', '', '', 25, NULL, 1), ('古い期限', '消耗品', '2026/10/1', NULL, NULL, 0, 1)"
            )
        )
        item_id = conn.execute(text("SELECT id FROM items WHERE item_name='古い物品'")).scalar_one()
        conn.execute(text("INSERT INTO inventory (item_id, quantity, threshold) VALUES (:i, 5, 10)"), {"i": item_id})
    eng.dispose()

    command.upgrade(cfg, "head")
    eng = create_engine(fresh_url)
    with eng.connect() as conn:
        row = conn.execute(
            text("SELECT expiry_date, item_code, unit, unit_price FROM items WHERE item_name='古い物品'")
        ).one()
        assert row.expiry_date is None and row.item_code is None
        assert row.unit == "個"
        # H-10：古い書き方の期限は YYYY-MM-DD にそろう
        assert conn.execute(text("SELECT expiry_date FROM items WHERE item_name='古い期限'")).scalar_one() == "2026-10-01"
        assert row.unit_price == 0
        assert conn.execute(text("SELECT threshold FROM inventory")).scalar_one() == 25
        # 初期管理者（admin/admin123）はパスワード変更が必須になる
        assert conn.execute(text("SELECT must_change_password FROM users WHERE username='admin'")).scalar_one() == 1
        # 部署名から部署IDが埋まる（ゲストの申請や部署別の集計に部署IDが要る）
        assert conn.execute(text(
            "SELECT d.name FROM users u JOIN departments d ON d.id = u.department_id WHERE u.username='admin'"
        )).scalar_one() == "総務部"
    eng.dispose()


def test_F03_app_boots_on_migrated_db(fresh_url, monkeypatch):
    """マイグレーション済み DB に対してアプリを起動し、初期管理者でログインできる。"""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app.db import get_db
    from app.main import app

    command.upgrade(_cfg(fresh_url), "head")
    eng = create_engine(fresh_url, connect_args={"check_same_thread": False})
    S = sessionmaker(bind=eng)

    def _override():
        s = S()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as c:
            r = c.post("/auth/login", json={"username": "admin", "password": "admin123"})
            assert r.status_code == 200
            assert r.json()["user"]["must_change_password"] is True
            assert c.post(
                "/auth/password", json={"current_password": "admin123", "new_password": "newadmin123"}
            ).status_code == 200
            assert c.get("/inventory/kpi").status_code == 200
            assert c.get("/categories").status_code == 200
    finally:
        app.dependency_overrides.clear()
        eng.dispose()
