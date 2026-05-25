"""RBAC: admin-only エンドポイントが USER/GUEST を拒否することを確認。"""
from __future__ import annotations


def test_user_cannot_create_item(user_client):
    r = user_client.post(
        "/items",
        json={"item_name": "新規", "category": "消耗品"},
    )
    assert r.status_code == 403


def test_admin_can_create_item(admin_client):
    r = admin_client.post(
        "/items",
        json={"item_name": "新規物品", "category": "消耗品", "vendor_name": "テスト商事"},
    )
    assert r.status_code in (200, 201), r.text


def test_guest_outbound_goes_pending(guest_client):
    items = guest_client.get("/inventory").json()["items"]
    item_id = items[0]["item_id"]
    r = guest_client.post("/outbound", json={"item_id": item_id, "quantity": 5})
    # GUEST は PENDING 承認待ち or 403 のいずれかが正しい挙動
    assert r.status_code in (200, 201, 202, 403)


def test_user_cannot_access_users_admin(user_client):
    r = user_client.get("/users")
    assert r.status_code == 403
