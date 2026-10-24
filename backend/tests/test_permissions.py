"""権限のテスト（テスト設計表 R）。

全部の API を「ログインなし・ゲスト・一般（本人）・一般（他人）・管理者」で呼び、
表のとおり「できる／403（権限なし）／401（ログインが要る）」になるかを確かめる。
部署：本人 taro＝検査科、他人 hanako＝看護部、ゲスト＝看護部（hanako と同じ部署）。
部署で変わる行（承認・廃棄の連絡）は SAME_DEPT＝ゲストと同じ部署の一般と管理者。細かい範囲は test_departments.py。
API を足したらこの表にも足すこと（足さないと test_R00 が落ちる）。
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.main import app
from app.models import (
    Category,
    Department,
    DisposalNotice,
    DisposalRequest,
    InventoryHistory,
    Item,
    PendingTransaction,
    PurchaseRequest,
    StocktakeRecord,
    StocktakeSession,
    User,
    Vendor,
)
from app.utils.datetime import jst_now

ROLES = ("anon", "guest", "other", "user", "admin")  # other＝ほかの一般ユーザー（hanako）を本人（taro）より先に呼ぶ（本人の操作で状態が変わる前に）
LOGIN_AS = {"guest": "guest", "user": "taro", "other": "hanako", "admin": "admin"}
ALL = {"guest", "user", "other", "admin"}
USERS_UP = {"user", "other", "admin"}
ADMIN = {"admin"}
OWNER_OR_ADMIN = {"user", "admin"}
SAME_DEPT = {"other", "admin"}  # ゲスト（看護部）と同じ部署の一般（hanako）と管理者（I-07 / I-08）
GUEST_ONLY = {"guest"}
PUBLIC = "public"  # ログインなしでも呼べる


@dataclass
class Row:
    id: str
    method: str
    path: str
    allowed: set[str] | str
    body: Callable[[dict], dict] | None = None
    params: dict = field(default_factory=dict)
    note: str = ""


def _b(d: dict) -> Callable[[dict], dict]:
    return lambda ctx: {k: (v(ctx) if callable(v) else v) for k, v in d.items()}


ITEM = lambda c: c["item"]  # noqa: E731
TABLE: list[Row] = [
    # ---- 認証・メタ ----
    Row("R01", "GET", "/healthz", PUBLIC),
    Row("R02", "GET", "/readyz", PUBLIC),
    Row("R03", "POST", "/auth/login", PUBLIC, _b({"username": "taro", "password": "user1234"})),
    Row("R04", "POST", "/auth/logout", PUBLIC),
    Row("R05", "POST", "/auth/refresh", "skip", note="リフレッシュ用の Cookie が要る。test_auth_users / test_security で確かめる"),
    Row("R06", "GET", "/auth/me", ALL),
    Row("R07", "POST", "/auth/password", ALL, _b({"current_password": "wrong-pass", "new_password": "newpass12"})),
    # ---- 見る ----
    Row("R10", "GET", "/inventory", ALL),
    Row("R11", "GET", "/inventory/kpi", ALL),
    Row("R12", "GET", "/inventory/export.csv", ALL),
    Row("R13", "GET", "/items", ALL),
    Row("R14", "GET", "/items/{item}", ALL),
    Row("R15", "GET", "/history", ALL),
    Row("R16", "GET", "/history/export.csv", ALL),
    Row("R17", "GET", "/alerts/low-stock", ALL),
    Row("R18", "GET", "/alerts/expiring", ALL),
    Row("R19", "GET", "/stats/monthly", ALL),
    Row("R20", "GET", "/stats/top-outbound", ALL),
    Row("R21", "GET", "/stats/by-department", ALL),
    Row("R22", "GET", "/stats/todo", USERS_UP),
    Row("R23", "GET", "/vendors", USERS_UP),
    Row("R24", "GET", "/categories", ALL),
    Row("R25", "GET", "/departments", ALL),
    Row("R26", "GET", "/purchase-requests", USERS_UP),
    Row("R27", "GET", "/disposal-requests", USERS_UP),
    Row("R28", "GET", "/outbound/my-requests", ALL),
    Row("R29", "GET", "/stocktake/sessions", USERS_UP),
    Row("R30", "GET", "/stocktake/sessions/{session}", USERS_UP),
    Row("R31", "GET", "/stocktake/sessions/{session}/records", USERS_UP),
    Row("R32", "GET", "/stocktake/sessions/{session}/export.xlsx", USERS_UP),
    Row("R33", "GET", "/ai/order-suggest", USERS_UP),
    Row("R34", "POST", "/ai/query", USERS_UP, _b({"question": "在庫は？"})),
    # ---- 在庫を動かす ----
    Row("R40", "POST", "/outbound", ALL, _b({"item_id": ITEM, "quantity": 1}), note="ゲストは申請になる"),
    Row("R41", "POST", "/outbound/bulk", ALL, _b({"items": lambda c: [{"item_id": c["item"], "quantity": 1}]})),
    Row("R42", "POST", "/inbound", USERS_UP, _b({"item_id": ITEM, "quantity": 1})),
    Row("R43", "POST", "/inbound/receive", USERS_UP, _b({"purchase_request_id": lambda c: c["pr"], "received_qty": 1})),
    Row("R44", "POST", "/adjust", ADMIN, _b({"item_id": ITEM, "new_quantity": 3, "reason": "数え直し"})),
    Row("R45", "POST", "/history/{history}/undo", OWNER_OR_ADMIN, note="本人（管理者は全員分）"),
    # ---- 申請と承認 ----
    Row("R50", "POST", "/purchase-requests", USERS_UP, _b({"item_id": ITEM, "requested_qty": 1})),
    Row("R51", "POST", "/purchase-requests/bulk", USERS_UP, _b({"items": lambda c: [{"item_id": c["item"], "requested_qty": 1}]})),
    Row("R52", "PATCH", "/purchase-requests/{pr}", OWNER_OR_ADMIN, _b({"note": "変更"}), note="本人（管理者は全員分）"),
    Row("R53", "DELETE", "/purchase-requests/{pr}", OWNER_OR_ADMIN),
    Row("R54", "GET", "/purchase-candidates", ADMIN),
    Row("R55", "PATCH", "/purchase-candidates/{pr}", ADMIN, _b({"note": "x"})),
    Row("R56", "POST", "/disposal-requests", USERS_UP, _b({"item_id": ITEM, "quantity": 1, "reason": "破損"})),
    Row("R57", "DELETE", "/disposal-requests/{dr}", OWNER_OR_ADMIN),
    Row("R58", "POST", "/disposal-requests/{dr}/approve", ADMIN, _b({"approve": True})),
    Row("R59", "GET", "/approvals", USERS_UP, note="一般は自分の部署の分だけ"),
    Row("R60", "POST", "/approvals/{pending}/decide", SAME_DEPT, _b({"approve": True})),
    Row("R61", "POST", "/orders/preview", ADMIN, _b({"request_ids": lambda c: [c["pr"]]})),
    Row("R62", "POST", "/orders/email", ADMIN, _b({"payload": {"vendor": "x", "items": []}})),
    Row("R63", "POST", "/orders/pdf", ADMIN, _b({"payload": {"vendor": "x", "items": []}})),
    Row("R64", "POST", "/orders/excel", ADMIN, _b({"payloads": [{"vendor": "x", "items": []}]})),
    Row("R65", "POST", "/orders/mark-ordered", ADMIN, _b({"request_ids": lambda c: [c["pr"]]})),
    Row("R66", "GET", "/purchase-requests/summary", ADMIN),
    Row("R67", "POST", "/purchase-requests/bulk-decide", ADMIN, _b({"ids": lambda c: [c["pr"]], "status": "APPROVED"})),
    # ---- ゲストの廃棄は部署への連絡（I-08） ----
    Row("R68", "GET", "/disposal-notices", ALL, note="ゲストは本人の分、一般は自分の部署の分"),
    Row("R69", "POST", "/disposal-notices", GUEST_ONLY, _b({"item_id": ITEM, "quantity": 1, "reason": "破損"})),
    Row("R75", "POST", "/disposal-notices/{notice}/promote", SAME_DEPT, _b({})),
    Row("R76", "POST", "/disposal-notices/{notice}/dismiss", SAME_DEPT, _b({})),
    Row("R77", "DELETE", "/disposal-notices/{notice}", GUEST_ONLY, note="ゲスト本人だけ"),
    # ---- 棚卸し ----
    Row("R70", "POST", "/stocktake/sessions", ADMIN, _b({"name": "2つ目"})),
    Row("R71", "POST", "/stocktake/sessions/{session}/refresh-items", ADMIN),
    Row("R72", "POST", "/stocktake/sessions/{session}/apply", ADMIN),
    Row("R73", "POST", "/stocktake/sessions/{session}/cancel", ADMIN),
    Row("R74", "PATCH", "/stocktake/records/{record}", USERS_UP, _b({"actual_qty": 1})),
    # ---- マスタ・ユーザー・メンテナンス ----
    Row("R80", "POST", "/items", ADMIN, _b({"item_name": "新しい物品", "category": "消耗品"})),
    Row("R81", "PATCH", "/items/{item}", ADMIN, _b({"location_text": "棚Z"})),
    Row("R82", "DELETE", "/items/{item}", ADMIN),
    Row("R83", "POST", "/vendors", ADMIN, _b({"vendor_code": "V900", "vendor_name": "新業者"})),
    Row("R84", "PATCH", "/vendors/{vendor}", ADMIN, _b({"phone": "000"})),
    Row("R85", "POST", "/categories", ADMIN, _b({"name": "新カテゴリ"})),
    Row("R86", "PATCH", "/categories/{category}", ADMIN, _b({"is_active": 1})),
    Row("R87", "DELETE", "/categories/{category}", ADMIN),
    Row("R88", "POST", "/departments", ADMIN, _b({"name": "新部署"})),
    Row("R89", "PATCH", "/departments/{department}", ADMIN, _b({"is_active": 1})),
    Row("R90", "DELETE", "/departments/{department}", ADMIN),
    Row("R91", "GET", "/users", ADMIN),
    Row("R92", "POST", "/users", ADMIN, _b({"username": "newone", "password": "password1", "display_name": "新人", "user_role": "USER"})),
    Row("R93", "PATCH", "/users/{target_user}", ADMIN, _b({"display_name": "改名"})),
    Row("R94", "DELETE", "/users/{target_user}", ADMIN),
    Row("R95", "GET", "/maintenance/schema", ADMIN),
    Row("R96", "POST", "/maintenance/repair-inventory", ADMIN),
    Row("R97", "POST", "/demo/seed", set(), note="DEMO_MODE が無効のときは管理者でも 403"),
]


@pytest.fixture
def ctx(db) -> dict:
    """表のパスに入れる ID を用意する（本人＝taro が作った申請・履歴）。"""
    by = {u.username: u for u in db.query(User).all()}
    item = db.query(Item).filter(Item.item_code == "G001").one()
    now = jst_now()
    pr = PurchaseRequest(item_id=item.id, requested_qty=3, requested_by_user_id=by["taro"].id, status="PENDING", created_at=now)
    dr = DisposalRequest(item_id=item.id, quantity=1, reason="破損", requester_id=by["taro"].id, status="PENDING", created_at=now)
    pt = PendingTransaction(change_type="OUT", item_id=item.id, quantity=1, actor_name="ゲスト",
                            guest_user_id=by["guest"].id, department_id=by["guest"].department_id, status="PENDING", created_at=now)
    hist = InventoryHistory(item_id=item.id, change_type="OUT", quantity=1, user_name="山田太郎", department="検査科",
                            status="CONFIRMED", created_by=by["taro"].id, created_at=now)
    sess = StocktakeSession(name="棚卸し", status="OPEN", created_by=by["admin"].id, created_at=now)
    notice = DisposalNotice(item_id=item.id, quantity=1, reason="破損", reporter_id=by["guest"].id,
                            department_id=by["guest"].department_id, status="OPEN", created_at=now)
    db.add_all([pr, dr, pt, hist, sess, notice])
    db.flush()
    rec = StocktakeRecord(session_id=sess.id, item_id=item.id, system_qty=50, status="PENDING")
    db.add(rec)
    db.commit()
    return {
        "item": item.id, "pr": pr.id, "dr": dr.id, "notice": notice.id, "pending": pt.id, "history": hist.id, "session": sess.id, "record": rec.id,
        "vendor": db.query(Vendor).first().id, "category": db.query(Category).filter(Category.name == "薬品").one().id,
        "department": db.query(Department).filter(Department.name == "看護部").one().id, "target_user": by["hanako"].id,
        "users": by,
    }


def _client(role: str, ctx: dict) -> TestClient:
    c = TestClient(app)
    if role != "anon":
        u = ctx["users"][LOGIN_AS[role]]
        c.cookies.set("zk_access", create_access_token(sub=u.username, role=u.user_role, extra={"uid": u.id, "ver": 0}))
    return c


def _call(c: TestClient, row: Row, ctx: dict):
    path = row.path.format(**ctx)
    body = row.body(ctx) if row.body else None
    return c.request(row.method, path, json=body, params=row.params)


@pytest.mark.parametrize("row", [r for r in TABLE if r.allowed != "skip"], ids=lambda r: f"{r.id}-{r.method}-{r.path}")
def test_R_matrix(row: Row, ctx, _override_db):
    """ロールの順に呼ぶ（admin を最後にして、状態を変える操作の影響を受けにくくする）。"""
    problems = []
    for role in ROLES:
        status = _call(_client(role, ctx), row, ctx).status_code
        if row.allowed == PUBLIC:
            expected_ok = True
        elif role == "anon":
            if status != 401:
                problems.append(f"{role}: ログインなしなのに {status}（401 のはず）")
            continue
        else:
            expected_ok = role in row.allowed
        if expected_ok and status in (401, 403):
            problems.append(f"{role}: できるはずなのに {status}")
        if not expected_ok and status != 403:
            problems.append(f"{role}: できないはずなのに {status}（403 のはず）")
        assert status < 500, f"{row.id} {role}: サーバーエラー {status}"
    assert not problems, f"{row.id} {row.method} {row.path}: " + " / ".join(problems)


def test_R00_every_api_is_in_the_table():
    """API を足したのに権限の表に書き忘れていないか。"""
    # FastAPI は取り込んだルーターを入れ子のまま持つので、API の一覧（OpenAPI）から数える
    routes = {(m.upper(), path) for path, ops in app.openapi()["paths"].items() for m in ops}
    normalized = {(m, re.sub(r"\{[^}]+\}", "{}", p)) for m, p in routes}
    table = {(r.method, re.sub(r"\{[^}]+\}", "{}", r.path)) for r in TABLE}
    missing = sorted(normalized - table)
    extra = sorted(table - normalized)
    assert not missing, f"権限の表に無い API: {missing}"
    assert not extra, f"表にあるのに存在しない API: {extra}"
