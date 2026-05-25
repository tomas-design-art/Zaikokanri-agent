"""Inventory + outbound/inbound flows."""
from __future__ import annotations


def test_inventory_kpi(user_client):
    r = user_client.get("/inventory/kpi")
    assert r.status_code == 200
    body = r.json()
    assert body["total_items"] >= 1
    assert body["total_quantity"] >= 50


def test_inventory_list(user_client):
    r = user_client.get("/inventory", params={"per_page": 50})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    assert items[0]["quantity"] == 50


def test_outbound_decrements_stock(user_client):
    items = user_client.get("/inventory").json()["items"]
    item_id = items[0]["item_id"]
    r = user_client.post("/outbound", json={"item_id": item_id, "quantity": 5})
    assert r.status_code in (200, 201), r.text
    after = user_client.get("/inventory").json()["items"]
    assert next(i for i in after if i["item_id"] == item_id)["quantity"] == 45


def test_outbound_blocked_when_insufficient(user_client):
    items = user_client.get("/inventory").json()["items"]
    item_id = items[0]["item_id"]
    r = user_client.post("/outbound", json={"item_id": item_id, "quantity": 999})
    assert r.status_code == 400


def test_inbound_increments_stock(user_client):
    items = user_client.get("/inventory").json()["items"]
    item_id = items[0]["item_id"]
    r = user_client.post("/inbound", json={"item_id": item_id, "quantity": 30, "unit_price": 120})
    assert r.status_code in (200, 201), r.text
    after = user_client.get("/inventory").json()["items"]
    assert next(i for i in after if i["item_id"] == item_id)["quantity"] == 80


def test_inventory_requires_auth(client):
    r = client.get("/inventory")
    assert r.status_code == 401
