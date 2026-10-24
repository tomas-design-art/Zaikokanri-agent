"""物品マスター・在庫一覧（受け入れ条件 B-01〜B-06, B-15〜B-21, E-06）。"""
from __future__ import annotations

from app.models import Inventory, Item
from tests.conftest import stock_of


def _new_item(admin_client, **kw) -> dict:
    body = {"item_name": "マスク", "category": "消耗品"} | kw
    r = admin_client.post("/items", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_B01_blank_strings_saved_as_null(admin_client, db):
    it = _new_item(admin_client, expiry_date="", item_code="", vendor_name="", location_text="")
    row = db.get(Item, it["id"])
    assert row.expiry_date is None
    assert row.item_code is None
    assert row.vendor_name is None
    # KPI の期限切れに数えない
    kpi = admin_client.get("/inventory/kpi").json()
    assert kpi["expired_count"] == 0
    # アラートの期限一覧にも出ない
    assert all(r["item_id"] != it["id"] for r in admin_client.get("/alerts/expiring").json())


def test_B01_invalid_date_rejected(admin_client):
    r = admin_client.post("/items", json={"item_name": "x", "category": "消耗品", "expiry_date": "2026/13/01"})
    assert r.status_code == 422
    assert "日付" in r.json()["detail"]


def test_B02_reorder_point_drives_low_stock(admin_client, db, item_id):
    # 在庫50・発注点10 → 不足ではない
    assert all(r["item_id"] != item_id for r in admin_client.get("/alerts/low-stock").json())
    r = admin_client.patch(f"/items/{item_id}", json={"reorder_point": 60})
    assert r.status_code == 200, r.text
    assert any(r["item_id"] == item_id for r in admin_client.get("/alerts/low-stock").json())
    db.expire_all()
    assert db.query(Inventory).filter(Inventory.item_id == item_id).one().threshold == 60


def test_B02_new_item_threshold_from_reorder_point(admin_client, db):
    it = _new_item(admin_client, reorder_point=3, initial_quantity=2)
    inv = db.query(Inventory).filter(Inventory.item_id == it["id"]).one()
    assert inv.threshold == 3
    assert inv.quantity == 2
    # 初期在庫は履歴に残る
    hist = admin_client.get("/history", params={"q": "マスク"}).json()["items"]
    assert hist and hist[0]["quantity"] == 2


def test_B03_location_text_shown_in_inventory(admin_client, item_id):
    row = next(r for r in admin_client.get("/inventory").json()["items"] if r["item_id"] == item_id)
    assert row["location"] == "棚A"


def test_B04_null_price_does_not_500(admin_client, item_id):
    r = admin_client.patch(f"/items/{item_id}", json={"unit_price": None})
    assert r.status_code in (200, 422)
    r2 = admin_client.patch(f"/items/{item_id}", json={"unit_price": -5})
    assert r2.status_code == 422


def test_B05_duplicates_return_409_japanese(admin_client):
    r = admin_client.post("/vendors", json={"vendor_code": "V001", "vendor_name": "別名"})
    assert r.status_code == 409
    assert "登録" in r.json()["detail"]
    assert admin_client.post("/categories", json={"name": "消耗品"}).status_code == 409
    assert admin_client.post("/departments", json={"name": "検査科"}).status_code == 409
    assert admin_client.post(
        "/users", json={"username": "taro", "password": "password1", "display_name": "x", "user_role": "USER"}
    ).status_code == 409


def test_B05_unknown_category_rejected(admin_client):
    r = admin_client.post("/items", json={"item_name": "x", "category": "存在しない"})
    assert r.status_code == 400
    assert "カテゴリ" in r.json()["detail"]


def test_B06_validation_error_is_japanese_string(user_client, item_id):
    r = user_client.post("/outbound", json={"item_id": item_id, "quantity": 0})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, str)
    assert "数量" in detail and "1" in detail


def test_B15_search_case_insensitive_and_escapes_wildcards(admin_client):
    _new_item(admin_client, item_name="Syringe 5mL", item_code="SY-5")
    names = [r["item_name"] for r in admin_client.get("/inventory", params={"q": "syringe"}).json()["items"]]
    assert "Syringe 5mL" in names
    assert admin_client.get("/inventory", params={"q": "%"}).json()["total"] == 0
    assert admin_client.get("/items", params={"q": "_"}).json()["total"] == 0


def test_B16_category_filter_exact(admin_client):
    _new_item(admin_client, item_name="消毒液", category="薬品")
    rows = admin_client.get("/inventory", params={"category": "薬品"}).json()["items"]
    assert [r["item_name"] for r in rows] == ["消毒液"]


def test_B17_today_is_jst():
    from app.utils.datetime import jst_today

    assert len(jst_today().isoformat()) == 10


def test_B19_unit_default_and_shown(admin_client):
    it = _new_item(admin_client, item_name="ガーゼ", unit="箱")
    assert it["unit"] == "箱"
    row = next(r for r in admin_client.get("/inventory").json()["items"] if r["item_id"] == it["id"])
    assert row["unit"] == "箱"
    default = _new_item(admin_client, item_name="綿棒")
    assert default["unit"] == "個"


def test_B20_inventory_csv_has_bom(user_client):
    r = user_client.get("/inventory/export.csv")
    assert r.status_code == 200
    assert r.content.startswith("﻿".encode())
    text = r.content.decode("utf-8-sig")
    assert "物品名" in text and "手袋" in text


def test_B21_inventory_row_has_price_and_vendor(user_client, item_id):
    row = next(r for r in user_client.get("/inventory").json()["items"] if r["item_id"] == item_id)
    assert row["unit_price"] == 100.0
    assert row["vendor_name"] == "テスト商事"


def test_item_detail_has_quantity(admin_client, item_id):
    d = admin_client.get(f"/items/{item_id}").json()
    assert d["quantity"] == 50
    assert d["threshold"] == 10


def test_items_reactivate(admin_client, item_id):
    assert admin_client.delete(f"/items/{item_id}").status_code == 204
    assert admin_client.get("/items").json()["total"] == 0
    assert admin_client.get("/items", params={"include_inactive": True}).json()["total"] == 1
    assert admin_client.patch(f"/items/{item_id}", json={"is_active": 1}).status_code == 200
    assert stock_of(admin_client, item_id) == 50


def test_E06_unhandled_error_message_japanese():
    from app.main import GENERIC_ERROR_MESSAGE

    assert "エラー" in GENERIC_ERROR_MESSAGE
