"""同時操作（受け入れ条件 H-01 / H-04 / H-07）。

2人の操作を確実に重ねるため、処理の途中（読んだ後・書く前）にわざと少し待たせる。
重ならないと「運よく通る」だけになり、二重処理の防止が本当に効いているか分からないため。
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Inventory, InventoryHistory, Item, StocktakeSession
from app.utils.datetime import jst_now
from tests.conftest import stock_of

PAUSE = 0.4


def _both(*calls):
    with ThreadPoolExecutor(len(calls)) as ex:
        return [f.result() for f in [ex.submit(c) for c in calls]]


def _slow_after(module, name: str, monkeypatch):
    original = getattr(module, name)

    def slow(*a, **kw):
        result = original(*a, **kw)
        time.sleep(PAUSE)
        return result

    monkeypatch.setattr(module, name, slow)


@pytest.fixture
def five(db) -> int:
    it = Item(item_name="残り5", category="消耗品", unit_price=1.0)
    db.add(it)
    db.flush()
    db.add(Inventory(item_id=it.id, quantity=5, threshold=1))
    db.commit()
    return it.id


def test_H01_two_people_cannot_take_the_same_last_five(make_client, monkeypatch, five, db):
    from app.services import stock_service

    _slow_after(stock_service, "lock_inventory", monkeypatch)  # 2人とも「在庫5」を読んでから書く
    a, b = make_client("taro"), make_client("hanako")
    r1, r2 = _both(lambda: a.post("/outbound", json={"item_id": five, "quantity": 5}),
                   lambda: b.post("/outbound", json={"item_id": five, "quantity": 5}))
    assert sorted([r1.status_code, r2.status_code]) == [201, 400]
    assert stock_of(a, five) == 0
    assert db.query(InventoryHistory).filter(InventoryHistory.item_id == five, InventoryHistory.change_type == "OUT").count() == 1


def test_H01_concurrent_in_and_out_both_counted(make_client, monkeypatch, five):
    from app.services import stock_service

    _slow_after(stock_service, "lock_inventory", monkeypatch)
    a, b = make_client("taro"), make_client("hanako")
    r1, r2 = _both(lambda: a.post("/outbound", json={"item_id": five, "quantity": 3}),
                   lambda: b.post("/inbound", json={"item_id": five, "quantity": 10}))
    assert (r1.status_code, r2.status_code) == (201, 201)
    assert stock_of(a, five) == 12  # 5 − 3 + 10（どちらの更新も消えない）


def test_H07_double_approval_at_the_same_moment(make_client, monkeypatch, item_id):
    from app.routers import approvals

    guest = make_client("guest")
    guest.post("/outbound", json={"item_id": item_id, "quantity": 5})
    a1, a2 = make_client("admin"), make_client("admin")
    pid = a1.get("/approvals").json()["items"][0]["id"]
    _slow_after(approvals, "require_reason", monkeypatch)  # 2人とも「承認待ち」を読んでから更新
    r1, r2 = _both(lambda: a1.post(f"/approvals/{pid}/decide", json={"approve": True}),
                   lambda: a2.post(f"/approvals/{pid}/decide", json={"approve": True}))
    assert sorted([r1.status_code, r2.status_code]) == [200, 409]
    assert stock_of(a1, item_id) == 45


def test_H07_double_undo_at_the_same_moment(make_client, monkeypatch, item_id):
    from app.routers import history

    taro, admin = make_client("taro"), make_client("admin")
    hid = taro.post("/outbound", json={"item_id": item_id, "quantity": 5}).json()["history_id"]
    _slow_after(history, "undo_problem", monkeypatch)
    r1, r2 = _both(lambda: taro.post(f"/history/{hid}/undo"), lambda: admin.post(f"/history/{hid}/undo"))
    assert sorted([r1.status_code, r2.status_code]) == [200, 400]
    assert stock_of(taro, item_id) == 50  # 2回戻して 55 にならない


def test_H12_count_while_session_is_being_closed(make_client, monkeypatch, item_id, db):
    """実数の保存の途中で確定されたら、その保存は入れない（完了した棚卸しに未反映のカウントを残さない）。"""
    from app.models import StocktakeRecord
    from app.services import stocktake_service

    admin, taro = make_client("admin"), make_client("taro")
    sid = admin.post("/stocktake/sessions", json={"name": "保存と確定"}).json()["id"]
    rid = taro.get(f"/stocktake/sessions/{sid}/records").json()[0]["id"]
    _slow_after(stocktake_service, "get_open_session", monkeypatch)  # 保存は「実施中」を確かめた後に止まる

    def close_later():
        time.sleep(PAUSE / 4)
        return admin.post(f"/stocktake/sessions/{sid}/apply")

    count, apply = _both(lambda: taro.patch(f"/stocktake/records/{rid}", json={"actual_qty": 7}), close_later)
    assert apply.status_code == 200
    assert count.status_code == 409
    db.expire_all()
    assert db.get(StocktakeRecord, rid).actual_qty is None
    assert stock_of(admin, item_id) == 50


def test_H04_only_one_open_session_enforced_by_db(db):
    db.add(StocktakeSession(name="1つ目", status="OPEN", created_at=jst_now()))
    db.commit()
    db.add(StocktakeSession(name="2つ目", status="OPEN", created_at=jst_now()))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # 完了・中止はいくつあってもよい
    db.add_all([StocktakeSession(name="済1", status="CLOSED"), StocktakeSession(name="済2", status="CLOSED")])
    db.commit()
