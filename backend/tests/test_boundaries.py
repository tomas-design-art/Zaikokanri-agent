"""境界値・意図しない入力（テスト設計表 X）。

どんな入力でも 500 にならず、在庫が勝手に動かず、受け付けた値はそのままの文字で保存されること。
"""
from __future__ import annotations

import pytest

from tests.conftest import stock_of

OK, BAD = "ok", "bad"


# ---------- X-01 出庫数 ----------
@pytest.mark.parametrize(
    ("qty", "expect", "after"),
    [
        (0, BAD, 50), (-1, BAD, 50), (1, OK, 49), (50, OK, 0), (51, BAD, 50),
        (1.5, BAD, 50), ("abc", BAD, 50), (None, BAD, 50), (10**12, BAD, 50), ("５", BAD, 50),
    ],
    ids=["0", "-1", "1", "在庫ちょうど", "在庫+1", "小数", "文字", "空", "巨大", "全角数字"],
)
def test_X01_outbound_quantity(user_client, item_id, qty, expect, after):
    r = user_client.post("/outbound", json={"item_id": item_id, "quantity": qty})
    assert r.status_code < 500
    assert (r.status_code == 201) == (expect == OK), r.text
    assert stock_of(user_client, item_id) == after


def test_X01_outbound_max_boundary(admin_client, user_client):
    iid = admin_client.post("/items", json={"item_name": "上限テスト", "category": "消耗品", "initial_quantity": 2000}).json()["id"]
    assert user_client.post("/outbound", json={"item_id": iid, "quantity": 1001}).status_code == 400
    assert user_client.post("/outbound", json={"item_id": iid, "quantity": 1000}).status_code == 201
    assert stock_of(user_client, iid) == 1000


# ---------- X-02 入庫数 ----------
@pytest.mark.parametrize(("qty", "status"), [(10000, 201), (10001, 400), (0, 422)])
def test_X02_inbound_quantity(user_client, item_id, qty, status):
    assert user_client.post("/inbound", json={"item_id": item_id, "quantity": qty}).status_code == status


# ---------- X-03 同じ物品を2行 ----------
def test_X03_same_item_twice_in_bulk_is_all_or_nothing(user_client, item_id):
    r = user_client.post("/outbound/bulk", json={"items": [{"item_id": item_id, "quantity": 30}, {"item_id": item_id, "quantity": 30}]})
    assert r.status_code == 400
    assert stock_of(user_client, item_id) == 50


# ---------- X-04 発注点ちょうど ----------
def test_X04_quantity_equal_to_reorder_point_is_low(admin_client, user_client, item_id):
    user_client.post("/outbound", json={"item_id": item_id, "quantity": 40})  # 50 → 10（発注点10）
    assert item_id in {r["item_id"] for r in user_client.get("/alerts/low-stock").json()}
    row = next(r for r in user_client.get("/inventory").json()["items"] if r["item_id"] == item_id)
    assert row["is_low_stock"] is True
    assert user_client.get("/inventory", params={"only_low_stock": True}).json()["total"] == 1
    user_client.post("/inbound", json={"item_id": item_id, "quantity": 1})  # 11 → 不足ではない
    assert item_id not in {r["item_id"] for r in user_client.get("/alerts/low-stock").json()}


# ---------- X-06 日付の書き方 ----------
@pytest.mark.parametrize("value", ["2026/01/01", "20260101", "2026-02-30", "2026-1-1", "令和8年1月1日", "2026-01-01T00:00:00"])
def test_X06_only_iso_dates(admin_client, item_id, value):
    r = admin_client.patch(f"/items/{item_id}", json={"expiry_date": value})
    assert r.status_code == 422, f"{value} を受け付けてしまった"
    assert "YYYY-MM-DD" in r.json()["detail"]


def test_X06_iso_date_accepted(admin_client, item_id):
    assert admin_client.patch(f"/items/{item_id}", json={"expiry_date": "2026-01-01"}).status_code == 200


# ---------- X-07 文字 ----------
@pytest.mark.parametrize(
    "name",
    ["<script>alert(1)</script>", "' OR 1=1 --", "手袋🧤（Ｍ）", "Robert'); DROP TABLE items;--", "a" * 255],
    ids=["script", "sql", "絵文字・全角", "sql2", "255文字"],
)
def test_X07_text_is_stored_as_is(admin_client, name):
    r = admin_client.post("/items", json={"item_name": name, "category": "消耗品"})
    assert r.status_code == 201, r.text
    assert admin_client.get(f"/items/{r.json()['id']}").json()["item_name"] == name
    assert admin_client.get("/items").json()["total"] == 2  # 表が消えていない


@pytest.mark.parametrize(("name", "status"), [("a" * 256, 422), ("   ", 422), ("", 422)], ids=["256文字", "空白だけ", "空"])
def test_X07_bad_names_rejected(admin_client, name, status):
    assert admin_client.post("/items", json={"item_name": name, "category": "消耗品"}).status_code == status


def test_X07_search_with_quotes_and_wildcards(user_client):
    for q in ["'", '"', "\\", "%_", "' OR 1=1 --"]:
        r = user_client.get("/inventory", params={"q": q})
        assert r.status_code == 200 and r.json()["total"] == 0, q


# ---------- X-08 ページ送り ----------
@pytest.mark.parametrize("params", [{"page": 0}, {"per_page": 0}, {"per_page": 501}, {"page": "x"}])
def test_X08_paging_validation(user_client, params):
    assert user_client.get("/inventory", params=params).status_code == 422


# ---------- X-09 存在しない ID ----------
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/items/99999", None),
        ("POST", "/outbound", {"item_id": 99999, "quantity": 1}),
        ("POST", "/inbound", {"item_id": 99999, "quantity": 1}),
        ("POST", "/adjust", {"item_id": 99999, "new_quantity": 1, "reason": "x"}),
        ("POST", "/disposal-requests", {"item_id": 99999, "quantity": 1, "reason": "x"}),
        ("POST", "/purchase-requests", {"item_id": 99999, "requested_qty": 1}),
        ("POST", "/approvals/99999/decide", {"approve": True}),
        ("POST", "/disposal-requests/99999/approve", {"approve": True}),
        ("PATCH", "/purchase-requests/99999", {"note": "x"}),
        ("POST", "/history/99999/undo", None),
        ("GET", "/stocktake/sessions/99999", None),
        ("PATCH", "/stocktake/records/99999", {"actual_qty": 1}),
        ("POST", "/inbound/receive", {"purchase_request_id": 99999, "received_qty": 1}),
        ("PATCH", "/users/99999", {"display_name": "x"}),
    ],
)
def test_X09_unknown_ids(admin_client, method, path, body):
    r = admin_client.request(method, path, json=body)
    assert r.status_code in (400, 404), f"{method} {path} → {r.status_code}"
    assert isinstance(r.json()["detail"], str)


# ---------- X-10 壊れた入力 ----------
def test_X10_broken_json(user_client):
    r = user_client.post("/outbound", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)


def test_X10_missing_fields_are_named_in_japanese(user_client):
    r = user_client.post("/outbound", json={})
    assert r.status_code == 422
    assert "物品" in r.json()["detail"] and "数量" in r.json()["detail"]


# ---------- X-11 承認の時点で在庫が足りない ----------
def test_X11_approve_when_stock_ran_out_keeps_request_pending(guest_client, user_client, admin_client, item_id):
    guest_client.post("/outbound", json={"item_id": item_id, "quantity": 10})
    user_client.post("/outbound", json={"item_id": item_id, "quantity": 45})  # 残り5
    pid = admin_client.get("/approvals").json()["items"][0]["id"]
    r = admin_client.post(f"/approvals/{pid}/decide", json={"approve": True})
    assert r.status_code == 400
    assert admin_client.get("/approvals").json()["items"][0]["status"] == "PENDING"
    assert stock_of(admin_client, item_id) == 5


# ---------- X-12 棚卸しの入力 ----------
@pytest.mark.parametrize(("qty", "status"), [(-1, 422), (10_000_001, 422), (0, 200), (10_000_000, 200), ("x", 422)])
def test_X12_stocktake_count_values(admin_client, user_client, qty, status):
    sid = admin_client.post("/stocktake/sessions", json={"name": "境界"}).json()["id"]
    rid = user_client.get(f"/stocktake/sessions/{sid}/records").json()[0]["id"]
    assert user_client.patch(f"/stocktake/records/{rid}", json={"actual_qty": qty}).status_code == status


def test_X12_cancelled_session_rejects_input(admin_client, user_client):
    sid = admin_client.post("/stocktake/sessions", json={"name": "中止"}).json()["id"]
    rid = user_client.get(f"/stocktake/sessions/{sid}/records").json()[0]["id"]
    admin_client.post(f"/stocktake/sessions/{sid}/cancel")
    assert user_client.patch(f"/stocktake/records/{rid}", json={"actual_qty": 1}).status_code == 409
    assert admin_client.post(f"/stocktake/sessions/{sid}/apply").status_code == 409


def test_X12_closed_session_rejects_refresh(admin_client):
    """中止・完了した棚卸しに対象の追加はできない（D-03）。"""
    sid = admin_client.post("/stocktake/sessions", json={"name": "中止後"}).json()["id"]
    admin_client.post(f"/stocktake/sessions/{sid}/cancel")
    admin_client.post("/items", json={"item_name": "あとから", "category": "消耗品"})
    assert admin_client.post(f"/stocktake/sessions/{sid}/refresh-items").status_code == 409
    assert len(admin_client.get(f"/stocktake/sessions/{sid}/records").json()) == 1


def test_X12_apply_with_nothing_counted(admin_client, item_id):
    sid = admin_client.post("/stocktake/sessions", json={"name": "未カウント"}).json()["id"]
    r = admin_client.post(f"/stocktake/sessions/{sid}/apply").json()
    assert (r["applied"], r["adjusted"], r["uncounted"]) == (0, 0, 1)
    assert stock_of(admin_client, item_id) == 50


def test_X12_stock_never_goes_negative_on_apply(admin_client, user_client, item_id):
    """数えた後に在庫が減って、差異を足すとマイナスになる場合は 0 で止める。"""
    sid = admin_client.post("/stocktake/sessions", json={"name": "マイナス"}).json()["id"]
    rid = user_client.get(f"/stocktake/sessions/{sid}/records").json()[0]["id"]
    user_client.patch(f"/stocktake/records/{rid}", json={"actual_qty": 10})  # 帳簿50 → 差異 −40
    user_client.post("/outbound", json={"item_id": item_id, "quantity": 45})  # 残り5
    admin_client.post(f"/stocktake/sessions/{sid}/apply")
    assert stock_of(admin_client, item_id) == 0


# ---------- X-13 受領数 ----------
def test_X13_receive_quantity(user_client, admin_client, item_id):
    pid = user_client.post("/purchase-requests", json={"item_id": item_id, "requested_qty": 5}).json()["id"]
    admin_client.patch(f"/purchase-requests/{pid}", json={"status": "APPROVED"})
    assert user_client.post("/inbound/receive", json={"purchase_request_id": pid, "received_qty": 0}).status_code == 422
    assert user_client.post("/inbound/receive", json={"purchase_request_id": pid, "received_qty": 6}).status_code == 400
    assert user_client.post("/inbound/receive", json={"purchase_request_id": pid, "received_qty": 5}).status_code == 200


# ---------- X-14 ログインのユーザー名 ----------
def test_X14_username_spaces_ignored_case_sensitive(client):
    assert client.post("/auth/login", json={"username": "  taro ", "password": "user1234"}).status_code == 200
    assert client.post("/auth/login", json={"username": "TARO", "password": "user1234"}).status_code == 401


# ---------- 取消の決めごと（すり抜け対策） ----------
def test_undo_inbound_after_stock_used_is_rejected(user_client, item_id):
    hid = user_client.post("/inbound", json={"item_id": item_id, "quantity": 10}).json()["history_id"]
    user_client.post("/outbound", json={"item_id": item_id, "quantity": 55})  # 60 → 5
    r = user_client.post(f"/history/{hid}/undo")
    assert r.status_code == 400
    assert stock_of(user_client, item_id) == 5


def test_undo_receipt_and_approved_requests_is_rejected(user_client, admin_client, guest_client, item_id):
    pid = user_client.post("/purchase-requests", json={"item_id": item_id, "requested_qty": 3}).json()["id"]
    admin_client.patch(f"/purchase-requests/{pid}", json={"status": "APPROVED"})
    hid = user_client.post("/inbound/receive", json={"purchase_request_id": pid, "received_qty": 3}).json()["history_id"]
    assert user_client.post(f"/history/{hid}/undo").status_code == 400
    assert admin_client.post(f"/history/{hid}/undo").status_code == 400


def test_guest_cannot_undo_even_own_approved_outbound(guest_client, admin_client, item_id):
    """承認済みの出庫の履歴はゲストのもの（担当＝ゲスト）だが、ゲストは取消そのものができない（権限）。"""
    guest_client.post("/outbound", json={"item_id": item_id, "quantity": 2})
    pid = admin_client.get("/approvals").json()["items"][0]["id"]
    admin_client.post(f"/approvals/{pid}/decide", json={"approve": True})
    hid = admin_client.get("/history", params={"change_type": "OUT"}).json()["items"][0]["id"]
    assert guest_client.post(f"/history/{hid}/undo").status_code == 403
    assert stock_of(admin_client, item_id) == 48


def test_history_rows_remember_operator(user_client, db, item_id):
    from app.models import InventoryHistory, User

    user_client.post("/inbound", json={"item_id": item_id, "quantity": 1})
    h = db.query(InventoryHistory).order_by(InventoryHistory.id.desc()).first()
    assert h.created_by == db.query(User).filter(User.username == "taro").one().id


# ---------- 状態遷移（すり抜け対策） ----------
def test_admin_cannot_change_ordered_request(user_client, admin_client, item_id):
    pid = user_client.post("/purchase-requests", json={"item_id": item_id, "requested_qty": 3}).json()["id"]
    admin_client.patch(f"/purchase-requests/{pid}", json={"status": "APPROVED"})
    admin_client.post("/orders/mark-ordered", json={"request_ids": [pid]})
    assert admin_client.patch(f"/purchase-requests/{pid}", json={"status": "REJECTED"}).status_code == 400


def test_requester_cannot_withdraw_after_approval(user_client, admin_client, item_id):
    pid = user_client.post("/purchase-requests", json={"item_id": item_id, "requested_qty": 3}).json()["id"]
    admin_client.patch(f"/purchase-requests/{pid}", json={"status": "APPROVED"})
    assert user_client.delete(f"/purchase-requests/{pid}").status_code == 400


def test_receive_rejects_unapproved_request(user_client, item_id):
    pid = user_client.post("/purchase-requests", json={"item_id": item_id, "requested_qty": 3}).json()["id"]
    assert user_client.post("/inbound/receive", json={"purchase_request_id": pid, "received_qty": 1}).status_code == 400
    assert stock_of(user_client, item_id) == 50


def test_mark_ordered_only_approved(user_client, admin_client, item_id):
    pid = user_client.post("/purchase-requests", json={"item_id": item_id, "requested_qty": 3}).json()["id"]
    assert admin_client.post("/orders/mark-ordered", json={"request_ids": [pid]}).json()["updated"] == 0
    assert user_client.get("/purchase-requests").json()["items"][0]["status"] == "PENDING"


def test_others_cannot_cancel_disposal(make_client, item_id):
    taro, hanako = make_client("taro"), make_client("hanako")
    did = taro.post("/disposal-requests", json={"item_id": item_id, "quantity": 1, "reason": "破損"}).json()["id"]
    assert hanako.delete(f"/disposal-requests/{did}").status_code == 403


def test_guest_without_department_cannot_request(guest_client, db, item_id):
    from app.models import User

    db.query(User).filter(User.username == "guest").update({"department_id": None})
    db.commit()
    r = guest_client.post("/outbound", json={"item_id": item_id, "quantity": 1})
    assert r.status_code == 400 and "部署" in r.json()["detail"]


def test_todo_counts_only_own_for_non_admin(make_client, item_id):
    taro, hanako = make_client("taro"), make_client("hanako")
    taro.post("/purchase-requests", json={"item_id": item_id, "requested_qty": 1})
    assert taro.get("/stats/todo").json()["purchase"] == 1
    assert hanako.get("/stats/todo").json()["purchase"] == 0


def test_stocktake_excludes_non_target_items(admin_client, user_client):
    admin_client.post("/items", json={"item_name": "対象外", "category": "消耗品", "is_inventory_target": 0})
    sid = admin_client.post("/stocktake/sessions", json={"name": "対象"}).json()["id"]
    assert "対象外" not in {r["item_name"] for r in user_client.get(f"/stocktake/sessions/{sid}/records").json()}


def test_refresh_token_cannot_be_used_as_access(make_client):
    c = make_client("taro")
    c.cookies.set("zk_access", c.cookies.get("zk_refresh"))
    assert c.get("/auth/me").status_code == 401


def test_deactivated_user_session_stops_immediately(make_client, db):
    from app.models import User

    taro = make_client("taro")
    db.query(User).filter(User.username == "taro").update({"is_active": 0})
    db.commit()
    assert taro.get("/inventory").status_code == 401
