"""7観点レビューの指摘（受け入れ条件 H-02〜H-13）。どれも直す前に赤を確かめてから直した。"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import pytest

from app.models import Inventory, Item, User
from tests.conftest import stock_of

BACKEND = Path(__file__).resolve().parents[1]


# ---------- H-02 AI の SQL：文字列から SQL を組み立てて実行する関数で抜けられない ----------
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT query_to_xml('select username, password_hash from us'||'ers', true, false, '')",
        'SELECT "query_to_xml"(\'select 1\', true, false, \'\')',
        "SELECT pg_catalog.query_to_xml('select 1', true, false, '')",
        "SELECT table_to_xml('items', true, false, '')",
        "SELECT dblink('x', 'select 1')",
        "SELECT current_setting('server_version')",
    ],
)
def test_H02_query_executing_functions_rejected(sql):
    from app.services.ai_query import is_safe_sql

    assert is_safe_sql(sql) is False


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM items",
        "SELECT lower(item_name), coalesce(item_code, '-') FROM items WHERE category IN ('消耗品')",
        "SELECT i.item_name FROM items i WHERE EXISTS (SELECT 1 FROM inventory v WHERE v.item_id = i.id)",
        "WITH x AS (SELECT item_id, sum(quantity) AS q FROM inventory_history GROUP BY item_id) SELECT * FROM x",
    ],
)
def test_H02_ordinary_queries_still_allowed(sql):
    from app.services.ai_query import is_safe_sql

    assert is_safe_sql(sql) is True


# ---------- H-03 数えた後に無効にした物品があっても確定できる ----------
def test_H03_apply_skips_items_deactivated_after_counting(admin_client, user_client, item_id):
    other = admin_client.post("/items", json={"item_name": "あとで無効", "category": "消耗品", "initial_quantity": 5}).json()["id"]
    sid = admin_client.post("/stocktake/sessions", json={"name": "無効化"}).json()["id"]
    recs = {r["item_id"]: r["id"] for r in user_client.get(f"/stocktake/sessions/{sid}/records").json()}
    user_client.patch(f"/stocktake/records/{recs[item_id]}", json={"actual_qty": 48})
    user_client.patch(f"/stocktake/records/{recs[other]}", json={"actual_qty": 1})
    admin_client.delete(f"/items/{other}")
    r = admin_client.post(f"/stocktake/sessions/{sid}/apply")
    assert r.status_code == 200, r.text
    assert r.json()["skipped"] == ["あとで無効"]
    assert stock_of(admin_client, item_id) == 48


# ---------- H-05 0 に丸めたら知らせる ----------
def test_H05_clamped_items_are_reported(admin_client, user_client, item_id):
    sid = admin_client.post("/stocktake/sessions", json={"name": "丸め"}).json()["id"]
    rid = user_client.get(f"/stocktake/sessions/{sid}/records").json()[0]["id"]
    user_client.patch(f"/stocktake/records/{rid}", json={"actual_qty": 10})  # 差異 −40
    user_client.post("/outbound", json={"item_id": item_id, "quantity": 45})  # 残り5
    r = admin_client.post(f"/stocktake/sessions/{sid}/apply").json()
    assert r["clamped"] == ["手袋"]
    assert stock_of(admin_client, item_id) == 0


# ---------- H-08 単価に無限大・非数は入れられない ----------
@pytest.mark.parametrize("raw", [b"Infinity", b"NaN", b"-Infinity", b"1e400"])
def test_H08_non_finite_price_rejected(user_client, admin_client, item_id, raw):
    body = b'{"item_id": %d, "quantity": 1, "unit_price": %s}' % (item_id, raw)
    r = user_client.post("/inbound", content=body, headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    r2 = admin_client.patch(f"/items/{item_id}", content=b'{"unit_price": %s}' % raw, headers={"Content-Type": "application/json"})
    assert r2.status_code == 422
    assert user_client.get("/history").status_code == 200
    assert user_client.get("/history/export.csv").status_code == 200


# ---------- H-09 デモデータの投入は本番で動かない・既存ユーザーを勝手に上書きしない ----------
def test_H09_seed_refuses_production(tmp_path):
    env = {"APP_ENV": "production", "JWT_SECRET": "x" * 40, "DATABASE_URL": f"sqlite:///{(tmp_path / 'p.db').as_posix()}",
           "PYTHONIOENCODING": "utf-8", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")}
    r = subprocess.run([sys.executable, "scripts/seed_demo.py"], cwd=BACKEND, env=env, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode != 0
    assert "本番" in (r.stdout + r.stderr)


def test_H09_seed_keeps_existing_passwords_unless_asked(db):
    sys.path.insert(0, str(BACKEND / "scripts"))
    import seed_demo

    db.query(Inventory).delete()
    db.query(Item).delete()
    db.commit()
    before = db.query(User).filter(User.username == "admin").one().password_hash
    seed_demo.seed()
    db.expire_all()
    assert db.query(User).filter(User.username == "admin").one().password_hash == before


# ---------- H-13 小さな指摘 ----------
def test_H13_rate_limit_message_is_japanese():
    import asyncio

    from app.main import rate_limit_handler

    resp = asyncio.run(rate_limit_handler(None, None))
    assert resp.status_code == 429
    assert "多すぎ" in resp.body.decode("utf-8")


def test_H13_unknown_usernames_are_masked_in_log(client, caplog):
    with caplog.at_level(logging.INFO, logger="security"):
        client.post("/auth/login", json={"username": "MyS3cretPassw0rd", "password": "x"})
    assert "MyS3cretPassw0rd" not in caplog.text
    assert "login_failed" in caplog.text


def test_H13_admin_resetting_own_password_keeps_own_session(admin_client, db):
    me = db.query(User).filter(User.username == "admin").one()
    assert admin_client.patch(f"/users/{me.id}", json={"password": "adminnew99"}).status_code == 200
    assert admin_client.get("/auth/me").status_code == 200
