"""棚卸し（受け入れ条件 D-01〜D-10）。"""
from __future__ import annotations

import io

from openpyxl import load_workbook

from app.models import Inventory, Item
from tests.conftest import stock_of


def _add_item(db, name: str, qty: int, location: str | None = None, category: str = "消耗品") -> int:
    it = Item(item_name=name, category=category, location_text=location, unit_price=1.0)
    db.add(it)
    db.flush()
    db.add(Inventory(item_id=it.id, quantity=qty, threshold=1))
    db.commit()
    return it.id


def _open_session(admin_client, **kw) -> int:
    r = admin_client.post("/stocktake/sessions", json={"name": "2026年10月 定期棚卸"} | kw)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _records(client, sid, **params) -> list[dict]:
    r = client.get(f"/stocktake/sessions/{sid}/records", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _count(client, rid, qty):
    return client.patch(f"/stocktake/records/{rid}", json={"actual_qty": qty})


def test_D01_apply_reflects_differences_to_inventory(admin_client, user_client, db, item_id):
    other = _add_item(db, "綿球", 3)
    sid = _open_session(admin_client)
    recs = {r["item_id"]: r for r in _records(user_client, sid)}
    assert _count(user_client, recs[item_id]["id"], 47).status_code == 200  # 3個足りない
    assert _count(user_client, recs[other]["id"], 3).status_code == 200  # 一致
    r = admin_client.post(f"/stocktake/sessions/{sid}/apply")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["adjusted"] == 1
    assert body["uncounted"] == 0
    assert stock_of(admin_client, item_id) == 47
    assert stock_of(admin_client, other) == 3
    h = admin_client.get("/history", params={"change_type": "STOCKTAKE"}).json()["items"]
    assert len(h) == 1 and h[0]["quantity"] == -3
    sess = admin_client.get(f"/stocktake/sessions/{sid}").json()
    assert sess["status"] == "CLOSED"
    # 二重に反映しない
    assert admin_client.post(f"/stocktake/sessions/{sid}/apply").status_code == 409
    assert stock_of(admin_client, item_id) == 47


def test_D02_movements_after_count_are_not_lost(admin_client, user_client, item_id):
    sid = _open_session(admin_client)
    # 開始後・数える前に5個出庫 → 帳簿45
    user_client.post("/outbound", json={"item_id": item_id, "quantity": 5})
    rec = _records(user_client, sid)[0]
    # 実数44（帳簿45より1少ない）
    counted = _count(user_client, rec["id"], 44).json()
    assert counted["system_qty"] == 45
    assert counted["diff_qty"] == -1
    # 数えた後に10個入庫 → 帳簿55
    user_client.post("/inbound", json={"item_id": item_id, "quantity": 10})
    admin_client.post(f"/stocktake/sessions/{sid}/apply")
    # 正しい在庫＝実数44＋数えた後の入庫10＝54（開始時の帳簿で差を取ると 44 になり、入庫10が消える）
    assert stock_of(admin_client, item_id) == 54


def test_D03_cannot_edit_closed_session(admin_client, user_client):
    sid = _open_session(admin_client)
    rec = _records(user_client, sid)[0]
    _count(user_client, rec["id"], 50)
    admin_client.post(f"/stocktake/sessions/{sid}/apply")
    r = _count(user_client, rec["id"], 10)
    assert r.status_code == 409


def test_D03_status_is_server_controlled_and_guest_forbidden(admin_client, user_client, guest_client):
    sid = _open_session(admin_client)
    rec = _records(user_client, sid)[0]
    r = user_client.patch(f"/stocktake/records/{rec['id']}", json={"actual_qty": 1, "status": "APPLIED"})
    assert r.status_code == 200
    assert r.json()["status"] == "COUNTED"
    assert guest_client.patch(f"/stocktake/records/{rec['id']}", json={"actual_qty": 1}).status_code == 403


def test_D03_clear_count_returns_to_pending(admin_client, user_client):
    sid = _open_session(admin_client)
    rec = _records(user_client, sid)[0]
    _count(user_client, rec["id"], 1)
    r = _count(user_client, rec["id"], None)
    assert r.json()["status"] == "PENDING"
    assert r.json()["diff_qty"] is None


def test_D04_records_sorted_by_location_and_filterable(admin_client, user_client, db):
    _add_item(db, "B品", 1, location="棚B")
    _add_item(db, "A品", 1, location="棚A")
    _add_item(db, "場所なし", 1)
    sid = _open_session(admin_client)
    names = [r["item_name"] for r in _records(user_client, sid)]
    assert names == ["A品", "手袋", "B品", "場所なし"]  # 棚A → 棚B → 未設定
    rec = _records(user_client, sid, q="B品")
    assert [r["item_name"] for r in rec] == ["B品"]
    assert rec[0]["location"] == "棚B"
    _count(user_client, rec[0]["id"], 5)
    assert "B品" not in [r["item_name"] for r in _records(user_client, sid, only="uncounted")]
    assert [r["item_name"] for r in _records(user_client, sid, only="diff")] == ["B品"]


def test_D06_session_summary_counts(admin_client, user_client, db):
    _add_item(db, "綿球", 3)
    sid = _open_session(admin_client)
    rec = _records(user_client, sid)[0]
    _count(user_client, rec["id"], rec["system_qty"] + 2)
    s = admin_client.get(f"/stocktake/sessions/{sid}").json()["summary"]
    assert s == {"total": 2, "counted": 1, "uncounted": 1, "matched": 0, "diff": 1}


def test_D07_only_one_open_session(admin_client):
    _open_session(admin_client)
    r = admin_client.post("/stocktake/sessions", json={"name": "2つ目"})
    assert r.status_code == 409


def test_D07_scope_by_category(admin_client, user_client, db):
    _add_item(db, "消毒液", 4, category="薬品")
    sid = _open_session(admin_client, category="薬品")
    assert [r["item_name"] for r in _records(user_client, sid)] == ["消毒液"]


def test_D08_refresh_adds_new_items_and_cancel(admin_client, user_client, db):
    sid = _open_session(admin_client)
    _add_item(db, "後から追加", 2)
    r = admin_client.post(f"/stocktake/sessions/{sid}/refresh-items")
    assert r.json()["added"] == 1
    assert len(_records(user_client, sid)) == 2
    assert admin_client.post(f"/stocktake/sessions/{sid}/cancel").status_code == 200
    assert admin_client.get(f"/stocktake/sessions/{sid}").json()["status"] == "CANCELLED"
    # 中止後は新しいセッションを作れる
    _open_session(admin_client)


def test_D09_uncounted_items_are_left_unchanged(admin_client, user_client, db, item_id):
    other = _add_item(db, "綿球", 3)
    sid = _open_session(admin_client)
    recs = {r["item_id"]: r for r in _records(user_client, sid)}
    _count(user_client, recs[item_id]["id"], 40)
    body = admin_client.post(f"/stocktake/sessions/{sid}/apply").json()
    assert body["uncounted"] == 1
    assert stock_of(admin_client, other) == 3


def test_D10_excel_has_detail_columns(admin_client, user_client):
    sid = _open_session(admin_client)
    rec = _records(user_client, sid)[0]
    _count(user_client, rec["id"], 49)
    r = admin_client.get(f"/stocktake/sessions/{sid}/export.xlsx")
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).worksheets[0]
    header = [c.value for c in next(ws.iter_rows(min_row=7, max_row=7))]
    for col in ("物品コード", "保管場所", "単位", "帳簿数", "実数", "差異", "数えた人", "数えた日時"):
        assert col in header, header
    row = [c.value for c in next(ws.iter_rows(min_row=8, max_row=8))]
    assert "山田太郎" in row


def test_non_admin_cannot_apply_or_create(user_client, admin_client):
    assert user_client.post("/stocktake/sessions", json={"name": "x"}).status_code == 403
    sid = _open_session(admin_client)
    assert user_client.post(f"/stocktake/sessions/{sid}/apply").status_code == 403
