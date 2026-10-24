"""テストが本当にバグを捕まえるかを確かめる（ミューテーションテスト）。

業務の決めごとをコードの1か所ずつ「わざと壊し」、テストを流す。
  - テストが赤になる   → 捕まえた（killed）＝そのテストは決めごとを守っている
  - テストが緑のまま   → すり抜けた（survived）＝テストが足りない
壊したファイルは毎回必ず元に戻す。

    cd backend
    .venv/Scripts/python scripts/mutation_check.py            # 全部
    .venv/Scripts/python scripts/mutation_check.py M01 M07    # 指定したものだけ

すり抜けが1つでもあれば終了コード 1。「同じ動きになる書き換え（等価）」は理由を書いて EQUIVALENT に入れる。
"""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PYTEST = [sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", "--no-header"]


@dataclass(frozen=True)
class Mutant:
    id: str
    file: str
    old: str
    new: str
    rule: str  # 壊したことで破られる決めごと（受け入れ条件の番号）


A = "app/"
M = Mutant
MUTANTS: list[Mutant] = [
    # ---- 在庫を動かす処理（B） ----
    M("M01", A + "services/stock_service.py", "if inv.quantity < quantity:", "if inv.quantity <= quantity:", "B: 在庫ちょうどまで出庫できる（境界）"),
    M("M02", A + "services/stock_service.py", "quantity > settings.outbound_max:", "quantity >= settings.outbound_max:", "B: 出庫の上限ちょうど（1000）は通る（境界）"),
    M("M03", A + "services/stock_service.py", "quantity > settings.inbound_max:", "quantity > settings.inbound_max * 100:", "B: 入庫の上限を超えると弾く"),
    M("M04", A + "services/stock_service.py", "if diff == 0:", "if False:", "B-12: 差が0の調整は弾く"),
    M("M05", A + "services/stock_service.py", "delta = max(diff, -inv.quantity)", "delta = diff", "D: 棚卸しの反映で在庫をマイナスにしない"),
    M("M06", A + "services/stock_service.py", "if inv.quantity < h.quantity:", "if False:", "B-10: 入庫の取消で在庫をマイナスにしない"),
    M("M07", A + "services/stock_service.py", '.where(InventoryHistory.id == h.id, InventoryHistory.status == "CONFIRMED")', ".where(InventoryHistory.id == h.id)", "B-10 / H-07: 同じ履歴を2回取り消せない（同時でも）"),
    M("M08", A + "services/stock_service.py", "if not is_admin and h.created_by != user_id:", "if h.created_by != user_id:", "B-10: 管理者は全員分を取り消せる"),
    M("M09", A + "services/stock_service.py", "if not is_admin and h.created_by != user_id:", "if False:", "B-10: 他人の操作は取り消せない"),
    M("M10", A + "services/stock_service.py", "if jst_now() - h.created_at > timedelta(minutes=settings.undo_minutes):", "if False:", "B-10: 10分を過ぎたら取り消せない"),
    M("M11", A + "services/stock_service.py", 'if h.change_type not in {"IN", "OUT"} or h.ref_type not in UNDOABLE_REF_TYPES:', 'if h.change_type not in {"IN", "OUT"}:', "B-10: 受領・承認・取消の履歴は取り消せない"),
    M("M12", A + "services/stock_service.py", "if not item or not item.is_active:", "if not item:", "B: 無効な物品は動かせない"),
    M("M13", A + "services/stock_service.py", "created_by=actor.user_id,", "created_by=None,", "B-10: 履歴に操作者IDを残す"),
    # ---- 申請の状態遷移（C） ----
    M("M14", A + "services/workflow.py", ".where(model.id == obj_id, model.status.in_(from_statuses))", ".where(model.id == obj_id)", "C-01: 二重の承認を防ぐ"),
    M("M15", A + "services/workflow.py", "if not approve and not reason:", "if False:", "C-02: 却下には理由が要る"),
    M("M16", A + "routers/outbound.py", "if user.department_id is None:", "if False:", "B-08: 部署のないゲストは申請できない"),
    M("M17", A + "routers/outbound.py", "    check_outbound(item, inv, line.quantity)\n", "", "B-08: ゲストの申請でも在庫を確かめる"),
    M("M18", A + "routers/approvals.py", "department=dept.name if dept else None", "department=None", "B-08: 承認後の履歴に部署を残す"),
    M("M19", A + "routers/disposal_requests.py", '        check_outbound(item, inv, body.quantity, verb="廃棄")\n', "", "C-03: 廃棄申請で在庫を確かめる"),
    M("M20", A + "routers/disposal_requests.py", "if d.requester_id != user.id and not user.is_admin:", "if False:", "C-03: 他人の廃棄申請は取り下げられない"),
    M("M21", A + "routers/purchase_requests.py", "if pr.status not in EDITABLE_BY_REQUESTER:", "if False:", "C-04: 承認後は申請者が直せない"),
    M("M22", A + "routers/purchase_requests.py", "elif pr.status not in DECIDABLE:", "elif False:", "C-04: 発注済・受領済は管理者でも状態を変えられない"),
    M("M23", A + "routers/purchase_requests.py", "if pr.status not in allowed:", "if False:", "C-07: 承認後は申請者が取り下げられない"),
    M("M24", A + "routers/inbound.py", "if body.received_qty > remaining:", "if body.received_qty > remaining + 1:", "C-05: 残数を超えて受領できない"),
    M("M25", A + "routers/inbound.py", 'status=case((new_received >= PurchaseRequest.requested_qty, "RECEIVED"), else_="ORDERED")', 'status="ORDERED"', "C-05: 全数そろったら受領済"),
    M("M26", A + "routers/inbound.py", 'if pr.status not in {"APPROVED", "ORDERED"}:', "if False:", "C-05: 承認前の申請は受領できない"),
    M("M27", A + "routers/orders.py", 'PurchaseRequest.status == "APPROVED",', "", "C-06: 発注済にするのは承認済だけ"),
    M("M28", A + "routers/stats.py", "    if not user.is_admin:\n        pt = pt.filter", "    if False:\n        pt = pt.filter", "C-09: 一般ユーザーの処理待ちは自分の分だけ"),
    # ---- 棚卸し（D） ----
    M("M29", A + "services/stocktake_service.py", "r.system_qty = inv.quantity if inv else 0", "pass", "D-02: 帳簿数は数えた時点の在庫"),
    M("M30", A + "services/stocktake_service.py", "if db.query(StocktakeSession).filter(StocktakeSession.status == OPEN).first():", "if False:", "D-07: 実施中は1つだけ"),
    M("M31", A + "services/stocktake_service.py", "if s.status != OPEN:", "if False:", "D-03: 完了・中止後は入力できない"),
    M("M32", A + "services/stocktake_service.py", "        if r.diff_qty:\n", "        if False:\n", "D-01: 差異を在庫に反映する"),
    M("M33", A + "services/stocktake_service.py", "    claim(db, StocktakeSession, sid, to_status=CLOSED, from_statuses=(OPEN,))\n", "    db.get(StocktakeSession, sid).status = CLOSED\n", "D-01: 2回確定して二重に反映しない"),
    M("M34", A + "services/stocktake_service.py", ".filter(Item.is_active == 1, Item.is_inventory_target == 1)", ".filter(Item.is_active == 1)", "D: 棚卸しの対象外の物品は含めない"),
    M("M35", A + "services/stocktake_service.py", "    if category:\n        q = q.filter(Item.category == category)", "    pass", "D-07: カテゴリで対象を絞る"),
    M("M36", A + "services/stocktake_service.py", "StocktakeRecord.actual_qty.is_(None)).count()", "StocktakeRecord.actual_qty.is_not(None)).count()", "D-09: 未カウントの件数を正しく返す"),
    # ---- 認証・ユーザー（A / G） ----
    M("M37", A + "auth/deps.py", 'if not payload or payload.get("type") != "access":', "if not payload:", "A-01: リフレッシュ用のトークンでは操作できない"),
    M("M38", A + "auth/deps.py", 'if payload.get("ver", 0) != (user.token_version or 0):', "if False:", "G-03: パスワード変更前のトークンは使えない"),
    M("M39", A + "auth/deps.py", "if current.must_change_password and request.url.path not in _ALLOWED_WHILE_MUST_CHANGE:", "if False:", "A-03: パスワード変更が必須なら業務APIは使えない"),
    M("M40", A + "auth/deps.py", 'User.username == payload.get("sub"), User.is_active == 1', 'User.username == payload.get("sub")', "A: 無効にしたユーザーはすぐ使えなくなる"),
    M("M41", A + "routers/auth.py", 'if not payload or payload.get("type") != "refresh":', "if not payload:", "A-01: アクセス用のトークンではリフレッシュできない"),
    M("M42", A + "routers/auth.py", "if user.failed_login_count >= settings.login_max_failures:", "if user.failed_login_count > settings.login_max_failures:", "G-02: 10回目の失敗でロック（境界）"),
    M("M43", A + "routers/auth.py", "if user.locked_until and user.locked_until > now:", "if False:", "G-02: ロック中は正しいパスワードでも入れない"),
    M("M44", A + "routers/auth.py", "    user.failed_login_count, user.locked_until = 0, None\n    if is_legacy:", "    if is_legacy:", "G-02: 成功したら失敗回数を戻す"),
    M("M45", A + "routers/auth.py", "verify_password(body.password, _DUMMY_HASH)", "None", "G-04: ユーザーがいなくても同じ重さの照合"),
    M("M46", A + "routers/auth.py", "    revoke_sessions(user)\n    db.commit()\n    security_event(\"password_changed\"", "    db.commit()\n    security_event(\"password_changed\"", "G-03: 自分で変えたら他の端末のログインを無効に"),
    M("M47", A + "routers/auth.py", 'if not user or not user.is_active:\n        verify_password', 'if not user:\n        verify_password', "A: 無効なユーザーはログインできない"),
    M("M48", A + "routers/users.py", "if target.id == me.id:", "if False:", "A-02: 自分自身を無効化・降格できない"),
    M("M49", A + "routers/users.py", "must_change_password=1,", "must_change_password=0,", "A-03: 管理者が作ったユーザーは変更必須"),
    M("M50", A + "routers/users.py", "        revoke_sessions(u)  # ほかの端末のログインも無効にする（G-03）\n", "", "G-03: リセットで他の端末のログインを無効に"),
    M("M51", A + "routers/users.py", "    u.is_active = 0\n    revoke_sessions(u)\n", "    u.is_active = 0\n", "G-03: 無効化で他の端末のログインを無効に"),
    M("M52", A + "schemas/common.py", "if len(v.encode(\"utf-8\")) > 72:", "if len(v.encode(\"utf-8\")) > 720:", "G-05: 72バイトを超えるパスワードは弾く"),
    M("M53", A + "schemas/common.py", "NewPassword = Annotated[str, Field(min_length=8,", "NewPassword = Annotated[str, Field(min_length=7,", "A-06: 8文字未満は弾く（境界）"),
    # ---- 権限（ロールごとにできること） ----
    M("M54", A + "routers/adjust.py", "user: CurrentUser = Depends(require_admin)", "user: CurrentUser = Depends(require_user)", "権限: 在庫調整は管理者だけ"),
    M("M55", A + "routers/items.py", "def create_item(body: ItemCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin))", "def create_item(body: ItemCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user))", "権限: 物品の登録は管理者だけ"),
    M("M56", A + "routers/inbound.py", "def create_inbound(body: InboundCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user))", "def create_inbound(body: InboundCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user))", "権限: ゲストは入庫できない"),
    M("M57", A + "routers/purchase_requests.py", "def create_pr(body: PRCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user))", "def create_pr(body: PRCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user))", "権限: ゲストは発注申請できない"),
    M("M58", A + "routers/stocktake.py", "def update_record(rid: int, body: RecordUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user))", "def update_record(rid: int, body: RecordUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user))", "権限: ゲストは棚卸しを入力できない"),
    M("M59", A + "routers/stocktake.py", "def apply_session(sid: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin))", "def apply_session(sid: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user))", "権限: 棚卸しの確定は管理者だけ"),
    M("M60", A + "routers/approvals.py", "pid: int, body: ApproveRequest, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)", "pid: int, body: ApproveRequest, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user)", "権限: ゲスト出庫の承認は管理者だけ"),
    M("M61", A + "routers/disposal_requests.py", "def approve_dr(dr_id: int, body: DRApprove, db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin))", "def approve_dr(dr_id: int, body: DRApprove, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user))", "権限: 廃棄の承認は管理者だけ"),
    M("M62", A + "routers/history.py", "def undo(hid: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_user))", "def undo(hid: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user))", "権限: ゲストは取り消せない"),
    M("M63", A + "routers/maintenance.py", "def repair_inventory(db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin))", "def repair_inventory(db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user))", "権限: メンテナンスは管理者だけ"),
    M("M64", A + "routers/vendors.py", "def create_vendor(body: VendorBase, db: Session = Depends(get_db), _: CurrentUser = Depends(require_admin))", "def create_vendor(body: VendorBase, db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user))", "権限: 業者の登録は管理者だけ"),
    M("M65", A + "routers/orders.py", "def mark_ordered(\n    body: IdsIn,\n    db: Session = Depends(get_db),\n    _: object = Depends(require_admin),", "def mark_ordered(\n    body: IdsIn,\n    db: Session = Depends(get_db),\n    _: object = Depends(require_user),", "権限: 発注済にするのは管理者だけ"),
    M("M66", A + "auth/deps.py", "return ROLE_LEVEL.get(self.role, 0) >= ROLE_LEVEL.get(required, 99)", "return ROLE_LEVEL.get(self.role, 0) >= ROLE_LEVEL.get(required, 99) - 1", "権限: 役割の上下関係"),
    # ---- 在庫一覧・アラート（B） ----
    M("M67", A + "services/inventory_view.py", "is_low_stock=inv.quantity <= inv.threshold,", "is_low_stock=inv.quantity < inv.threshold,", "B-02: 発注点ちょうどは在庫不足（境界）"),
    M("M68", A + "services/inventory_view.py", "query = query.filter(Inventory.quantity <= Inventory.threshold)", "query = query.filter(Inventory.quantity < Inventory.threshold)", "B-02: アラートも発注点ちょうどを含む（境界）"),
    M("M69", A + "services/inventory_view.py", "expired = bool(item.expiry_date and item.expiry_date < today)", "expired = bool(item.expiry_date and item.expiry_date <= today)", "B: 期限が今日の物品は期限切れではない（境界）"),
    M("M70", A + "services/inventory_view.py", "is_expiring_soon=bool(item.expiry_date and not expired and item.expiry_date <= soon),", "is_expiring_soon=bool(item.expiry_date and not expired and item.expiry_date < soon),", "B: 30日後ちょうどは期限間近（境界）"),
    M("M71", A + "services/inventory_view.py", "    if inv and item.reorder_point is not None:\n        inv.threshold = item.reorder_point", "    pass", "B-02: 発注点を在庫不足の判定に反映"),
    M("M72", A + "routers/inventory.py", "with_expiry.filter(Item.expiry_date < today).count()", "with_expiry.filter(Item.expiry_date <= today).count()", "B: KPI の期限切れに今日の物品を数えない（境界）"),
    M("M73", A + "routers/stats.py", '        or_(InventoryHistory.ref_type.is_(None), InventoryHistory.ref_type != "UNDO"),\n', "", "E-01: 取り消した操作は統計に入れない"),
    M("M74", A + "routers/history.py", "query = query.filter(InventoryHistory.created_at < end)", "query = query.filter(InventoryHistory.created_at < start)", "E-04: 終了日の日中の履歴も含める"),
    # ---- 入力と出力（B / G） ----
    M("M75", A + "utils/text.py", '.replace("%", LIKE_ESCAPE + "%")', "", "B-15: % を文字として検索する"),
    M("M76", A + "utils/text.py", "return v or None", "return v", "B-01: 空文字は未設定にする"),
    M("M77", A + "utils/text.py", 'FORMULA_PREFIXES = ("=", "+", "-", "@", "\\t", "\\r")', 'FORMULA_PREFIXES = ("=",)', "G-01: + - @ で始まる値も数式にさせない"),
    M("M78", A + "utils/xlsx.py", '        cell.data_type = "s"\n', "        pass\n", "G-01: Excel は文字として書く"),
    M("M79", A + "errors.py", "if _is_unique_violation(exc):", "if False:", "B-05: 重複は 409"),
    M("M80", A + "middleware/security.py", '== "cross-site"', '== "never"', "G-07: 他サイトからの書き込みは拒否"),
    M("M81", A + "services/ai_query.py", "if words & _blocked_tables():", "if False:", "E-02: 読めないテーブルを参照させない"),
    M("M82", A + "config.py", "len(s.jwt_secret) < 32", "len(s.jwt_secret) < 3", "G-09: 本番は32文字未満の秘密鍵で起動しない"),
    M("M83", A + "routers/items.py", "    _check_category(db, body.category)\n", "", "B-05: 登録されていないカテゴリは弾く"),
    M("M84", A + "routers/items.py", "if v is None and k in _NOT_NULL:", "if False:", "B-04: 空の単価で 500 にしない"),
    # ---- 7観点レビューの指摘（H）で入れた守り ----
    M("M85", A + "services/stock_service.py", ".where(Inventory.id == inv.id, Inventory.quantity + signed_change >= 0)", ".where(Inventory.id == inv.id)", "H-01: 同時でも在庫をマイナスにしない"),
    M("M86", A + "services/stock_service.py", ".values(quantity=Inventory.quantity + signed_change,", ".values(quantity=inv.quantity + signed_change,", "H-01: 同時の入出庫で片方の更新を消さない"),
    M("M87", A + "services/ai_query.py", "return calls <= ALLOWED_FUNCTIONS", "return True", "H-02: SQL を組み立てて実行する関数を通さない"),
    M("M88", A + "schemas/common.py", "if not _ISO_DATE.fullmatch(v):", "if False:", "X-06: 日付は YYYY-MM-DD だけ"),
    M("M89", A + "schemas/items.py", "unit_price: float | None = Field(default=None, ge=0, le=100_000_000, allow_inf_nan=False)", "unit_price: float | None = Field(default=None, ge=0, le=100_000_000)", "H-08: 単価に無限大を入れない"),
    M("M90", A + "services/stocktake_service.py", "if not item or not item.is_active:", "if not item:", "H-03: 無効にした物品は飛ばして確定する"),
    M("M91", A + "services/stocktake_service.py", "if (res.change if res else 0) != r.diff_qty:", "if False:", "H-05: 0で止めた物品を知らせる"),
    M("M92", A + "routers/users.py", "if u.id == me.id and body.password:", "if False:", "H-13: 自分のパスワードを変えても今の画面は続く"),
    M("M93", A + "routers/auth.py", 'user=username if user else f"(不明・{len(username)}文字)"', "user=username", "H-13: 存在しないユーザー名は記録に残さない"),
    M("M94", A + "services/stocktake_service.py", "    if current != OPEN:\n", "    if False:\n", "H-12: 完了後の入力は書き込みの後でも止める"),
]

# 書き換えても動きが変わらないもの（テストで捕まえられないのが正しい）。理由を必ず書く。
EQUIVALENT: dict[str, str] = {
    "M06": "入庫の取消でマイナスにしない事前チェック。消しても在庫の条件付き更新（H-01）が同じく止め、同じ 400 になる",
    "M30": "実施中は1つだけの事前チェック。消しても DB の一意インデックス（H-04）が止め、同じ 409 になる",
    "M89": "単価の allow_inf_nan=False。消しても上限 le・下限 ge が無限大・非数を弾き、同じ 422 になる",
}

# 壊したファイル → 流すテスト（全部流すと1件45秒かかるため）。無いファイルは飛ばす
_STOCK = ["test_stock_ops", "test_inventory", "test_requests", "test_boundaries", "test_propagation", "test_concurrency", "test_review_findings"]
_AUTH = ["test_auth_users", "test_auth", "test_security", "test_boundaries", "test_migrations", "test_review_findings"]
_VIEW = ["test_items_inventory", "test_stats_ai_health", "test_propagation", "test_boundaries", "test_review_findings"]
TEST_MAP: list[tuple[str, list[str]]] = [
    ("services/stock_service.py", _STOCK),
    ("services/workflow.py", _STOCK),
    ("services/stocktake_service.py", ["test_stocktake", "test_boundaries", "test_propagation", "test_concurrency", "test_review_findings"]),
    ("services/inventory_view.py", _VIEW),
    ("services/ai_query.py", ["test_stats_ai_health", "test_security", "test_review_findings"]),
    ("auth/", _AUTH + ["test_permissions", "test_rbac"]),
    ("routers/auth.py", _AUTH),
    ("routers/users.py", _AUTH),
    ("schemas/common.py", _AUTH + ["test_items_inventory"]),
    ("config.py", ["test_security"]),
    ("routers/", _STOCK + ["test_stocktake", "test_items_inventory", "test_stats_ai_health", "test_permissions", "test_rbac", "test_orders"]),
    ("", ["test_items_inventory", "test_security", "test_stats_ai_health", "test_boundaries", "test_review_findings"]),
]


def tests_for(mutant: Mutant, only_permissions: bool) -> list[str]:
    rel = mutant.file.removeprefix(A)
    names = next(names for prefix, names in TEST_MAP if rel.startswith(prefix))
    if only_permissions:  # 権限の書き換えは権限の表で捕まえるべきもの
        names = ["test_permissions", "test_rbac"] + names
    files = [f"tests/{n}.py" for n in dict.fromkeys(names) if (BACKEND / "tests" / f"{n}.py").exists()]
    return files or ["tests"]


def run(mutant: Mutant) -> tuple[str, float]:
    path = BACKEND / mutant.file
    raw = path.read_bytes()  # 改行コードを変えずに戻すため、バイトのまま持つ
    original = raw.decode("utf-8")
    count = original.count(mutant.old)
    if count != 1:
        return f"NOT_FOUND({count})", 0.0
    start = time.monotonic()
    try:
        path.write_bytes(original.replace(mutant.old, mutant.new).encode("utf-8"))
        files = tests_for(mutant, mutant.rule.startswith("権限"))
        res = subprocess.run(PYTEST + files, cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", errors="replace")
        status = "killed" if res.returncode != 0 else "SURVIVED"
    finally:
        path.write_bytes(raw)
    return status, time.monotonic() - start


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    targets = [m for m in MUTANTS if not argv or m.id in argv]
    bad = []
    for m in targets:
        status, sec = run(m)
        if m.id in EQUIVALENT and status == "SURVIVED":
            status = "equivalent"
        print(f"{m.id} {status:<12} {sec:5.1f}s  {m.rule}", flush=True)
        if status in {"SURVIVED"} or status.startswith("NOT_FOUND"):
            bad.append(m.id)
    killed = sum(1 for _ in targets) - len(bad)
    print(f"\n捕まえた {killed} / {len(targets)}　すり抜け・見つからない: {' '.join(bad) or 'なし'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
