"""統計・AI の安全性・ヘルスチェック・履歴（受け入れ条件 E-01〜E-05, F-06）。"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.models import InventoryHistory
from app.utils.datetime import jst_now


def test_E01_top_outbound_defaults_to_current_month(user_client, db, item_id):
    user_client.post("/outbound", json={"item_id": item_id, "quantity": 3})
    old = db.query(InventoryHistory).order_by(InventoryHistory.id.desc()).first()
    user_client.post("/outbound", json={"item_id": item_id, "quantity": 2})
    old.created_at = jst_now() - timedelta(days=62)
    db.commit()
    top = user_client.get("/stats/top-outbound").json()
    assert top == [{"item_id": item_id, "item_name": "手袋", "total_quantity": 2}]
    wide = user_client.get(
        "/stats/top-outbound",
        params={"date_from": (jst_now() - timedelta(days=90)).date().isoformat()},
    ).json()
    assert wide[0]["total_quantity"] == 5


def test_E01_undone_outbound_not_counted(user_client, item_id):
    hid = user_client.post("/outbound", json={"item_id": item_id, "quantity": 3}).json()["history_id"]
    user_client.post(f"/history/{hid}/undo")
    assert user_client.get("/stats/top-outbound").json() == []
    monthly = user_client.get("/stats/monthly").json()
    assert all(m["total_quantity"] == 0 or m["change_type"] != "IN" for m in monthly)


def test_E01_monthly_limits_by_months(user_client, db, item_id):
    user_client.post("/outbound", json={"item_id": item_id, "quantity": 1})
    h = db.query(InventoryHistory).order_by(InventoryHistory.id.desc()).first()
    h.created_at = jst_now() - timedelta(days=400)
    db.commit()
    user_client.post("/outbound", json={"item_id": item_id, "quantity": 1})
    yms = {m["ym"] for m in user_client.get("/stats/monthly", params={"months": 3}).json()}
    assert yms == {jst_now().strftime("%Y-%m")}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT password_hash FROM users",
        'SELECT * FROM "users"',
        "SELECT name FROM sqlite_master",
        "SELECT * FROM pg_catalog.pg_tables",
        "SELECT * FROM items; DELETE FROM items",
        "DELETE FROM items",
        "WITH x AS (SELECT 1) DELETE FROM items",
        "SELECT * FROM pending_transactions",
    ],
)
def test_E02_unsafe_sql_rejected(sql):
    from app.services.ai_query import is_safe_sql

    assert is_safe_sql(sql) is False


def test_E02_safe_sql_runs_read_only_with_limit(db):
    from app.services.ai_query import is_safe_sql, run_readonly_query

    sql = "SELECT i.item_name, v.quantity FROM items i JOIN inventory v ON v.item_id = i.id"
    assert is_safe_sql(sql) is True
    rows = run_readonly_query(db, sql, limit=1)
    assert rows == [{"item_name": "手袋", "quantity": 50}]


def test_E02_ai_disabled_message(user_client):
    r = user_client.post("/ai/query", json={"question": "在庫は?"})
    assert r.status_code == 200
    assert "無効" in r.json()["answer"]


def test_E03_alerts_return_lists(user_client):
    assert user_client.get("/alerts/low-stock").json() == []
    assert user_client.get("/alerts/expiring").json() == []


def test_E04_history_invalid_date_is_422(user_client):
    r = user_client.get("/history", params={"date_from": "2026-99-99"})
    assert r.status_code == 422


def test_E04_history_date_range(user_client, item_id):
    user_client.post("/outbound", json={"item_id": item_id, "quantity": 1})
    today = jst_now().date().isoformat()
    assert user_client.get("/history", params={"date_from": today, "date_to": today}).json()["total"] == 1
    tomorrow = (jst_now() + timedelta(days=1)).date().isoformat()
    assert user_client.get("/history", params={"date_from": tomorrow}).json()["total"] == 0


def test_E05_health_and_ready(client):
    assert client.get("/healthz").json()["ok"] is True
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["db"] == "ok"


def test_F06_render_cookie_samesite_lax():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[2] / "render.yaml").read_text(encoding="utf-8")
    block = text.split("COOKIE_SAMESITE", 1)[1].split("- key", 1)[0]
    assert "lax" in block
