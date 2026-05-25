# LEGACY FEATURE INVENTORY — Streamlit版 在庫管理システム 完全機能棚卸表

**目的**: FastAPI + Next.js への移行時に**機能を一切失わない**ための完全棚卸表。  
各項目は移植完了後に `[x]` でチェックする。100% 消化が完了条件。  
**凍結日**: 2026-05-25 / **基準コミット**: `v-streamlit-final` タグ参照

---

## 0. 共通仕様

| 観点 | 現行仕様 |
|---|---|
| 起動 | `streamlit run app.py` |
| 認証 | DB users テーブル / bcrypt + SHA-256+salt 両対応 / `verify_password()` で自動判定 |
| ロール | ADMIN(3) / USER(2) / GUEST(1) の3層 |
| 画面遷移 | `app.py::set_menu(menu_id)` 経由のみ（直接 session_state 代入禁止） |
| 時刻 | JST で保存。`CURRENT_TIMESTAMP` (UTC) は使用禁止 |
| 表示サイズ | サイドバー「小/中/大」→ `ui/css.py` で CSS 変数注入 |
| ページネーション | 手動実装、`session_state.current_page` + `<< < > >>` ボタン |
| デフォルト管理者 | `admin / admin123` |

---

## 1. ページ別機能棚卸

### 1.1 ログインページ ([ui/login.py](ui/login.py))
- [ ] ユーザー名 / パスワード入力
- [ ] 認証成功 → `session_state.logged_in = True`, `current_user` 設定 → `st.rerun()`
- [ ] 認証失敗時のエラーメッセージ
- [ ] bcrypt と SHA-256+salt 両ハッシュ対応
- [ ] レガシーハッシュ → 初回成功時に bcrypt 再ハッシュ（互換維持）

### 1.2 📦 在庫一覧 `inventory` ([ui/pages/inventory.py](ui/pages/inventory.py))
- [ ] 5列の KPI カード（総物品数 / 総在庫 / 不足品目 / 期限切れ / 期限間近）
- [ ] 検索ボックス（品目名・品目コード・業者名・業者品番 横断）
- [ ] カテゴリフィルタ（複数選択）
- [ ] 部署フィルタ
- [ ] ページネーション 50/100/200/500 件切替
- [ ] 在庫不足品目に ⚠️ マーク表示
- [ ] 期限切れ・期限間近の表示
- [ ] 列ソート対応
- [ ] CSV ダウンロード

### 1.3 🚨 アラート `alert` ([ui/pages/alert.py](ui/pages/alert.py))
- [ ] 3タブ：在庫不足 / 期限切れ / 期限間近
- [ ] 各タブの一覧表示
- [ ] 一括発注申請への遷移
- [ ] GUEST には表示限定

### 1.4 📝 発注申請 `purchase_request` ([ui/pages/purchase_request.py](ui/pages/purchase_request.py))
- [ ] 物品選択（検索付き selectbox）
- [ ] 数量入力（INBOUND_MAX 上限）
- [ ] 優先度（NORMAL / HIGH / URGENT）
- [ ] 希望納期入力
- [ ] 備考入力
- [ ] 申請送信 → `purchase_requests` テーブルに PENDING で登録
- [ ] 申請履歴の確認

### 1.5 🗑️ 廃棄申請 `disposal_request` ([ui/pages/disposal_request.py](ui/pages/disposal_request.py))
- [ ] 物品選択
- [ ] 数量入力（現在庫を超えない）
- [ ] 廃棄理由（期限切れ / 破損 / 不要 / その他）
- [ ] 申請送信 → `disposal_requests` に PENDING 登録

### 1.6 ➕ 入庫 `inbound` ([ui/pages/inbound.py](ui/pages/inbound.py))
- [ ] **タブ1：通常入庫** — 物品選択 / 数量 / 業者 / 単価 / 備考 / 送信
- [ ] **タブ2：発注経由受領** — APPROVED な purchase_request を一覧 → 受領数入力 → 在庫反映 + status=ORDERED
- [ ] バリデーション（INBOUND_MAX）
- [ ] 在庫加算 + `inventory_history` (IN) 同一 Tx 記録
- [ ] 成功メッセージ表示

### 1.7 ➖ 出庫 `outbound` ([ui/pages/outbound.py](ui/pages/outbound.py))
- [ ] **タブ1：単一出庫** — 検索 → 物品確定 → 数量入力 → 出庫実行
- [ ] **タブ2：一括出庫** — 複数物品を一度に選択 → 各数量入力 → 一括送信
- [ ] GUEST の場合は `pending_transactions` に申請として登録
- [ ] USER/ADMIN は即時 OUT 確定
- [ ] OUTBOUND_MAX バリデーション + 在庫不足チェック
- [ ] 当月 TOP10 ダッシュボード（消費量上位10品目）
- [ ] 直近出庫の取消（UNDO_MINUTES=10分以内）

### 1.8 📋 履歴 `history` ([ui/pages/history.py](ui/pages/history.py))
- [ ] 日付範囲フィルタ
- [ ] 部署フィルタ
- [ ] 変動タイプフィルタ（IN / OUT / DISPOSE / ORDER）
- [ ] ユーザーフィルタ
- [ ] 一覧表示（時刻 JST / 物品 / 種別 / 数量 / 担当 / 部署 / 備考）
- [ ] CSV エクスポート
- [ ] PDF エクスポート
- [ ] 取消可能エントリ（UNDO_MINUTES 以内）にボタン表示

### 1.9 📊 集計 `stats` ([ui/pages/statistics.py](ui/pages/statistics.py))
- [ ] 部署別出庫集計
- [ ] 月別推移グラフ
- [ ] 部品消費ランキング TOP N
- [ ] 期間フィルタ

### 1.10 🤖 AIアシスタント `ai` ([ui/pages/ai_assistant.py](ui/pages/ai_assistant.py))
- [ ] 自然言語クエリ入力欄
- [ ] OpenAI で SQL 生成
- [ ] **安全実行**: read-only / SELECT のみ / LIMIT 強制
- [ ] 結果を `st.dataframe` で表示
- [ ] 発注提案モード（在庫不足を AI が要約）
- [ ] AI_ENABLED=false の場合は無効表示

### 1.11 ✅ 承認管理 `approval` ([ui/pages/approval.py](ui/pages/approval.py))
- [ ] GUEST 出庫申請の一覧（USER=自部署のみ、ADMIN=全部署）
- [ ] 承認 → 在庫減算 + history(OUT) 同一 Tx
- [ ] 却下 → 理由入力必須
- [ ] 承認待ち件数表示（サイドバーバッジ連動）

### 1.12 ✅ 廃棄承認 `disposal_approval` ([ui/pages/disposal_approval.py](ui/pages/disposal_approval.py))
- [ ] ADMIN のみアクセス
- [ ] 廃棄申請一覧
- [ ] 承認 → 在庫減算 + history(DISPOSE) 同一 Tx
- [ ] 却下 → 理由入力

### 1.13 ✅ 発注申請管理 `purchase_admin` ([ui/pages/purchase_admin.py](ui/pages/purchase_admin.py))
- [ ] ADMIN のみアクセス
- [ ] PENDING 申請一覧
- [ ] 承認 / 保留 / 却下 / 管理者コメント
- [ ] **複数申請を選択 → 業者別に発注書 payload 自動分割**
- [ ] **発注書出力**：メール文面 / PDF (fpdf2+NotoSansJP) / Excel (openpyxl)
- [ ] AI 文案生成（gpt-4o-mini）
- [ ] 出力後 status=ORDERED + history(ORDER) 記録

### 1.14 🔧 在庫調整 `adjust` ([ui/pages/adjust.py](ui/pages/adjust.py))
- [ ] ADMIN のみアクセス
- [ ] 物品選択 / 新数量入力 / 理由コメント必須
- [ ] 差分を `inventory_history` (IN または OUT) として記録

### 1.15 📦 物品マスター `item_master` ([ui/pages/item_master.py](ui/pages/item_master.py))
- [ ] ADMIN のみアクセス
- [ ] 物品 CRUD（品目名 / 品目コード / 業者 / 業者品番 / カテゴリ / 部署タグ / 単価 / 資産フラグ / 期限 / 頻度タグ）
- [ ] 検索・カテゴリフィルタ
- [ ] is_active 切替（論理削除）
- [ ] owner_department_id / is_common（全社共通）/ location_text
- [ ] 最終点検日 / 次回点検日 / 点検間隔月 / 発注点 / 棚卸対象フラグ

### 1.16 🏢 業者管理 `vendor` ([ui/pages/vendor.py](ui/pages/vendor.py))
- [ ] ADMIN のみアクセス
- [ ] 業者 CRUD（コード / 名前 / 住所 / 電話 / メール / is_active）
- [ ] 検索

### 1.17 👥 ユーザー管理 `users` ([ui/pages/users.py](ui/pages/users.py))
- [ ] ADMIN のみアクセス
- [ ] ユーザー CRUD（username / display_name / department_id / user_role / is_active）
- [ ] パスワードリセット（bcrypt で再ハッシュ）
- [ ] 自分自身の削除/無効化を防ぐガード

### 1.18 🏢 部署管理 `departments` ([ui/pages/departments.py](ui/pages/departments.py))
- [ ] ADMIN のみアクセス
- [ ] 部署 CRUD / is_active 切替

### 1.19 🛠️ メンテナンス `maintenance` ([ui/pages/maintenance.py](ui/pages/maintenance.py))
- [ ] ADMIN のみアクセス
- [ ] DB スキーマチェック表示
- [ ] レガシーデータ変換（INBOUND → IN 等）
- [ ] 整合性ボタン

### 1.20 🎭 デモモード `demo` ([ui/pages/demo.py](ui/pages/demo.py))
- [ ] ADMIN のみアクセス
- [ ] ダミーデータ投入 / 削除
- [ ] DEMO_MODE=true 時に有効

### 1.21〜1.25 棚卸し関連 5ページ ([ui/pages/stocktake/](ui/pages/stocktake/))
- [ ] **stocktake_sessions**: ADMIN がセッション CRUD・開始/終了
- [ ] **stocktake_entry**: アクティブセッション内で実地数入力 / 一括入力 / 進捗表示
- [ ] **stocktake_review**: ADMIN が差分確認 / 承認 / 在庫反映
- [ ] **stocktake_report**: セッション別サマリ / 差分統計 / PDF・Excel 出力
- [ ] **stocktake_admin**: ADMIN がテンプレート管理 / セッション一覧 / 一括削除

---

## 2. データモデル棚卸（14 テーブル全保持）

すべて [docs/LEGACY_DB_SCHEMA.md](LEGACY_DB_SCHEMA.md) 参照。要点：

| テーブル | 重要カラム | 移行注意 |
|---|---|---|
| items | id, item_name, item_code, vendor_name, category, department_tags(CSV), unit_price, is_asset, expiry_date, is_active, owner_department_id, is_common, reorder_point, is_inventory_target | UNIQUE(vendor_name, vendor_item_code) |
| inventory | item_id(UNIQUE), quantity, threshold, location, updated_at | FK→items |
| inventory_history | item_id, change_type(IN/OUT/DISPOSE/ORDER), quantity, user_name, department, status(PENDING/CONFIRMED/REJECTED), vendor_name, unit_price, total_price, created_by | 監査ログ兼用 |
| departments | name(UNIQUE), is_active | デフォルト6件 |
| categories | name(UNIQUE), is_active | デフォルト5件 |
| vendors | vendor_code(UNIQUE), vendor_name(UNIQUE), address, phone, email | デフォルト3件 |
| users | username(UNIQUE), password_hash, display_name, department, department_id, user_role, is_active | bcrypt + SHA-256 両形式 |
| pending_transactions | change_type, item_id, quantity, actor_name, guest_user_id, department_id, status, approved_by, reject_reason | ゲスト出庫申請 |
| disposal_requests | item_id, quantity, reason, requester_id, status, approved_by, reject_reason | 廃棄申請 |
| purchase_requests | item_id, requested_qty, priority, due_date, requested_by_user_id, requested_by_department, status(PENDING/APPROVED/ON_HOLD/REJECTED/ORDERED), admin_comment, deleted_at(論理削除) | 発注申請 |
| purchase_candidates | item_id, auto_reason, selected_for_order, deferred, priority, recommended_qty, status(OPEN/SELECTED/DEFERRED/ORDERED) | 発注候補選別 |
| stocktake_sessions | name, start_date, end_date, status(OPEN/CLOSED), created_by, closed_at | 棚卸セッション |
| stocktake_records | session_id, item_id, system_qty, actual_qty, diff_qty, counted_by, verified_by, approved_by, status(PENDING/COUNTED/VERIFIED/APPROVED/APPLIED) | 棚卸実績 |
| stocktake_templates / mappings | テンプレート + Excel セルマッピング | テンプレ機能 |

---

## 3. ビジネスロジック層棚卸

### 3.1 リポジトリ層（16ファイル → ほぼそのまま移植）
- [ ] base.py — DB接続管理
- [ ] inventory_query.py — 在庫一覧、カテゴリ取得、検索
- [ ] inventory_repo.py — process_outbound / process_inbound / 承認フロー
- [ ] history_repo.py — 履歴取得 / process_undo / process_undo_pending / process_adjust
- [ ] pending_repo.py — ゲスト出庫申請 CRUD + カウント
- [ ] disposal_repo.py — 廃棄申請 CRUD + 承認
- [ ] purchase_request_repo.py — 発注申請 CRUD + ステータス更新 + カウント
- [ ] purchase_candidate_repo.py — 発注候補自動抽出 + 選別状態管理
- [ ] item_repo.py — 物品マスター CRUD + 検索 + カテゴリ別集計
- [ ] vendor_repo.py — 業者 CRUD
- [ ] user_repo.py — authenticate_user + CRUD
- [ ] department_repo.py — 部署 CRUD
- [ ] category_repo.py — カテゴリ CRUD
- [ ] alert_repo.py — 不足 / 期限切れ / 期限間近 取得
- [ ] stats_repo.py — 月別 / TOP物品 / 部門集計
- [ ] stocktake_repo.py — セッション・記録・テンプレート CRUD + 差分計算

### 3.2 サービス層
- [ ] inventory_service.py — 出庫・入庫・調整の facade
- [ ] stocktake_service.py — 棚卸セッション・記録・差分・承認フロー

### 3.3 レンダラー（帳票・CSV・PDF）
- [ ] renderers/order_renderer.py — 発注書ファサード
- [ ] renderers/csv_renderer.py — 履歴CSV
- [ ] renderers/payload.py — payload ビルダー
- [ ] renderers/stocktake_renderer.py — 棚卸レポート
- [ ] order_output.py — `build_purchase_order_payloads()` 業者別分割
- [ ] purchase_order_payload.py — payload スキーマ・検証
- [ ] purchase_order_renderers.py — メール文面 / PDF / Excel 実装

### 3.4 AI
- [ ] ai.py — `call_openai_chat()` / `generate_purchase_order_text()` / フォールバック実装

### 3.5 ユーティリティ
- [ ] utils/auth.py — 権限チェック関数群
- [ ] utils/validation.py — to_int_safe など
- [ ] utils/logger.py — ログ
- [ ] utils/exceptions.py — ValidationError, InsufficientStockError 等
- [ ] utils/date_utils.py — JST タイムゾーン

---

## 4. 設定・環境変数棚卸

| 変数 | デフォルト | 移植先での扱い |
|---|---|---|
| `DB_PATH` | `./inventory.db` | `DATABASE_URL` (sqlite または postgresql) に変更 |
| `AI_ENABLED` | `false` | 同じ |
| `OPENAI_API_KEY` | (なし) | デプロイSecretのみ・git直書き禁止 |
| `OPENAI_MODEL` | `gpt-4o-mini` | 同じ |
| `LOG_LEVEL` | `INFO` | 同じ |
| `DEMO_MODE` | `false` | 同じ |
| `OUTBOUND_MAX` | 1000 | 定数維持 |
| `INBOUND_MAX` | 10000 | 定数維持 |
| `WARNING_THRESHOLD` | 100 | 定数維持 |
| `UNDO_MINUTES` | 10 | 定数維持 |
| `FONT_PATH` | `fonts/NotoSansJP-Regular.ttf` | バックエンドに同梱 |

新規追加:
- [ ] `JWT_SECRET` — JWT 署名鍵（環境変数のみ）
- [ ] `JWT_ALGORITHM` — `HS256`
- [ ] `JWT_ACCESS_TTL_MIN` — 30
- [ ] `JWT_REFRESH_TTL_DAYS` — 14
- [ ] `CORS_ORIGINS` — 許可オリジン CSV
- [ ] `FRONTEND_ORIGIN` — Vercel デプロイ URL

---

## 5. 動線（ページ間遷移）保持リスト

| From | To | トリガー |
|---|---|---|
| login | inventory | ログイン成功 |
| inventory | item detail (modal/page) | 行クリック |
| inventory | outbound | KPI「在庫不足」クリック |
| alert | purchase_request | 「一括発注申請へ」ボタン |
| purchase_request | purchase_admin | 申請後（USER は履歴へ、ADMIN は承認画面へ） |
| approval | history | 承認後の確認 |
| purchase_admin | history (ORDER 記録) | 発注書生成完了 |
| stocktake_sessions | stocktake_entry | セッション開始 |
| stocktake_entry | stocktake_review | 入力完了 |
| stocktake_review | stocktake_report | 承認完了 |
| sidebar | 任意ページ | メニュークリック（ロール別動的） |
| sidebar バッジ | approval / disposal_approval / purchase_admin | 件数表示でユーザを誘導 |

---

## 6. UI/UX 保持項目（移植先で再現必須）

- [ ] 表示サイズ切替（小/中/大）→ CSS 変数で再現
- [ ] サイドバー：ロール別動的メニュー + 承認待ちバッジ + ユーザー情報表示
- [ ] KPI カード 5列レイアウト
- [ ] タブ分割（出庫 単一/一括、入庫 通常/発注経由）
- [ ] 当月 TOP10 ダッシュボード
- [ ] 一覧テーブル：sticky header / 列折返し / 横スクロール / ページネーション
- [ ] フォーム送信後の成功/エラーメッセージ（Streamlit `last_*_success` 群を Toast に統一）
- [ ] 空状態の親切な表示
- [ ] 取消ボタン（UNDO_MINUTES 以内のエントリのみ）
- [ ] CSV/PDF/Excel ダウンロードボタン

---

## 7. テスト棚卸（既存 tests/ から移植）

- [ ] test_alerts.py — 不足/期限アラート
- [ ] test_actual_flow.py / test_complete_flow.py — ログイン→出庫→承認の統合
- [ ] test_ai_assistant.py / test_ai_module.py — AI機能
- [ ] test_demo.py — デモモード
- [ ] test_department_filter.py — 部署フィルタ
- [ ] test_final_check.py — 全体回帰
- [ ] test_order_output.py / test_payload_*.py — 発注書 payload
- [ ] その他 unit_*.py — 設定/ユーティリティ/ルーティング

---

## 8. 移植完了判定

すべての `[ ]` が `[x]` になり、かつ：

1. ステージング Postgres と本番 Postgres でデータ件数完全一致
2. pytest + FastAPI TestClient が green
3. Playwright で主要動線 E2E green
4. gitleaks / pip-audit / npm audit が critical 0
5. 主要10ページのスクショ比較レビュー完了

→ Streamlit 版を read-only 化 → 2 週間後に停止 → `legacy/` をアーカイブ
