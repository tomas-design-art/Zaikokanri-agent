"""反映のテスト（テスト設計表 P）。

操作の前と後で「見える場所」を全部まとめて取り、
  - 変わった所が表のとおり（どれだけ変わったかも）
  - ほかの所は1つも変わっていない
ことを確かめる。
"""
from __future__ import annotations

import csv
import io
from datetime import timedelta

import pytest

from app.utils.datetime import jst_today

VIEWS = ("qty", "detail_qty", "kpi", "low", "expiring", "listed", "hist_n", "hist_last", "top", "dept", "monthly",
         "todo", "approvals", "csv_qty")


def snapshot(admin, item_id: int) -> dict:
    """管理者から見える全部の場所。"""
    inv = {r["item_id"]: r for r in admin.get("/inventory", params={"per_page": 500}).json()["items"]}
    detail = admin.get(f"/items/{item_id}").json()
    hist = admin.get("/history", params={"per_page": 500}).json()["items"]
    mine = [h for h in hist if h["item_id"] == item_id]
    rows = list(csv.reader(io.StringIO(admin.get("/inventory/export.csv").content.decode("utf-8-sig"))))
    csv_qty = next((int(r[5]) for r in rows[1:] if r[0] == detail["item_name"]), None)
    return {
        "qty": inv[item_id]["quantity"] if item_id in inv else None,
        "detail_qty": detail["quantity"],
        "kpi": admin.get("/inventory/kpi").json(),
        "low": item_id in {r["item_id"] for r in admin.get("/alerts/low-stock").json()},
        "expiring": item_id in {r["item_id"] for r in admin.get("/alerts/expiring").json()},
        "listed": item_id in inv,
        "hist_n": len(mine),
        "hist_last": {k: mine[0][k] for k in ("change_type", "quantity", "user_name", "department", "status")} if mine else None,
        "top": {r["item_id"]: r["total_quantity"] for r in admin.get("/stats/top-outbound").json()}.get(item_id, 0),
        "dept": {r["department"]: r["total_outbound"] for r in admin.get("/stats/by-department").json()},
        "monthly": {(r["ym"], r["change_type"]): r["total_quantity"] for r in admin.get("/stats/monthly").json()},
        "todo": admin.get("/stats/todo").json(),
        "approvals": admin.get("/approvals").json()["total"],
        "csv_qty": csv_qty,
    }


def changed(before: dict, after: dict) -> set[str]:
    return {k for k in VIEWS if before[k] != after[k]}


def ym() -> str:
    return jst_today().strftime("%Y-%m")


def month(snap: dict, kind: str) -> int:
    return snap["monthly"].get((ym(), kind), 0)


@pytest.fixture
def item(admin_client) -> dict:
    """在庫20・発注点5 の物品（期限なし）。"""
    r = admin_client.post("/items", json={"item_name": "反映テスト品", "category": "消耗品", "reorder_point": 5, "initial_quantity": 20})
    assert r.status_code == 201, r.text
    return r.json()


def test_P01_outbound_reaches_every_view(admin_client, user_client, item):
    b = snapshot(admin_client, item["id"])
    assert user_client.post("/outbound", json={"item_id": item["id"], "quantity": 4}).status_code == 201
    a = snapshot(admin_client, item["id"])
    assert changed(b, a) == {"qty", "detail_qty", "kpi", "hist_n", "hist_last", "top", "dept", "monthly", "csv_qty"}
    assert a["qty"] == a["detail_qty"] == a["csv_qty"] == 16
    assert a["kpi"]["total_quantity"] == b["kpi"]["total_quantity"] - 4
    assert a["kpi"]["total_items"] == b["kpi"]["total_items"]
    assert a["hist_last"] == {"change_type": "OUT", "quantity": 4, "user_name": "山田太郎", "department": "検査科", "status": "CONFIRMED"}
    assert a["top"] == 4
    assert a["dept"].get("検査科", 0) == b["dept"].get("検査科", 0) + 4
    assert month(a, "OUT") == month(b, "OUT") + 4


def test_P02_undo_restores_every_view(admin_client, user_client, item):
    b = snapshot(admin_client, item["id"])
    hid = user_client.post("/outbound", json={"item_id": item["id"], "quantity": 4}).json()["history_id"]
    assert user_client.post(f"/history/{hid}/undo").status_code == 200
    a = snapshot(admin_client, item["id"])
    # 履歴が2行増える（元の出庫＝取消済、打ち消しの入庫）。それ以外は全部元どおり
    assert changed(b, a) == {"hist_n", "hist_last"}
    assert a["hist_n"] == b["hist_n"] + 2
    statuses = {h["change_type"]: h["status"] for h in admin_client.get("/history").json()["items"] if h["item_id"] == item["id"] and h["quantity"] == 4}
    assert statuses == {"OUT": "REJECTED", "IN": "CONFIRMED"}


def test_P03_crossing_reorder_point_raises_alert(admin_client, user_client, item):
    b = snapshot(admin_client, item["id"])
    user_client.post("/outbound", json={"item_id": item["id"], "quantity": 15})  # 20 → 5（発注点ちょうど）
    a = snapshot(admin_client, item["id"])
    assert not b["low"] and a["low"]
    assert a["kpi"]["low_stock_count"] == b["kpi"]["low_stock_count"] + 1


def test_P04_guest_request_changes_only_queues(admin_client, guest_client, item):
    b = snapshot(admin_client, item["id"])
    r = guest_client.post("/outbound", json={"item_id": item["id"], "quantity": 2})
    assert r.status_code == 201 and r.json()["pending"] is True
    a = snapshot(admin_client, item["id"])
    assert changed(b, a) == {"todo", "approvals"}
    assert a["approvals"] == b["approvals"] + 1
    assert a["todo"]["guest_outbound"] == b["todo"]["guest_outbound"] + 1
    assert guest_client.get("/outbound/my-requests").json()[0]["status"] == "PENDING"


def test_P05_approved_guest_request_counts_under_guest_department(admin_client, guest_client, item):
    guest_client.post("/outbound", json={"item_id": item["id"], "quantity": 2})
    b = snapshot(admin_client, item["id"])
    pid = admin_client.get("/approvals").json()["items"][0]["id"]
    assert admin_client.post(f"/approvals/{pid}/decide", json={"approve": True}).status_code == 200
    a = snapshot(admin_client, item["id"])
    assert changed(b, a) == {"qty", "detail_qty", "kpi", "hist_n", "hist_last", "top", "dept", "monthly", "todo", "approvals", "csv_qty"}
    assert a["qty"] == 18
    assert a["hist_last"] == {"change_type": "OUT", "quantity": 2, "user_name": "ゲスト", "department": "看護部", "status": "CONFIRMED"}
    assert a["dept"].get("看護部", 0) == b["dept"].get("看護部", 0) + 2
    assert a["approvals"] == b["approvals"] - 1
    assert guest_client.get("/outbound/my-requests").json()[0]["status"] == "APPROVED"


def test_P06_rejected_guest_request_changes_no_stock(admin_client, guest_client, item):
    guest_client.post("/outbound", json={"item_id": item["id"], "quantity": 2})
    b = snapshot(admin_client, item["id"])
    pid = admin_client.get("/approvals").json()["items"][0]["id"]
    admin_client.post(f"/approvals/{pid}/decide", json={"approve": False, "reject_reason": "在庫確保"})
    a = snapshot(admin_client, item["id"])
    assert changed(b, a) == {"todo", "approvals"}
    mine = guest_client.get("/outbound/my-requests").json()[0]
    assert (mine["status"], mine["reject_reason"]) == ("REJECTED", "在庫確保")


def test_P07_inbound_reaches_every_view(admin_client, user_client, item):
    user_client.post("/outbound", json={"item_id": item["id"], "quantity": 16})  # 4 → 在庫不足
    b = snapshot(admin_client, item["id"])
    r = user_client.post("/inbound", json={"item_id": item["id"], "quantity": 10, "vendor_name": "テスト商事", "unit_price": 120})
    assert r.status_code == 201
    a = snapshot(admin_client, item["id"])
    assert changed(b, a) == {"qty", "detail_qty", "kpi", "low", "hist_n", "hist_last", "monthly", "csv_qty"}
    assert a["qty"] == 14 and b["low"] and not a["low"]
    assert month(a, "IN") == month(b, "IN") + 10
    last = admin_client.get("/history").json()["items"][0]
    assert (last["vendor_name"], last["unit_price"], last["total_price"]) == ("テスト商事", 120, 1200)


def test_P08_purchase_lifecycle(admin_client, user_client, item):
    b = snapshot(admin_client, item["id"])
    pid = user_client.post("/purchase-requests", json={"item_id": item["id"], "requested_qty": 10}).json()["id"]
    a1 = snapshot(admin_client, item["id"])
    assert changed(b, a1) == {"todo"} and a1["todo"]["purchase"] == b["todo"]["purchase"] + 1
    admin_client.patch(f"/purchase-requests/{pid}", json={"status": "APPROVED"})
    a2 = snapshot(admin_client, item["id"])
    assert changed(a1, a2) == {"todo"}
    assert (a2["todo"]["purchase"], a2["todo"]["receivable"]) == (a1["todo"]["purchase"] - 1, a1["todo"]["receivable"] + 1)
    admin_client.post("/orders/mark-ordered", json={"request_ids": [pid]})
    assert changed(a2, snapshot(admin_client, item["id"])) == set()  # 発注済にしても在庫は変わらない
    user_client.post("/inbound/receive", json={"purchase_request_id": pid, "received_qty": 4})
    a3 = snapshot(admin_client, item["id"])
    assert a3["qty"] == 24 and a3["todo"]["receivable"] == a2["todo"]["receivable"]  # 一部ならまだ受領待ち
    user_client.post("/inbound/receive", json={"purchase_request_id": pid, "received_qty": 6})
    a4 = snapshot(admin_client, item["id"])
    assert a4["qty"] == 30 and a4["todo"]["receivable"] == a3["todo"]["receivable"] - 1
    assert a4["top"] == b["top"]  # 受領は出庫ランキングに関係しない


def test_P09_disposal_not_counted_as_outbound(admin_client, user_client, item):
    did = user_client.post("/disposal-requests", json={"item_id": item["id"], "quantity": 3, "reason": "破損"}).json()["id"]
    b = snapshot(admin_client, item["id"])
    admin_client.post(f"/disposal-requests/{did}/approve", json={"approve": True})
    a = snapshot(admin_client, item["id"])
    assert changed(b, a) == {"qty", "detail_qty", "kpi", "hist_n", "hist_last", "monthly", "todo", "csv_qty"}
    assert a["qty"] == 17 and a["hist_last"]["change_type"] == "DISPOSE"
    assert a["top"] == b["top"] and a["dept"] == b["dept"]
    assert month(a, "DISPOSE") == month(b, "DISPOSE") + 3


def test_P10_adjust_not_in_stats(admin_client, item):
    b = snapshot(admin_client, item["id"])
    admin_client.post("/adjust", json={"item_id": item["id"], "new_quantity": 7, "reason": "数え直し"})
    a = snapshot(admin_client, item["id"])
    assert changed(b, a) == {"qty", "detail_qty", "kpi", "hist_n", "hist_last", "csv_qty"}
    assert a["qty"] == 7 and a["hist_last"]["change_type"] == "ADJUST" and a["hist_last"]["quantity"] == -13


def test_P11_new_item_with_initial_stock(admin_client):
    kpi = admin_client.get("/inventory/kpi").json()
    r = admin_client.post("/items", json={"item_name": "初期在庫テスト", "category": "消耗品", "reorder_point": 5, "initial_quantity": 3})
    a = snapshot(admin_client, r.json()["id"])
    assert a["listed"] and a["qty"] == 3 and a["low"]  # 3 ≤ 5
    assert a["kpi"]["total_items"] == kpi["total_items"] + 1
    assert a["kpi"]["total_quantity"] == kpi["total_quantity"] + 3
    assert a["hist_last"]["change_type"] == "IN" and a["hist_n"] == 1


def test_P12_reorder_point_change(admin_client, item):
    b = snapshot(admin_client, item["id"])
    admin_client.patch(f"/items/{item['id']}", json={"reorder_point": 20})
    a = snapshot(admin_client, item["id"])
    assert changed(b, a) == {"kpi", "low"} and a["low"]


@pytest.mark.parametrize(("days", "expired", "expiring"), [(-1, True, True), (0, False, True), (30, False, True), (31, False, False)])
def test_P13_expiry_dates(admin_client, item, days, expired, expiring):
    d = (jst_today() + timedelta(days=days)).isoformat()
    b = snapshot(admin_client, item["id"])
    admin_client.patch(f"/items/{item['id']}", json={"expiry_date": d})
    a = snapshot(admin_client, item["id"])
    assert a["expiring"] is expiring  # 期限の一覧＝期限切れ＋30日以内
    assert a["kpi"]["expired_count"] == b["kpi"]["expired_count"] + int(expired)
    assert a["kpi"]["expiring_soon_count"] == b["kpi"]["expiring_soon_count"] + int(expiring and not expired)
    row = next(r for r in admin_client.get("/inventory").json()["items"] if r["item_id"] == item["id"])
    assert (row["is_expired"], row["is_expiring_soon"]) == (expired, expiring and not expired)


def test_P14_deactivated_item_leaves_lists_but_keeps_history(admin_client, user_client, item):
    user_client.post("/outbound", json={"item_id": item["id"], "quantity": 16})  # 在庫不足にしておく
    b = snapshot(admin_client, item["id"])
    admin_client.delete(f"/items/{item['id']}")
    a = snapshot(admin_client, item["id"])
    assert b["listed"] and b["low"] and not a["listed"] and not a["low"]
    assert a["kpi"]["total_items"] == b["kpi"]["total_items"] - 1
    assert a["hist_n"] == b["hist_n"]
    sid = admin_client.post("/stocktake/sessions", json={"name": "無効の後"}).json()["id"]
    assert item["id"] not in {r["item_id"] for r in admin_client.get(f"/stocktake/sessions/{sid}/records").json()}


def test_P15_stocktake_apply_only_touches_diff_items(admin_client, user_client, item):
    other = admin_client.post("/items", json={"item_name": "差異なし品", "category": "消耗品", "initial_quantity": 9}).json()
    sid = admin_client.post("/stocktake/sessions", json={"name": "反映"}).json()["id"]
    recs = {r["item_id"]: r["id"] for r in admin_client.get(f"/stocktake/sessions/{sid}/records").json()}
    user_client.patch(f"/stocktake/records/{recs[item['id']]}", json={"actual_qty": 18})
    user_client.patch(f"/stocktake/records/{recs[other['id']]}", json={"actual_qty": 9})
    b, bo = snapshot(admin_client, item["id"]), snapshot(admin_client, other["id"])
    admin_client.post(f"/stocktake/sessions/{sid}/apply")
    a, ao = snapshot(admin_client, item["id"]), snapshot(admin_client, other["id"])
    assert changed(b, a) == {"qty", "detail_qty", "kpi", "hist_n", "hist_last", "csv_qty"}
    assert a["qty"] == 18 and a["hist_last"]["change_type"] == "STOCKTAKE" and a["hist_last"]["quantity"] == -2
    assert ao["qty"] == bo["qty"] == 9 and ao["hist_n"] == bo["hist_n"]


def test_P16_category_rename_follows_items(admin_client, item):
    cid = next(c["id"] for c in admin_client.get("/categories").json() if c["name"] == "消耗品")
    b = snapshot(admin_client, item["id"])
    admin_client.patch(f"/categories/{cid}", json={"name": "消耗品（院内）"})
    a = snapshot(admin_client, item["id"])
    assert changed(b, a) == set()
    assert admin_client.get(f"/items/{item['id']}").json()["category"] == "消耗品（院内）"
    assert {r["category"] for r in admin_client.get("/inventory").json()["items"]} == {"消耗品（院内）"}
