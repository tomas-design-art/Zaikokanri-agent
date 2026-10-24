"""廃棄申請・発注申請・発注書・受領・処理待ち件数（受け入れ条件 C-03〜C-09）。"""
from __future__ import annotations

from tests.conftest import stock_of


# ---------- 廃棄申請 ----------
def test_C03_disposal_checks_stock(user_client, item_id):
    r = user_client.post("/disposal-requests", json={"item_id": item_id, "quantity": 51, "reason": "期限切れ"})
    assert r.status_code == 400


def test_C03_disposal_cancel_by_requester(user_client, admin_client, item_id):
    did = user_client.post(
        "/disposal-requests", json={"item_id": item_id, "quantity": 2, "reason": "破損"}
    ).json()["id"]
    assert user_client.delete(f"/disposal-requests/{did}").status_code == 204
    row = admin_client.get("/disposal-requests").json()["items"][0]
    assert row["status"] == "CANCELLED"
    # 取り下げ済みは承認できない
    assert admin_client.post(f"/disposal-requests/{did}/approve", json={"approve": True}).status_code == 409


def test_C03_disposal_approve_reduces_stock_once(user_client, admin_client, item_id):
    did = user_client.post(
        "/disposal-requests", json={"item_id": item_id, "quantity": 2, "reason": "破損"}
    ).json()["id"]
    assert admin_client.post(f"/disposal-requests/{did}/approve", json={"approve": True}).status_code == 200
    assert admin_client.post(f"/disposal-requests/{did}/approve", json={"approve": True}).status_code == 409
    assert stock_of(admin_client, item_id) == 48


def test_C03_disposal_reject_requires_reason(user_client, admin_client, item_id):
    did = user_client.post(
        "/disposal-requests", json={"item_id": item_id, "quantity": 2, "reason": "破損"}
    ).json()["id"]
    assert admin_client.post(f"/disposal-requests/{did}/approve", json={"approve": False}).status_code == 400


# ---------- 発注申請 ----------
def _pr(client, item_id, qty=5, **kw) -> int:
    r = client.post("/purchase-requests", json={"item_id": item_id, "requested_qty": qty} | kw)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_C04_requester_cannot_edit_after_approval(user_client, admin_client, item_id):
    pid = _pr(user_client, item_id)
    assert user_client.patch(f"/purchase-requests/{pid}", json={"requested_qty": 7}).status_code == 200
    admin_client.patch(f"/purchase-requests/{pid}", json={"status": "APPROVED"})
    assert user_client.patch(f"/purchase-requests/{pid}", json={"requested_qty": 9}).status_code == 400


def test_C04_invalid_status_and_priority_rejected(user_client, admin_client, item_id):
    assert user_client.post(
        "/purchase-requests", json={"item_id": item_id, "requested_qty": 1, "priority": "SUPER"}
    ).status_code == 422
    pid = _pr(user_client, item_id)
    assert admin_client.patch(f"/purchase-requests/{pid}", json={"status": "WHATEVER"}).status_code == 422
    # 承認前に受領済にはできない
    assert admin_client.patch(f"/purchase-requests/{pid}", json={"status": "RECEIVED"}).status_code in (400, 422)


def test_C05_receive_partial_then_full(user_client, admin_client, item_id):
    pid = _pr(user_client, item_id, qty=10)
    admin_client.patch(f"/purchase-requests/{pid}", json={"status": "APPROVED"})
    r1 = user_client.post("/inbound/receive", json={"purchase_request_id": pid, "received_qty": 4})
    assert r1.status_code == 200, r1.text
    pr = user_client.get("/purchase-requests").json()["items"][0]
    assert pr["status"] == "ORDERED"
    assert pr["remaining_qty"] == 6
    # 残数を超える受領は不可
    assert user_client.post("/inbound/receive", json={"purchase_request_id": pid, "received_qty": 7}).status_code == 400
    assert user_client.post("/inbound/receive", json={"purchase_request_id": pid, "received_qty": 6}).status_code == 200
    pr = user_client.get("/purchase-requests").json()["items"][0]
    assert pr["status"] == "RECEIVED"
    assert stock_of(user_client, item_id) == 60
    # 受領済にはもう受領できない
    assert user_client.post("/inbound/receive", json={"purchase_request_id": pid, "received_qty": 1}).status_code == 400


def test_C05_receivable_filter(user_client, admin_client, item_id):
    a = _pr(user_client, item_id)
    _pr(user_client, item_id)
    admin_client.patch(f"/purchase-requests/{a}", json={"status": "APPROVED"})
    rows = user_client.get("/purchase-requests", params={"receivable": True}).json()["items"]
    assert [r["id"] for r in rows] == [a]


def test_C06_mark_ordered_and_reissue(user_client, admin_client, item_id):
    pid = _pr(user_client, item_id, qty=3)
    admin_client.patch(f"/purchase-requests/{pid}", json={"status": "APPROVED"})
    r = admin_client.post("/orders/mark-ordered", json={"request_ids": [pid]})
    assert r.status_code == 200
    assert r.json()["updated"] == 1
    assert user_client.get("/purchase-requests").json()["items"][0]["status"] == "ORDERED"
    # 発注済からも発注書を出し直せる
    assert admin_client.post("/orders/preview", json={"request_ids": [pid]}).status_code == 200


def test_C07_requester_can_withdraw_pending(user_client, item_id):
    pid = _pr(user_client, item_id, due_date="2026-12-01", note="至急")
    row = user_client.get("/purchase-requests").json()["items"][0]
    assert row["due_date"] == "2026-12-01"
    assert user_client.delete(f"/purchase-requests/{pid}").status_code == 204
    assert user_client.get("/purchase-requests").json()["total"] == 0


def test_C08_bulk_create_from_alerts(user_client, item_id):
    r = user_client.post(
        "/purchase-requests/bulk", json={"items": [{"item_id": item_id, "requested_qty": 20}]}
    )
    assert r.status_code == 201, r.text
    assert len(r.json()) == 1


def test_C09_todo_counts_for_admin(guest_client, user_client, admin_client, item_id):
    guest_client.post("/outbound", json={"item_id": item_id, "quantity": 1})
    user_client.post("/disposal-requests", json={"item_id": item_id, "quantity": 1, "reason": "破損"})
    _pr(user_client, item_id)
    todo = admin_client.get("/stats/todo").json()
    assert todo == {"guest_outbound": 1, "disposal": 1, "purchase": 1, "receivable": 0}


def test_order_render_flow_still_works(user_client, admin_client, item_id):
    pid = _pr(user_client, item_id, qty=3)
    admin_client.patch(f"/purchase-requests/{pid}", json={"status": "APPROVED"})
    payloads = admin_client.post("/orders/preview", json={"request_ids": [pid]}).json()["payloads"]
    assert payloads[0]["total"] == 300.0
    assert admin_client.post("/orders/pdf", json={"payload": payloads[0]}).content[:4] == b"%PDF"
    assert admin_client.post("/orders/excel", json={"payloads": payloads}).content[:2] == b"PK"
