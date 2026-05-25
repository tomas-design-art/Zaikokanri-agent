"""Purchase request CRUD + admin decision + order rendering."""
from __future__ import annotations


def _create_pr(client, qty: int = 5) -> int:
    items = client.get("/inventory").json()["items"]
    r = client.post(
        "/purchase-requests",
        json={"item_id": items[0]["item_id"], "requested_qty": qty, "priority": "NORMAL"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_user_can_create_pr(user_client):
    pr_id = _create_pr(user_client)
    assert pr_id > 0


def test_admin_approves_pr(user_client, client):
    pr_id = _create_pr(user_client)
    # admin で再ログイン
    client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    r = client.patch(f"/purchase-requests/{pr_id}", json={"status": "APPROVED"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED"


def test_order_preview_admin_only(user_client):
    pr_id = _create_pr(user_client)
    r = user_client.post("/orders/preview", json={"request_ids": [pr_id]})
    assert r.status_code == 403


def test_order_render_flow(user_client, client):
    pr_id = _create_pr(user_client, qty=3)
    # admin で承認
    client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    client.patch(f"/purchase-requests/{pr_id}", json={"status": "APPROVED"})

    # preview
    r = client.post("/orders/preview", json={"request_ids": [pr_id]})
    assert r.status_code == 200
    payloads = r.json()["payloads"]
    assert len(payloads) == 1
    assert payloads[0]["vendor"] == "テスト商事"
    assert payloads[0]["total"] == 300.0  # 3 * 100

    # email
    r2 = client.post("/orders/email", json={"payload": payloads[0]})
    assert r2.status_code == 200
    assert "発注" in r2.json()["email_text"]

    # PDF
    r3 = client.post("/orders/pdf", json={"payload": payloads[0]})
    assert r3.status_code == 200
    assert r3.content[:4] == b"%PDF"

    # Excel
    r4 = client.post("/orders/excel", json={"payloads": payloads})
    assert r4.status_code == 200
    assert r4.content[:2] == b"PK"  # xlsx (zip)


def test_order_preview_rejects_unapproved(user_client, client):
    pr_id = _create_pr(user_client)
    client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    r = client.post("/orders/preview", json={"request_ids": [pr_id]})
    assert r.status_code == 404
