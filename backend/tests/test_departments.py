"""部署ごとの機能のテスト（受け入れ条件 I 章・テスト設計表 R-D と P-17〜P-22）。

テストの人：一般 taro＝検査科／一般 hanako＝看護部／ゲスト guest＝看護部／管理者 admin＝検査科。
物品：A＝検査科の物品／B＝看護部の物品／C＝共通（どれも在庫20・発注点30＝在庫不足・期限は10日後）。
"""
from __future__ import annotations

import csv
import io
from datetime import timedelta

import pytest

from app.models import Department, DisposalRequest, Inventory, InventoryHistory, Item
from app.utils.datetime import jst_today

NAMES = {"A物品", "B物品", "C物品"}


@pytest.fixture
def depts(db) -> dict[str, int]:
    return {d.name: d.id for d in db.query(Department).all()}


@pytest.fixture
def abc(db, depts) -> dict[str, int]:
    soon = (jst_today() + timedelta(days=10)).isoformat()
    spec = {"A": (depts["検査科"], 0), "B": (depts["看護部"], 0), "C": (None, 1)}
    ids = {}
    for key, (owner, common) in spec.items():
        it = Item(item_name=f"{key}物品", item_code=f"{key}-01", category="消耗品", vendor_name="テスト商事",
                  vendor_item_code=f"V-{key}", unit_price=100.0, reorder_point=30, expiry_date=soon,
                  owner_department_id=owner, is_common=common)
        db.add(it)
        db.flush()
        db.add(Inventory(item_id=it.id, quantity=20, threshold=30))
        ids[key] = it.id
    db.commit()
    return ids


@pytest.fixture
def hanako_client(make_client):
    return make_client("hanako")


@pytest.fixture
def who(admin_client, user_client, hanako_client, guest_client) -> dict:
    return {"admin": admin_client, "taro": user_client, "hanako": hanako_client, "guest": guest_client}


def _p(scope):
    return {"scope": scope} if scope else {}


def _csv(resp) -> list[list[str]]:
    assert resp.status_code == 200, resp.text
    return list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))


# ---------------- I-01 / I-02：物品の所属部署と全社共通 ----------------
def test_I01_item_needs_department_or_common(admin_client, depts):
    base = {"category": "消耗品"}
    r = admin_client.post("/items", json={**base, "item_name": "どちらも無し", "is_common": 0})
    assert r.status_code == 400 and "所属部署" in r.json()["detail"]
    r = admin_client.post("/items", json={**base, "item_name": "何も指定しない"})
    assert r.status_code == 201 and r.json()["is_common"] == 1 and r.json()["owner_department_id"] is None
    r = admin_client.post("/items", json={**base, "item_name": "検査科の物", "owner_department_id": depts["検査科"]})
    assert r.status_code == 201 and r.json()["is_common"] == 0 and r.json()["owner_department_id"] == depts["検査科"]
    r = admin_client.post("/items", json={**base, "item_name": "総務の共通品", "owner_department_id": depts["検査科"], "is_common": 1})
    assert r.status_code == 201 and r.json()["is_common"] == 1
    assert admin_client.post("/items", json={**base, "item_name": "無い部署", "owner_department_id": 99999}).status_code == 400


def test_I01_inactive_department_rejected(admin_client, depts):
    assert admin_client.delete(f"/departments/{depts['看護部']}").status_code == 204
    r = admin_client.post("/items", json={"item_name": "無効な部署", "category": "消耗品", "owner_department_id": depts["看護部"]})
    assert r.status_code == 400


def test_I01_update_keeps_the_rule(admin_client, abc):
    # 共通をやめるには所属部署が要る
    assert admin_client.patch(f"/items/{abc['C']}", json={"is_common": 0}).status_code == 400
    assert admin_client.get(f"/items/{abc['C']}").json()["is_common"] == 1
    # 部署だけの物品から部署を外せない
    assert admin_client.patch(f"/items/{abc['A']}", json={"owner_department_id": None}).status_code == 400
    assert admin_client.get(f"/items/{abc['A']}").json()["owner_department_id"] is not None
    # 部署を外して共通にするのは同時ならできる
    r = admin_client.patch(f"/items/{abc['A']}", json={"owner_department_id": None, "is_common": 1})
    assert r.status_code == 200 and r.json()["is_common"] == 1


# ---------------- I-03：見える物品（R-D1） ----------------
RD1 = [
    ("taro", None, {"A物品", "C物品"}),
    ("taro", "dept", {"A物品", "C物品"}),
    ("taro", "all", NAMES),
    ("hanako", None, {"B物品", "C物品"}),
    ("guest", None, {"B物品", "C物品"}),
    ("guest", "all", {"B物品", "C物品"}),  # ゲストは切り替えられない
    ("admin", None, NAMES),
    ("admin", "dept", {"A物品", "C物品"}),
]


@pytest.mark.parametrize(("person", "scope", "expected"), RD1, ids=[f"{a}-{b}" for a, b, _ in RD1])
def test_RD1_visible_items(who, abc, person, scope, expected):
    c, p = who[person], _p(scope)
    assert {r["item_name"] for r in c.get("/inventory", params=p).json()["items"]} & NAMES == expected
    assert {r["item_name"] for r in c.get("/alerts/low-stock", params=p).json()} & NAMES == expected
    assert {r["item_name"] for r in c.get("/alerts/expiring", params=p).json()} & NAMES == expected
    assert {r["item_name"] for r in c.get("/items", params=p).json()["items"]} & NAMES == expected
    assert {row[0] for row in _csv(c.get("/inventory/export.csv", params=p))[1:]} & NAMES == expected
    # KPI の品目数＝見える物品＋共通の「手袋」（conftest）
    assert c.get("/inventory/kpi", params=p).json()["total_items"] == len(expected) + 1
    if person != "guest":
        assert {r["item_name"] for r in c.get("/ai/order-suggest", params=p).json()} & NAMES == expected


def test_RD1_user_without_department_sees_common_only(admin_client, make_client, abc):
    r = admin_client.post("/users", json={"username": "nodept", "password": "password1", "display_name": "部署なし", "user_role": "USER"})
    assert r.status_code == 201, r.text
    c = make_client(None)
    assert c.post("/auth/login", json={"username": "nodept", "password": "password1"}).status_code == 200
    assert c.post("/auth/password", json={"current_password": "password1", "new_password": "password2"}).status_code == 200
    assert {r["item_name"] for r in c.get("/inventory").json()["items"]} & NAMES == {"C物品"}


def test_P18_changing_owner_moves_the_item(admin_client, user_client, hanako_client, abc, depts):
    def taro_sees():
        return {r["item_name"] for r in user_client.get("/inventory").json()["items"]} & NAMES

    def hanako_kpi():
        return hanako_client.get("/inventory/kpi").json()["total_items"]

    before = hanako_kpi()
    assert admin_client.patch(f"/items/{abc['A']}", json={"owner_department_id": depts["看護部"]}).status_code == 200
    assert taro_sees() == {"C物品"}
    assert hanako_kpi() == before + 1
    assert admin_client.patch(f"/items/{abc['B']}", json={"is_common": 1}).status_code == 200
    assert taro_sees() == {"B物品", "C物品"}


# ---------------- I-04：ゲストはほかの部署の物品を使えない（R-D2） ----------------
def test_RD2_guest_cannot_use_other_department_items(guest_client, abc):
    assert guest_client.get(f"/items/{abc['A']}").status_code == 403
    assert guest_client.get(f"/items/{abc['B']}").status_code == 200
    assert guest_client.get(f"/items/{abc['C']}").status_code == 200
    assert guest_client.post("/outbound", json={"item_id": abc["A"], "quantity": 1}).status_code == 403
    assert guest_client.post("/outbound/bulk", json={"items": [{"item_id": abc["B"], "quantity": 1}, {"item_id": abc["A"], "quantity": 1}]}).status_code == 403
    assert guest_client.get("/outbound/my-requests").json() == []  # 403 のときは何も残らない
    assert guest_client.post("/disposal-notices", json={"item_id": abc["A"], "quantity": 1, "reason": "破損"}).status_code == 403
    assert guest_client.post("/outbound", json={"item_id": abc["B"], "quantity": 1}).status_code == 201
    assert guest_client.post("/disposal-notices", json={"item_id": abc["C"], "quantity": 1, "reason": "破損"}).status_code == 201


# ---------------- I-07：同じ部署の一般がゲストの出庫申請を承認する（R-D3・P-21） ----------------
def test_RD3_P21_same_department_user_approves_guest_outbound(who, abc, db):
    guest, taro, hanako, admin = who["guest"], who["taro"], who["hanako"], who["admin"]
    pid = guest.post("/outbound", json={"item_id": abc["B"], "quantity": 3}).json()["pending_id"]
    assert pid
    assert hanako.get("/stats/todo").json()["guest_outbound"] == 1
    assert taro.get("/stats/todo").json()["guest_outbound"] == 0
    assert [p["id"] for p in hanako.get("/approvals").json()["items"]] == [pid]
    assert taro.get("/approvals").json()["total"] == 0  # ほかの部署の申請は一覧にも出ない
    assert pid in [p["id"] for p in admin.get("/approvals").json()["items"]]
    r = taro.post(f"/approvals/{pid}/decide", json={"approve": True})
    assert r.status_code == 403 and "ほかの部署" in r.json()["detail"]
    r = hanako.post(f"/approvals/{pid}/decide", json={"approve": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED"
    inv = admin.get("/inventory").json()["items"]
    assert next(i["quantity"] for i in inv if i["item_id"] == abc["B"]) == 17
    last = admin.get("/history").json()["items"][0]
    assert (last["change_type"], last["quantity"], last["user_name"], last["department"]) == ("OUT", 3, "ゲスト", "看護部")
    assert hanako.get("/stats/todo").json()["guest_outbound"] == 0
    assert admin.get("/approvals").json()["total"] == 0
    # 二重の承認は 409
    assert hanako.post(f"/approvals/{pid}/decide", json={"approve": True}).status_code == 409


def test_RD3_same_department_user_rejects(who, abc):
    pid = who["guest"].post("/outbound", json={"item_id": abc["B"], "quantity": 1}).json()["pending_id"]
    assert who["hanako"].post(f"/approvals/{pid}/decide", json={"approve": False}).status_code == 400  # 理由が要る
    r = who["hanako"].post(f"/approvals/{pid}/decide", json={"approve": False, "reject_reason": "数が多い"})
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    mine = who["guest"].get("/outbound/my-requests").json()
    assert (mine[0]["status"], mine[0]["reject_reason"]) == ("REJECTED", "数が多い")


# ---------------- I-08：ゲストの廃棄は部署への連絡（R-D4・P-19・P-20） ----------------
def test_RD4_P19_P20_notice_promoted_to_disposal_request(who, abc, db):
    guest, taro, hanako, admin = who["guest"], who["taro"], who["hanako"], who["admin"]
    assert guest.post("/disposal-requests", json={"item_id": abc["B"], "quantity": 1, "reason": "破損"}).status_code == 403
    before_admin = admin.get("/stats/todo").json()
    r = guest.post("/disposal-notices", json={"item_id": abc["B"], "quantity": 2, "reason": "箱がつぶれている"})
    assert r.status_code == 201, r.text
    nid = r.json()["id"]
    assert r.json()["status"] == "OPEN" and r.json()["department"] == "看護部"
    # P-19：看護部の一般に届く。在庫・廃棄申請・管理者の廃棄の処理待ちは変わらない
    assert [n["id"] for n in hanako.get("/disposal-notices").json()["items"]] == [nid]
    assert taro.get("/disposal-notices").json()["total"] == 0
    assert [n["id"] for n in guest.get("/disposal-notices").json()["items"]] == [nid]
    assert hanako.get("/stats/todo").json()["disposal_notices"] == 1
    assert taro.get("/stats/todo").json()["disposal_notices"] == 0
    assert admin.get("/disposal-requests").json()["total"] == 0
    assert admin.get("/stats/todo").json()["disposal"] == before_admin["disposal"]
    assert next(i["quantity"] for i in admin.get("/inventory").json()["items"] if i["item_id"] == abc["B"]) == 20
    # ほかの部署の一般は上げられない
    assert taro.post(f"/disposal-notices/{nid}/promote", json={}).status_code == 403
    assert taro.post(f"/disposal-notices/{nid}/dismiss", json={}).status_code == 403
    # P-20：看護部の一般が数量・理由を直して正式な申請に上げる
    r = hanako.post(f"/disposal-notices/{nid}/promote", json={"quantity": 1, "reason": "1箱だけ破損"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PROMOTED" and r.json()["disposal_request_id"]
    dr = db.get(DisposalRequest, r.json()["disposal_request_id"])
    assert (dr.quantity, dr.reason, dr.status, dr.department_id) == (1, "1箱だけ破損", "PENDING", db.query(Department).filter_by(name="看護部").one().id)
    listed = admin.get("/disposal-requests").json()["items"]
    assert [(d["requester"], d["department"]) for d in listed] == [("佐藤花子", "看護部")]
    assert admin.get("/stats/todo").json()["disposal"] == before_admin["disposal"] + 1
    assert hanako.get("/stats/todo").json()["disposal_notices"] == 0
    assert next(i["quantity"] for i in admin.get("/inventory").json()["items"] if i["item_id"] == abc["B"]) == 20
    # 二重に上げられない
    assert hanako.post(f"/disposal-notices/{nid}/promote", json={}).status_code == 409
    assert admin.post(f"/disposal-notices/{nid}/dismiss", json={}).status_code == 409
    # ゲスト本人の一覧で結果が分かる
    mine = guest.get("/disposal-notices").json()["items"][0]
    assert (mine["status"], mine["handled_by"]) == ("PROMOTED", "佐藤花子")


def test_RD4_notice_dismiss_and_withdraw(who, abc, db, depts):
    guest, hanako, admin = who["guest"], who["hanako"], who["admin"]
    n1 = guest.post("/disposal-notices", json={"item_id": abc["C"], "quantity": 1, "reason": "汚れ"}).json()["id"]
    r = hanako.post(f"/disposal-notices/{n1}/dismiss", json={"comment": "まだ使える"})
    assert r.status_code == 200 and (r.json()["status"], r.json()["handled_comment"]) == ("DISMISSED", "まだ使える")
    assert guest.delete(f"/disposal-notices/{n1}").status_code == 409  # 対応済みは取り下げられない
    n2 = guest.post("/disposal-notices", json={"item_id": abc["C"], "quantity": 1, "reason": "汚れ"}).json()["id"]
    assert hanako.delete(f"/disposal-notices/{n2}").status_code == 403
    assert admin.delete(f"/disposal-notices/{n2}").status_code == 403
    assert guest.delete(f"/disposal-notices/{n2}").status_code == 204
    assert guest.delete(f"/disposal-notices/{n2}").status_code == 409
    statuses = {n["id"]: n["status"] for n in guest.get("/disposal-notices").json()["items"]}
    assert statuses == {n1: "DISMISSED", n2: "CANCELLED"}
    # 管理者（検査科）は全部署の連絡を上げられる。上げた申請の部署は連絡したゲストの部署（看護部）
    n3 = guest.post("/disposal-notices", json={"item_id": abc["C"], "quantity": 1, "reason": "汚れ"}).json()["id"]
    r = admin.post(f"/disposal-notices/{n3}/promote", json={})
    assert r.status_code == 200
    assert db.get(DisposalRequest, r.json()["disposal_request_id"]).department_id == depts["看護部"]


def test_RD4_notice_validation(who, abc):
    guest, hanako = who["guest"], who["hanako"]
    assert guest.post("/disposal-notices", json={"item_id": abc["B"], "quantity": 21, "reason": "多すぎ"}).status_code == 400
    assert guest.post("/disposal-notices", json={"item_id": abc["B"], "quantity": 0, "reason": "x"}).status_code == 422
    assert guest.post("/disposal-notices", json={"item_id": abc["B"], "quantity": 1, "reason": "  "}).status_code == 422
    assert hanako.post("/disposal-notices", json={"item_id": abc["B"], "quantity": 1, "reason": "x"}).status_code == 403
    nid = guest.post("/disposal-notices", json={"item_id": abc["B"], "quantity": 1, "reason": "破損"}).json()["id"]
    # 上げる時点で在庫を超えていれば 400、連絡は未対応のまま
    assert hanako.post(f"/disposal-notices/{nid}/promote", json={"quantity": 21}).status_code == 400
    assert guest.get("/disposal-notices").json()["items"][0]["status"] == "OPEN"


# ---------------- I-05 / I-06：履歴・統計の「自分の部署」（R-D5・P-17） ----------------
@pytest.fixture
def three_ops(who, abc):
    """taro が共通の C、hanako が検査科の A と看護部の B を1つずつ出庫。"""
    assert who["taro"].post("/outbound", json={"item_id": abc["C"], "quantity": 1}).status_code == 201
    assert who["hanako"].post("/outbound", json={"item_id": abc["A"], "quantity": 1}).status_code == 201
    assert who["hanako"].post("/outbound", json={"item_id": abc["B"], "quantity": 1}).status_code == 201


ALL_OPS = {("C物品", "山田太郎"), ("A物品", "佐藤花子"), ("B物品", "佐藤花子")}
KENSA = {("C物品", "山田太郎"), ("A物品", "佐藤花子")}  # 検査科の人の操作＋検査科の物品への操作
KANGO = {("A物品", "佐藤花子"), ("B物品", "佐藤花子")}  # 看護部の人の操作（A・B）＋看護部の物品への操作（B）
RD5 = [("taro", None, KENSA), ("taro", "all", ALL_OPS), ("hanako", None, KANGO), ("guest", None, KANGO),
       ("guest", "all", KANGO), ("admin", None, ALL_OPS), ("admin", "dept", KENSA)]


@pytest.mark.parametrize(("person", "scope", "expected"), RD5, ids=[f"{a}-{b}" for a, b, _ in RD5])
def test_RD5_P17_history_and_stats_scope(who, three_ops, person, scope, expected):
    c, p = who[person], _p(scope)
    hist = {(h["item_name"], h["user_name"]) for h in c.get("/history", params=p).json()["items"] if h["item_name"] in NAMES}
    assert hist == expected
    rows = _csv(c.get("/history/export.csv", params=p))
    assert {(r[1], r[5]) for r in rows[1:] if r[1] in NAMES} == expected
    top = {r["item_name"]: r["total_quantity"] for r in c.get("/stats/top-outbound", params=p).json()}
    assert {k for k in top if k in NAMES} == {name for name, _ in expected}
    dept = {r["department"]: r["total_outbound"] for r in c.get("/stats/by-department", params=p).json()}
    assert sum(dept.values()) == len(expected)
    ym = jst_today().strftime("%Y-%m")
    monthly = {(r["ym"], r["change_type"]): r["total_quantity"] for r in c.get("/stats/monthly", params=p).json()}
    assert monthly.get((ym, "OUT"), 0) == len(expected)


def test_I06_history_keeps_department_id_after_rename(admin_client, hanako_client, three_ops, db, depts):
    kango = depts["看護部"]
    ids = {h.department_id for h in db.query(InventoryHistory).filter(InventoryHistory.user_name == "佐藤花子").all()}
    assert ids == {kango}
    assert admin_client.patch(f"/departments/{kango}", json={"name": "看護局"}).status_code == 200
    hist = {(h["item_name"], h["user_name"]) for h in hanako_client.get("/history").json()["items"] if h["item_name"] in NAMES}
    assert hist == KANGO


# ---------------- I-10：発注・廃棄の申請の一覧（R-D6） ----------------
def test_RD6_request_lists_scope(who, abc):
    taro, hanako, admin = who["taro"], who["hanako"], who["admin"]
    t = taro.post("/purchase-requests", json={"item_id": abc["C"], "requested_qty": 10}).json()["id"]
    h = hanako.post("/purchase-requests", json={"item_id": abc["C"], "requested_qty": 10}).json()["id"]
    dt = taro.post("/disposal-requests", json={"item_id": abc["C"], "quantity": 1, "reason": "破損"}).json()["id"]
    dh = hanako.post("/disposal-requests", json={"item_id": abc["C"], "quantity": 1, "reason": "破損"}).json()["id"]

    def ids(c, path, scope=None):
        return {r["id"] for r in c.get(path, params=_p(scope)).json()["items"]}

    assert ids(taro, "/purchase-requests") == {t}
    assert ids(taro, "/purchase-requests", "all") == {t, h}
    assert ids(hanako, "/purchase-requests") == {h}
    assert ids(admin, "/purchase-requests") == {t, h}
    assert ids(admin, "/purchase-requests", "dept") == {t}
    assert ids(taro, "/disposal-requests") == {dt}
    assert ids(taro, "/disposal-requests", "all") == {dt, dh}
    assert ids(admin, "/disposal-requests") == {dt, dh}
    assert who["guest"].get("/purchase-requests").status_code == 403
    assert who["guest"].get("/disposal-requests").status_code == 403


# ---------------- I-11 / I-12：申請のまとめ・まとめて承認・発注書は1行（P-22） ----------------
def test_I11_I12_P22_summary_bulk_decide_and_merged_order(who, abc):
    taro, hanako, admin = who["taro"], who["hanako"], who["admin"]
    t = taro.post("/purchase-requests", json={"item_id": abc["C"], "requested_qty": 10}).json()["id"]
    h = hanako.post("/purchase-requests", json={"item_id": abc["C"], "requested_qty": 15}).json()["id"]
    a = hanako.post("/purchase-requests", json={"item_id": abc["A"], "requested_qty": 5}).json()["id"]
    assert taro.get("/purchase-requests/summary").status_code == 403
    groups = {g["item_name"]: g for g in admin.get("/purchase-requests/summary").json()}
    c = groups["C物品"]
    assert (c["total_qty"], c["current_stock"], c["unit"]) == (25, 20, "個")
    assert {(d["department"], d["qty"]) for d in c["departments"]} == {("検査科", 10), ("看護部", 15)}
    assert {r["id"] for r in c["requests"]} == {t, h}
    assert groups["A物品"]["total_qty"] == 5
    # 検査科の分だけ承認し、看護部の分は却下
    r = admin.post("/purchase-requests/bulk-decide", json={"ids": [t, a], "status": "APPROVED"})
    assert r.status_code == 200, r.text
    assert {x["status"] for x in r.json()} == {"APPROVED"}
    assert admin.post("/purchase-requests/bulk-decide", json={"ids": [h], "status": "REJECTED", "admin_comment": "今月は検査科の分だけ"}).status_code == 200
    assert "C物品" not in {g["item_name"] for g in admin.get("/purchase-requests/summary").json()}
    statuses = {p["id"]: p["status"] for p in admin.get("/purchase-requests").json()["items"]}
    assert statuses == {t: "APPROVED", h: "REJECTED", a: "APPROVED"}


def test_I11_bulk_decide_all_or_nothing(who, abc):
    taro, admin = who["taro"], who["admin"]
    p1 = taro.post("/purchase-requests", json={"item_id": abc["C"], "requested_qty": 1}).json()["id"]
    p2 = taro.post("/purchase-requests", json={"item_id": abc["C"], "requested_qty": 1}).json()["id"]
    assert admin.post("/purchase-requests/bulk-decide", json={"ids": [p1], "status": "REJECTED"}).status_code == 200
    assert admin.post("/purchase-requests/bulk-decide", json={"ids": [p1, p2], "status": "APPROVED"}).status_code == 409
    statuses = {p["id"]: p["status"] for p in admin.get("/purchase-requests").json()["items"]}
    assert statuses == {p1: "REJECTED", p2: "PENDING"}
    assert admin.post("/purchase-requests/bulk-decide", json={"ids": [], "status": "APPROVED"}).status_code == 422
    assert admin.post("/purchase-requests/bulk-decide", json={"ids": [p2], "status": "ORDERED"}).status_code == 422
    assert admin.post("/purchase-requests/bulk-decide", json={"ids": [99999], "status": "APPROVED"}).status_code == 409


def test_I12_order_merges_same_item(who, abc):
    taro, hanako, admin = who["taro"], who["hanako"], who["admin"]
    t = taro.post("/purchase-requests", json={"item_id": abc["C"], "requested_qty": 10}).json()["id"]
    h = hanako.post("/purchase-requests", json={"item_id": abc["C"], "requested_qty": 15}).json()["id"]
    assert admin.post("/purchase-requests/bulk-decide", json={"ids": [t, h], "status": "APPROVED"}).status_code == 200
    payloads = admin.post("/orders/preview", json={"request_ids": [t, h]}).json()["payloads"]
    assert len(payloads) == 1
    lines = payloads[0]["items"]
    assert len(lines) == 1
    assert (lines[0]["item_name"], lines[0]["quantity"], lines[0]["subtotal"]) == ("C物品", 25, 2500.0)
    assert "検査科 10" in lines[0]["notes"] and "看護部 15" in lines[0]["notes"]
    assert payloads[0]["total"] == 2500.0


# ---------------- I-09：ゲストに単価・業者を出さない（R-D7） ----------------
def test_RD7_guest_never_sees_price_or_vendor(who, abc):
    guest, taro = who["guest"], who["taro"]
    assert who["hanako"].post("/inbound", json={"item_id": abc["B"], "quantity": 2, "vendor_name": "テスト商事", "unit_price": 120}).status_code == 201
    row = next(r for r in guest.get("/inventory").json()["items"] if r["item_id"] == abc["B"])
    assert (row["unit_price"], row["vendor_name"]) == (None, None)
    for item in [guest.get(f"/items/{abc['B']}").json(), *[i for i in guest.get("/items").json()["items"] if i["id"] == abc["B"]]]:
        assert (item["unit_price"], item["vendor_name"], item["vendor_item_code"]) == (None, None, None)
    header = _csv(guest.get("/inventory/export.csv"))[0]
    assert "業者" not in header and "単価" not in header
    h = next(x for x in guest.get("/history").json()["items"] if x["item_name"] == "B物品")
    assert (h["vendor_name"], h["unit_price"], h["total_price"]) == (None, None, None)
    header = _csv(guest.get("/history/export.csv"))[0]
    assert not {"業者", "単価", "合計"} & set(header)
    # 一般には出る
    row = next(r for r in taro.get("/inventory", params={"scope": "all"}).json()["items"] if r["item_id"] == abc["B"])
    assert (row["unit_price"], row["vendor_name"]) == (100.0, "テスト商事")
    assert "単価" in _csv(taro.get("/history/export.csv"))[0]


# ---------------- すり抜け対策（わざと壊す確認で見つかる穴を先に塞ぐ） ----------------
def _new_user(admin_client, make_client, username: str, role: str, dept_id: int | None):
    body = {"username": username, "password": "password1", "display_name": username, "user_role": role}
    if dept_id is not None:
        body["department_id"] = dept_id
    assert admin_client.post("/users", json=body).status_code == 201
    c = make_client(None)
    assert c.post("/auth/login", json={"username": username, "password": "password1"}).status_code == 200
    assert c.post("/auth/password", json={"current_password": "password1", "new_password": "password2"}).status_code == 200
    return c


def test_I05_own_operations_are_always_in_my_history(admin_client, make_client, abc):
    """部署の無い一般でも、自分の操作は既定の履歴に出る。"""
    c = _new_user(admin_client, make_client, "nodept2", "USER", None)
    assert c.post("/outbound", json={"item_id": abc["C"], "quantity": 1}).status_code == 201
    assert [h["item_name"] for h in c.get("/history").json()["items"]] == ["C物品"]


def test_I10_own_requests_stay_after_moving_department(who, abc, depts, db):
    taro, admin = who["taro"], who["admin"]
    t = taro.post("/purchase-requests", json={"item_id": abc["C"], "requested_qty": 1}).json()["id"]
    d = taro.post("/disposal-requests", json={"item_id": abc["C"], "quantity": 1, "reason": "破損"}).json()["id"]
    taro_id = next(u["id"] for u in admin.get("/users").json() if u["username"] == "taro")
    assert admin.patch(f"/users/{taro_id}", json={"department_id": depts["看護部"]}).status_code == 200
    assert t in {r["id"] for r in taro.get("/purchase-requests").json()["items"]}
    assert d in {r["id"] for r in taro.get("/disposal-requests").json()["items"]}


def test_I07_approved_guest_outbound_counts_for_guest_department(who, abc):
    """承認した出庫の履歴はゲストの部署（看護部）のもの。共通の物品でも看護部の既定の履歴に出る。"""
    pid = who["guest"].post("/outbound", json={"item_id": abc["C"], "quantity": 1}).json()["pending_id"]
    assert who["hanako"].post(f"/approvals/{pid}/decide", json={"approve": True}).status_code == 200
    mine = {(h["item_name"], h["user_name"]) for h in who["hanako"].get("/history").json()["items"]}
    assert ("C物品", "ゲスト") in mine
    assert ("C物品", "ゲスト") not in {(h["item_name"], h["user_name"]) for h in who["taro"].get("/history").json()["items"]}


def test_I08_notice_goes_only_to_its_department(admin_client, make_client, who, abc, depts, db):
    """検査科のゲストの連絡は検査科の一般にだけ届き、看護部のゲスト・一般には見えない。管理者が上げても部署は検査科。"""
    g2 = _new_user(admin_client, make_client, "guest_kensa", "GUEST", depts["検査科"])
    nid = g2.post("/disposal-notices", json={"item_id": abc["C"], "quantity": 1, "reason": "汚れ"}).json()["id"]
    assert who["guest"].get("/disposal-notices").json()["total"] == 0
    assert who["hanako"].get("/disposal-notices").json()["total"] == 0
    assert [n["id"] for n in who["taro"].get("/disposal-notices").json()["items"]] == [nid]
    assert who["hanako"].post(f"/disposal-notices/{nid}/promote", json={}).status_code == 403
    r = who["admin"].post(f"/disposal-notices/{nid}/promote", json={})
    assert r.status_code == 200
    dr = db.get(DisposalRequest, r.json()["disposal_request_id"])
    assert dr.department_id == depts["検査科"]
