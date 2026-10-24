"""入出庫・取消・調整・ゲスト申請（受け入れ条件 B-07〜B-14, C-01）。"""
from __future__ import annotations

from datetime import timedelta

from app.models import InventoryHistory, Item
from tests.conftest import stock_of


def _second_item(db) -> int:
    from app.models import Inventory

    it = Item(item_name="綿球", category="消耗品", unit_price=10.0)
    db.add(it)
    db.flush()
    db.add(Inventory(item_id=it.id, quantity=3, threshold=1))
    db.commit()
    return it.id


def test_B07_guest_bulk_outbound_becomes_pending(guest_client, db, item_id):
    other = _second_item(db)
    r = guest_client.post(
        "/outbound/bulk",
        json={"items": [{"item_id": item_id, "quantity": 2}, {"item_id": other, "quantity": 1}]},
    )
    assert r.status_code == 201, r.text
    assert all(x["pending"] for x in r.json())
    assert stock_of(guest_client, item_id) == 50  # まだ減らない


def test_B07_guest_single_outbound_is_pending(guest_client, item_id):
    r = guest_client.post("/outbound", json={"item_id": item_id, "quantity": 2})
    assert r.status_code == 201
    assert r.json()["pending"] is True


def test_B08_guest_request_checks_stock(guest_client, item_id):
    r = guest_client.post("/outbound", json={"item_id": item_id, "quantity": 51})
    assert r.status_code == 400
    assert "手袋" in r.json()["detail"]


def test_B08_approved_history_has_department(guest_client, admin_client, item_id):
    guest_client.post("/outbound", json={"item_id": item_id, "quantity": 2})
    pid = admin_client.get("/approvals").json()["items"][0]["id"]
    assert admin_client.post(f"/approvals/{pid}/decide", json={"approve": True}).status_code == 200
    h = admin_client.get("/history", params={"change_type": "OUT"}).json()["items"][0]
    assert h["department"] == "看護部"
    assert h["user_name"] == "ゲスト"
    assert stock_of(admin_client, item_id) == 48


def test_B09_guest_sees_own_requests(guest_client, admin_client, item_id):
    guest_client.post("/outbound", json={"item_id": item_id, "quantity": 2})
    pid = admin_client.get("/approvals").json()["items"][0]["id"]
    admin_client.post(f"/approvals/{pid}/decide", json={"approve": False, "reject_reason": "在庫確保のため"})
    mine = guest_client.get("/outbound/my-requests").json()
    assert mine[0]["status"] == "REJECTED"
    assert mine[0]["reject_reason"] == "在庫確保のため"


def test_C01_reject_requires_reason(guest_client, admin_client, item_id):
    guest_client.post("/outbound", json={"item_id": item_id, "quantity": 2})
    pid = admin_client.get("/approvals").json()["items"][0]["id"]
    r = admin_client.post(f"/approvals/{pid}/decide", json={"approve": False})
    assert r.status_code == 400


def test_C01_double_approve_is_409(guest_client, admin_client, item_id):
    guest_client.post("/outbound", json={"item_id": item_id, "quantity": 2})
    pid = admin_client.get("/approvals").json()["items"][0]["id"]
    assert admin_client.post(f"/approvals/{pid}/decide", json={"approve": True}).status_code == 200
    r = admin_client.post(f"/approvals/{pid}/decide", json={"approve": True})
    assert r.status_code == 409
    assert stock_of(admin_client, item_id) == 48  # 二重に減らない


def test_B10_history_records_operator_id(user_client, db, item_id):
    user_client.post("/outbound", json={"item_id": item_id, "quantity": 1})
    h = db.query(InventoryHistory).order_by(InventoryHistory.id.desc()).first()
    assert h.created_by is not None


def test_B10_undo_own_outbound(user_client, item_id):
    r = user_client.post("/outbound", json={"item_id": item_id, "quantity": 5})
    hid = r.json()["history_id"]
    assert stock_of(user_client, item_id) == 45
    u = user_client.post(f"/history/{hid}/undo")
    assert u.status_code == 200, u.text
    assert stock_of(user_client, item_id) == 50
    # 2回目は不可
    assert user_client.post(f"/history/{hid}/undo").status_code == 400


def test_B10_cannot_undo_others(make_client, item_id):
    taro = make_client("taro")
    hanako = make_client("hanako")
    hid = taro.post("/outbound", json={"item_id": item_id, "quantity": 5}).json()["history_id"]
    assert hanako.post(f"/history/{hid}/undo").status_code == 403
    admin = make_client("admin")
    assert admin.post(f"/history/{hid}/undo").status_code == 200


def test_B10_guest_cannot_undo(make_client, item_id):
    hid = make_client("taro").post("/outbound", json={"item_id": item_id, "quantity": 5}).json()["history_id"]
    assert make_client("guest").post(f"/history/{hid}/undo").status_code == 403


def test_B10_undo_expires_after_10_minutes(user_client, db, item_id):
    hid = user_client.post("/outbound", json={"item_id": item_id, "quantity": 5}).json()["history_id"]
    h = db.get(InventoryHistory, hid)
    h.created_at = h.created_at - timedelta(minutes=11)
    db.commit()
    r = user_client.post(f"/history/{hid}/undo")
    assert r.status_code == 400
    assert "10分" in r.json()["detail"]


def test_B11_history_rows_have_can_undo(user_client, item_id):
    user_client.post("/outbound", json={"item_id": item_id, "quantity": 1})
    row = user_client.get("/history").json()["items"][0]
    assert row["can_undo"] is True


def test_B12_adjust_records_adjust_type(admin_client, item_id):
    r = admin_client.post("/adjust", json={"item_id": item_id, "new_quantity": 47, "reason": "破損分"})
    assert r.status_code == 200, r.text
    h = admin_client.get("/history").json()["items"][0]
    assert h["change_type"] == "ADJUST"
    assert h["quantity"] == -3
    # 調整は出庫ランキングに入らない
    assert admin_client.get("/stats/top-outbound").json() == []


def test_B12_adjust_without_change_rejected(admin_client, item_id):
    r = admin_client.post("/adjust", json={"item_id": item_id, "new_quantity": 50, "reason": "x"})
    assert r.status_code == 400


def test_B14_bulk_error_names_item(user_client, db, item_id):
    other = _second_item(db)
    r = user_client.post(
        "/outbound/bulk",
        json={"items": [{"item_id": item_id, "quantity": 1}, {"item_id": other, "quantity": 9}]},
    )
    assert r.status_code == 400
    assert "綿球" in r.json()["detail"]
    assert stock_of(user_client, item_id) == 50  # 全件ロールバック


def test_inbound_rejects_inactive_item(admin_client, user_client, item_id):
    admin_client.delete(f"/items/{item_id}")
    r = user_client.post("/inbound", json={"item_id": item_id, "quantity": 1})
    assert r.status_code == 400
