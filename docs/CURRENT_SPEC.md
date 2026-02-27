# 在庫管理アプリ仕様書（現行実装準拠）

> 最終更新: 2026-02-27  
> 本書は実装コード (`app.py`, `db.py`, `utils/`, `ai.py`, `purchase_order_payload.py`, `purchase_order_renderers.py`, `csv_import_helper.py`) の解析に基づき、**実装済み機能のみ**を記載しています。

---

## 目次

1. [システム概要](#1-システム概要)
2. [技術構成](#2-技術構成)
3. [認証・権限モデル](#3-認証権限モデル)
4. [画面構成・ナビゲーション](#4-画面構成ナビゲーション)
5. [データ構造（テーブル定義）](#5-データ構造テーブル定義)
6. [入出庫ロジック](#6-入出庫ロジック)
7. [発注フロー](#7-発注フロー)
8. [廃棄フロー](#8-廃棄フロー)
9. [状態管理（session_state）](#9-状態管理session_state)
10. [バリデーション](#10-バリデーション)
11. [CSV入出力](#11-csv入出力)
12. [AI機能](#12-ai機能)
13. [ログ機能](#13-ログ機能)
14. [既知仕様・制約・注意点](#14-既知仕様制約注意点)

---

## 1. システム概要

SQLite + Streamlit で構築された在庫管理 Web アプリケーション。  
物品マスター管理・入出庫・在庫調整・発注申請/承認・廃棄申請/承認・アラート・集計・AI アシスタントの機能を備える。

ロールベースアクセス制御（ADMIN / USER / GUEST）により、操作範囲を制限する。

---

## 2. 技術構成

| 項目 | 値 |
|---|---|
| フレームワーク | Streamlit（`layout="wide"`） |
| データベース | SQLite 3（`inventory.db`） |
| 言語 | Python 3 |
| パスワードハッシュ | SHA-256 + salt（レガシー）/ bcrypt（両対応） |
| AI | OpenAI API（`gpt-4o-mini`、環境変数 `AI_ENABLED` で切替） |
| PDF 生成 | fpdf2（NotoSansJP フォント必須） |
| Excel 生成 | openpyxl |
| タイムゾーン | JST（`Asia/Tokyo`）。DB 保存は UTC 文字列、表示時 JST 変換 |
| 日時フォーマット | `YYYY-MM-DD HH:MM:SS` |
| 仮想環境 | `env/`（venv） |

### 環境変数（`.env`）

| 変数名 | デフォルト | 説明 |
|---|---|---|
| `DB_PATH` | `./inventory.db`（起動ディレクトリ基準で絶対パスに変換） | DB ファイルパス |
| `AI_ENABLED` | `false` | AI 機能の有効/無効 |
| `OPENAI_API_KEY` | なし | OpenAI API キー |
| `OPENAI_MODEL` | `gpt-4o-mini` | 使用 AI モデル |
| `LOG_LEVEL` | `INFO` | ログレベル |

---

## 3. 認証・権限モデル

### 3.1 ロール定義

| ロール | レベル | 表示名 |
|---|---|---|
| `GUEST` | 1 | ゲスト |
| `USER` | 2 | 一般ユーザー |
| `ADMIN` | 3 | 管理者 |

### 3.2 ロール別操作権限

| 機能 | ADMIN | USER | GUEST |
|---|---|---|---|
| ダッシュボード | ✅ 全社 | ✅ 全社 | ✅ 自部署+全社共通のみ |
| 在庫一覧 | ✅ 全件 | ✅ 全件 | ✅ 自部署タグ+全社共通 |
| 出庫 | ✅ 即時反映 | ✅ 即時反映 | ✅ 仮入力（PENDING→承認待ち） |
| 入庫 | ✅ | ✅ | ❌ |
| 在庫調整 | ✅ | ❌ | ❌ |
| 承認管理（ゲスト申請） | ✅ 全部署 | ✅ 自部署のみ | ❌ |
| 発注申請 | ✅ 部署選択可 | ✅ 自部署 | ❌ |
| 発注申請管理 | ✅ | ❌ | ❌ |
| 廃棄申請 | ✅ | ✅ | ❌ |
| 廃棄承認 | ✅ | ❌ | ❌ |
| 履歴表示 | ✅ 全件 | ✅ 自部署 | ✅ 自分のみ |
| 集計 | ✅ | ✅ | ❌ |
| アラート | ✅ 全社 | ✅ 自部署 | ✅ 自部署（期限アラート非表示） |
| AI アシスタント | ✅ | ✅ | ✅ |
| ユーザー管理 | ✅ | ❌ | ❌ |
| 物品マスター管理 | ✅ | ❌ | ❌ |
| 業者管理 | ✅ | ❌ | ❌ |
| 部署管理 | ✅ | ❌ | ❌ |
| メンテナンス | ✅ | ❌ | ❌ |
| デモモード | ✅ | ❌ | ❌ |

### 3.3 認証フロー

- ログイン: `username` + `password` → `authenticate_user()` → `session_state` にユーザー dict 保存
- パスワード検証: bcrypt 形式（`$2a$`/`$2b$` 開頭）と SHA-256+salt 形式の両方に対応
- デフォルト管理者: `admin` / `admin123`
- ログアウト: `session_state.logged_in = False`, `current_user = {}`

### 3.4 権限チェック関数群（`utils/auth.py`）

| 関数 | 用途 |
|---|---|
| `require_login()` | ログイン必須チェック |
| `require_role(role)` | 特定ロール完全一致 |
| `require_min_role(role)` | 指定ロール以上 |
| `require_not_guest()` | GUEST 排除（`require_min_role("USER")`） |
| `can_edit()` | USER 以上 |
| `can_outbound()` | 全ロール可 |
| `can_inbound()` | USER 以上 |
| `can_undo()` | 全ロール可 |
| `can_adjust()` | ADMIN のみ |
| `can_approve()` | USER 以上 |
| `can_manage_users()` | ADMIN のみ |
| `can_manage_masters()` | ADMIN のみ |

---

## 4. 画面構成・ナビゲーション

### 4.1 ナビゲーション方式

- サイドバーに `st.radio` でメニュー一覧を表示
- メニューID ベースの遷移（`set_menu(menu_id)` でページ遷移）
- `st.session_state.menu_id` / `pending_menu_id` で管理
- 旧日本語ラベルからの自動移行ロジックあり（`_migrate_legacy_menu_to_id()`）
- 表示サイズ切替（小 / 中 / 大）をサイドバーで提供

### 4.2 ロール別メニュー構成

#### GUEST

| ID | ラベル |
|---|---|
| `outbound` | ➖ 出庫（申請） |

#### USER

| ID | ラベル |
|---|---|
| `inventory` | 📦 在庫一覧 |
| `alert` | 🚨 アラート |
| `purchase_request` | 📝 発注申請 |
| `disposal_request` | 🗑️ 廃棄申請 |
| `inbound` | ➕ 入庫 |
| `outbound` | ➖ 出庫 |
| `history` | 📋 履歴 |
| `stats` | 📊 集計 |
| `approval` | ✅ 承認管理（PENDING 件数バッジ付き） |

#### ADMIN（USER の全メニュー + 以下）

| ID | ラベル |
|---|---|
| `ai` | 🤖 AI アシスタント（`AI_ENABLED=true` 時のみ） |
| `disposal_approval` | ✅ 廃棄承認（PENDING 件数バッジ付き） |
| `purchase_admin` | ✅ 発注申請管理（PENDING 件数バッジ付き） |
| `adjust` | 🔧 在庫調整 |
| `item_master` | 📦 物品マスター管理 |
| `vendor` | 🏢 業者管理 |
| `users` | 👥 ユーザー管理 |
| `departments` | 🏢 部署管理 |
| `maintenance` | 🛠️ メンテナンス |
| `demo` | 🎭 デモモード |

### 4.3 各画面の詳細

#### 🔐 ログイン画面

- 中央寄せレイアウト（max-width: 720px）
- フォーム: ユーザーID、パスワード
- 初期管理者情報を caption で表示

#### 🏠 ダッシュボード

- KPI カード 4 列:
  - 📤 今月の出庫数量（`get_monthly_outbound_total()`）
  - ⚠️ 在庫不足件数（`get_stock_alert_count()`）— 在庫数 ≤ 発注点
  - 🔴 期限切れ件数（`get_expired_count()`）
  - 🗑️ 廃棄待ち件数（`get_disposal_count("PENDING")`）— ADMIN/USER のみ表示
- GUEST は自部署フィルタ適用

#### 📦 在庫一覧（`inventory`）

- KPI カード 5 列（ダッシュボード KPI + 📦 発注候補件数）
- 検索（物品名/品目コード/業者名/業者品番の LIKE 検索）
- フィルタ: カテゴリ、資産区分（すべて/消耗品/資産）
- GUEST: 自部署タグ + 全社共通のみ表示
- ページネーション（LIMIT/OFFSET）
- CSV 出力ボタン（UTF-8 BOM）
- データテーブル表示

#### ➖ 出庫（`outbound`）

- **ミニダッシュボード**: 今月出庫量 TOP10 一覧
- **タブ切替**: 「単品出庫」「クイック出庫」
- **単品出庫フォーム**:
  - 物品選択（在庫 > 0、消耗品デフォルト表示）
  - 選択物品の月別出庫推移グラフ（折れ線グラフ）
  - 数量入力
  - GUEST: 出庫者名手入力 + 仮入力（PENDING）として処理
  - ADMIN/USER: 出庫者名自動設定 + 即時反映
  - 成功カード表示 + 在庫不足時に発注申請へのクイックリンク
  - 連打防止（`outbound_button_disabled`）
- **直近履歴と取消**:
  - 直近の確定済み履歴を表示
  - 10 分以内の履歴は取消可能（`can_undo_history()` — デフォルト 10 分制限）
  - GUEST: 取消申請（PENDING）として処理
- **クイック出庫**:
  - `st.data_editor` による一括出庫
  - チェックボックス + 数量列で複数物品を一度に出庫

#### ➕ 入庫（`inbound`）

- **タブ切替**: 「通常入庫」「発注品入庫」
- **通常入庫フォーム**:
  - 物品選択、数量入力、入庫者名（自動設定）、部署（自動設定）、備考
  - 成功カード表示
  - 連打防止
- **直近入庫履歴と取消**（出庫と同等ロジック）
- **発注品入庫タブ**:
  - ORDERED ステータスの発注申請一覧を表示
  - 各カードに「入庫」ボタン → 数量入力 → `receive_purchase_order()` 実行
  - 入庫完了で purchase_requests ステータスを RECEIVED に更新

#### 📋 履歴（`history`）

- 確定履歴タブ + 承認待ちタブ
- フィルタ: 期間（7日/30日/90日/全期間）、種別（IN/OUT/ADJUST/DISPOSE/ORDER/UNDO_*）
- 検索（物品名/操作者名）
- CSV 出力（UTF-8 BOM）
- GUEST: 自分の履歴のみ、USER: 自部署、ADMIN: 全件

#### 🔧 在庫調整（`adjust`）— ADMIN 専用

- 物品選択 → 現在の在庫数表示 → 調整後数量入力 → 理由入力（必須）
- 差分が 0 の場合はエラー
- 履歴に `ADJUST` として記録（差分を quantity に格納）

#### ✅ 承認管理（`approval`）

- PENDING 状態のゲスト申請一覧
- USER: 自部署の申請のみ表示
- ADMIN: 全部署表示
- 承認操作: 在庫更新 + CONFIRMED 履歴記録
- 却下操作: ステータスを REJECTED に更新
- 二重実行防止フラグ

#### 👥 ユーザー管理（`users`）— ADMIN 専用

- ユーザー一覧（検索、ロールフィルタ、部署フィルタ、ページネーション）
- 新規ユーザー作成フォーム（ID/PW/確認PW/表示名/部署/権限）
- ユーザー詳細・編集（表示名/部署/パスワード変更(任意)/権限/有効状態）

#### 📦 物品マスター管理（`item_master`）— ADMIN 専用

- **一覧タブ**: 物品検索・フィルタ・ページネーション、詳細/編集
- **新規登録タブ**: 品目名(必須)、カテゴリ(必須)、品目コード(任意)、業者名、業者品番、単価、使用頻度タグ、使用期限、管理部署、利用部署タグ、発注点、点検間隔（月）
- **カテゴリ管理タブ**: 一覧表示 + 新規カテゴリ追加
- **CSV 取り込みタブ**: 6 ステップ（サンプル DL→アップロード→プレビュー→設定→検証→実行）
- 品目コード重複チェック、業者名+業者品番ユニーク制約

#### 🏢 業者管理（`vendor`）— ADMIN 専用

- 業者一覧（検索、ページネーション）
- 新規登録フォーム（業者コード/業者名/所在地/電話/メール）
- 業者詳細・編集
- 有効/無効切替

#### 🏢 部署管理（`departments`）— ADMIN 専用

- 部署一覧（検索、ページネーション）
- 新規部署追加
- 部署名変更、有効/無効切替

#### 🚨 アラート（`alert`）

- **在庫不足アラート**: `quantity ≤ reorder_point` の物品一覧
  - GUEST/USER: 自部署フィルタ
  - 部署タグ + 全社共通を対象
  - 発注申請へのクイックリンク / 廃棄申請へのクイックリンク
- **期限アラート**: 期限切れ + 30 日以内の物品
  - `YYYY-MM` / `YYYY-MM-DD` 両形式対応

#### 🗑️ 廃棄申請（`disposal_request`）

- 薬品選択、廃棄数量、廃棄理由（5 文字以上必須）
- 在庫超過チェック
- 重複申請防止（ハッシュチェック）
- アラートページからのプリセット対応（`prefill_disposal_*`）

#### ✅ 廃棄承認（`disposal_approval`）— ADMIN 専用

- PENDING 一覧 → 承認/却下
- 承認時: 在庫減算 + DISPOSE 履歴記録
- 却下時: 却下理由入力
- 処理済み CSV 出力
- 冪等性確保（PENDING 時のみ更新、rowcount=0 で処理済み判定）

#### 📊 集計（`stats`）

- **月別出庫サマリ**: 月別の出庫数量集計 + CSV 出力
- **部署別×月別出庫**: クロス集計テーブル + CSV 出力
- **カテゴリ別廃棄集計**: 承認済み廃棄のカテゴリ別集計 + CSV 出力

#### 📝 発注申請（`purchase_request`）

- 物品選択、希望数量、希望納期（任意、YYYY-MM-DD）、優先度（normal/high/urgent）、備考
- 二重送信防止（3 秒 + ハッシュチェック）
- アラートページ/出庫ページからのプリセット対応
- USER: 自部署固定、ADMIN: 部署選択可

#### ✅ 発注申請管理（`purchase_admin`）— ADMIN 専用

- タブ構成: PENDING / APPROVED / ON_HOLD / REJECTED / ORDERED
- 各タブに件数バッジ + CSV 出力
- **承認フロー**: PENDING → APPROVED / ON_HOLD / REJECTED
  - 保留・却下時はコメント必須
  - PENDING に戻す操作可（ORDERED 除く）
  - 論理削除対応（`deleted_at`）
- **発注書作成画面**:
  - 承認済み申請を選択 → payload 生成（vendor 別グループ化）
  - メール文面生成（AI/テンプレート切替）
  - PDF 出力（NotoSansJP フォント使用、業者別）
  - Excel 出力（業者別シート）
  - 発注確定 → ORDERED ステータス + ORDER 履歴記録

#### 🤖 AI アシスタント（`ai`）

- チャット形式（`ai_chat_history`）
- コンテキスト: 在庫情報/アラート/月別集計を自動取得
- 操作系キーワードの安全チェック（`check_safety_request()`）
- OpenAI API 呼び出し（`call_openai_chat()`）
- `AI_ENABLED=true` 時のみメニュー表示

#### 🛠️ メンテナンス（`maintenance`）— ADMIN 専用

- `change_type` 分布の確認
- 履歴の CSV バックアップ（`backup_inventory_history_to_csv()`）
- `change_type` 整理（ORDER 削除、INBOUND→IN 変換）

#### 🎭 デモモード（`demo`）— ADMIN 専用

- デモデータ一括投入（UPSERT 方式）
  - 部署 5 件 / ユーザー 7 名 / 業者 5 社 / カテゴリ 6 種 / 物品 24 件 / 在庫 / 履歴
- データリセット（全テーブル DELETE）
- 現在データ件数表示

---

## 5. データ構造（テーブル定義）

### 5.1 items（物品マスター）

| カラム | 型 | 説明 |
|---|---|---|
| `id` | INTEGER PK | 物品 ID |
| `item_name` | TEXT NOT NULL | 品目名 |
| `item_code` | TEXT | 品目コード |
| `vendor_name` | TEXT | 業者名 |
| `vendor_item_code` | TEXT | 業者品番 |
| `category` | TEXT NOT NULL | カテゴリ |
| `department_tags` | TEXT | 利用部署タグ（カンマ区切り） |
| `unit_price` | REAL DEFAULT 0 | 単価 |
| `is_asset` | INTEGER DEFAULT 0 | 0: 消耗品, 1: 資産 |
| `frequency_tag` | TEXT | 使用頻度タグ |
| `expiry_date` | TEXT | 使用期限（YYYY-MM-DD） |
| `is_active` | INTEGER DEFAULT 1 | 有効フラグ（論理削除用） |
| `is_common` | INTEGER DEFAULT 0 | 全社共通フラグ |
| `owner_department_id` | INTEGER | 管理部署 ID（FK→departments） |
| `location_text` | TEXT | 保管場所テキスト |
| `last_inspection_date` | TEXT | 最終点検日 |
| `next_inspection_date` | TEXT | 次回点検日 |
| `interval_months` | INTEGER | 点検間隔（月） |
| `reorder_point` | INTEGER | 発注点 |
| `created_at` | TEXT | 作成日時 |
| `updated_at` | TEXT | 更新日時 |

**ユニーク制約**: `(vendor_name, vendor_item_code)`

**インデックス**: `item_name`, `item_code`, `category`, `(vendor_name, vendor_item_code)`

### 5.2 inventory（在庫）

| カラム | 型 | 説明 |
|---|---|---|
| `id` | INTEGER PK | ID |
| `item_id` | INTEGER NOT NULL FK | 物品 ID |
| `quantity` | INTEGER DEFAULT 0 | 現在在庫数 |
| `threshold` | INTEGER DEFAULT 10 | 閾値（アラート用） |
| `location` | TEXT | 保管場所 |
| `updated_at` | TEXT | 更新日時 |

**ユニーク制約**: `item_id`

### 5.3 inventory_history（在庫履歴）

| カラム | 型 | 説明 |
|---|---|---|
| `id` | INTEGER PK | 履歴 ID |
| `item_id` | INTEGER NOT NULL FK | 物品 ID |
| `change_type` | TEXT NOT NULL | `IN` / `OUT` / `ADJUST` / `DISPOSE` / `ORDER` / `UNDO_IN` / `UNDO_OUT` |
| `quantity` | INTEGER NOT NULL | 変動数量 |
| `user_name` | TEXT NOT NULL | 操作者名 |
| `department` | TEXT | 部署名 |
| `status` | TEXT DEFAULT `CONFIRMED` | `PENDING` / `CONFIRMED` / `REJECTED` |
| `note` | TEXT | 備考 |
| `vendor_name` | TEXT | 発注先業者名（ORDER 時） |
| `unit_price` | REAL | 単価（ORDER 時） |
| `total_price` | REAL | 合計金額（ORDER 時） |
| `created_by` | INTEGER | 作成者ユーザー ID |
| `created_at` | TEXT | 作成日時 |

**インデックス**: `(item_id, created_at DESC)`, `status`

### 5.4 users（ユーザー）

| カラム | 型 | 説明 |
|---|---|---|
| `id` | INTEGER PK | ユーザー ID |
| `username` | TEXT UNIQUE NOT NULL | ログイン ID |
| `password_hash` | TEXT NOT NULL | パスワードハッシュ |
| `display_name` | TEXT NOT NULL | 表示名 |
| `department` | TEXT | 部署名（テキスト） |
| `department_id` | INTEGER FK | 部署 ID |
| `user_role` | TEXT NOT NULL | ロール（ADMIN/USER/GUEST） |
| `is_active` | INTEGER DEFAULT 1 | 有効フラグ |
| `created_at` | TEXT | 作成日時 |
| `updated_at` | TEXT | 更新日時 |

**インデックス**: `username`, `user_role`, `department`, `department_id`

### 5.5 departments（部署マスター）

| カラム | 型 | 説明 |
|---|---|---|
| `id` | INTEGER PK | 部署 ID |
| `name` | TEXT UNIQUE NOT NULL | 部署名 |
| `is_active` | INTEGER DEFAULT 1 | 有効フラグ |
| `created_at` | TEXT | 作成日時 |

**デフォルト値**: 総務部 / 営業部 / 経理部 / 看護係 / 薬剤部 / 未設定

### 5.6 categories（カテゴリマスター）

| カラム | 型 | 説明 |
|---|---|---|
| `id` | INTEGER PK | ID |
| `name` | TEXT UNIQUE NOT NULL | カテゴリ名 |
| `is_active` | INTEGER DEFAULT 1 | 有効フラグ |
| `created_at` | TEXT | 作成日時 |

**デフォルト値**: 事務用品 / 薬品 / 医療機器 / 消耗品 / その他

### 5.7 vendors（業者マスター）

| カラム | 型 | 説明 |
|---|---|---|
| `id` | INTEGER PK | 業者 ID |
| `vendor_code` | TEXT UNIQUE NOT NULL | 業者コード |
| `vendor_name` | TEXT UNIQUE NOT NULL | 業者名 |
| `address` | TEXT | 所在地 |
| `phone` | TEXT | 電話番号 |
| `email` | TEXT | メールアドレス |
| `is_active` | INTEGER DEFAULT 1 | 有効フラグ |
| `created_at` | TEXT | 作成日時 |
| `updated_at` | TEXT | 更新日時 |

**デフォルト値**: ○○商事(V001) / △△物産(V002) / 未登録業者(V003)

### 5.8 pending_transactions（ゲスト申請）

| カラム | 型 | 説明 |
|---|---|---|
| `id` | INTEGER PK | 申請 ID |
| `change_type` | TEXT NOT NULL | 変更種別（OUT / UNDO_OUT 等） |
| `item_id` | INTEGER NOT NULL FK | 物品 ID |
| `quantity` | INTEGER NOT NULL | 数量 |
| `actor_name` | TEXT NOT NULL | 操作者名 |
| `note` | TEXT | 備考 |
| `guest_user_id` | INTEGER NOT NULL FK | ゲストユーザー ID |
| `department_id` | INTEGER NOT NULL FK | 部署 ID |
| `status` | TEXT DEFAULT `PENDING` | `PENDING` / `APPROVED` / `REJECTED` / `CANCELLED` |
| `approved_by` | INTEGER FK | 承認者ユーザー ID |
| `approved_at` | TEXT | 承認日時 |
| `reject_reason` | TEXT | 却下理由 |
| `created_at` | TEXT | 申請日時 |

**インデックス**: `status`, `department_id`

### 5.9 disposal_requests（廃棄申請）

| カラム | 型 | 説明 |
|---|---|---|
| `id` | INTEGER PK | 申請 ID |
| `item_id` | INTEGER NOT NULL FK | 物品 ID |
| `quantity` | INTEGER NOT NULL | 廃棄数量 |
| `reason` | TEXT NOT NULL | 廃棄理由 |
| `requester_id` | INTEGER NOT NULL FK | 申請者ユーザー ID |
| `status` | TEXT DEFAULT `PENDING` | `PENDING` / `APPROVED` / `REJECTED` |
| `approved_by` | INTEGER FK | 承認者 ID |
| `approved_at` | TEXT | 承認日時 |
| `reject_reason` | TEXT | 却下理由 |
| `created_at` | TEXT | 申請日時 |

**インデックス**: `status`, `requester_id`

### 5.10 purchase_requests（発注申請）

| カラム | 型 | 説明 |
|---|---|---|
| `id` | INTEGER PK | 申請 ID |
| `item_id` | INTEGER NOT NULL FK | 物品 ID |
| `requested_qty` | INTEGER NOT NULL | 希望数量 |
| `priority` | TEXT DEFAULT `normal` | `normal` / `high` / `urgent` |
| `due_date` | TEXT | 希望納期（YYYY-MM-DD） |
| `note` | TEXT | 備考 |
| `requested_by_user_id` | INTEGER NOT NULL FK | 申請者 ID |
| `requested_by_department` | TEXT | 申請部署 |
| `status` | TEXT DEFAULT `PENDING` | `PENDING` / `APPROVED` / `ON_HOLD` / `REJECTED` / `ORDERED` / `RECEIVED` |
| `admin_comment` | TEXT | 管理者コメント |
| `approved_by` | INTEGER FK | 承認者 ID |
| `approved_at` | TEXT | 承認日時 |
| `deleted_at` | TEXT | 論理削除日時 |
| `deleted_by` | INTEGER | 削除者 ID |
| `created_at` | TEXT | 申請日時 |
| `updated_at` | TEXT | 更新日時 |

**インデックス**: `status`, `requested_by_user_id`, `item_id`

### 5.11 purchase_candidates（発注候補）

| カラム | 型 | 説明 |
|---|---|---|
| `id` | INTEGER PK | ID |
| `item_id` | INTEGER UNIQUE NOT NULL FK | 物品 ID |
| `auto_reason` | TEXT DEFAULT `reorder_point` | 自動候補理由 |
| `selected_for_order` | INTEGER DEFAULT 0 | 発注対象選択フラグ |
| `deferred` | INTEGER DEFAULT 0 | 保留フラグ |
| `priority` | TEXT DEFAULT `normal` | 優先度 |
| `recommended_qty` | INTEGER DEFAULT 0 | 推奨発注数量 |
| `note` | TEXT | メモ |
| `status` | TEXT DEFAULT `OPEN` | `OPEN` / `ORDERED` |
| `updated_by_user_id` | INTEGER FK | 更新者 ID |
| `updated_at` | TEXT | 更新日時 |
| `created_at` | TEXT | 作成日時 |

**インデックス**: `status`, `selected_for_order`, `item_id`

---

## 6. 入出庫ロジック

### 6.1 出庫処理（`process_outbound()`）

```
1. 物品ID + 現在在庫数を取得（items JOIN inventory）
2. 在庫不足チェック（current_quantity < quantity → エラー）
3. inventory.quantity を減算
4. inventory_history に OUT / CONFIRMED を INSERT
5. 閾値割れ（new_quantity ≤ threshold）の場合は警告メッセージ付与
```

**戻り値**: `{ success, message, remaining_quantity }`

### 6.2 ゲスト仮出庫（`process_outbound_pending()`）

```
1. 物品情報+在庫取得
2. 在庫チェック（在庫不足なら拒否）
3. 在庫は変更しない
4. inventory_history に OUT / PENDING / note="[仮入力]..." を INSERT
```

### 6.3 入庫処理（`process_inbound()`）

```
1. 物品情報を取得
2. inventory.quantity を加算
3. inventory_history に IN / CONFIRMED を INSERT
```

**戻り値**: `{ success, message, new_quantity }`

### 6.4 在庫調整（`process_adjust()`）— ADMIN 専用

```
1. 物品の現在在庫を取得
2. 差分 = new_quantity - current_quantity（差分0はエラー）
3. inventory.quantity を new_quantity に SET
4. inventory_history に ADJUST / CONFIRMED / quantity=差分 を INSERT
5. 理由を note に記録
```

**戻り値**: `{ success, message, old_quantity, new_quantity }`

### 6.5 取消処理（`process_undo()`）

```
1. 対象履歴レコードを取得
2. can_undo_history() で取消可能チェック（10分以内 + 未取消）
3. 逆取引を実行（OUT→在庫加算, IN→在庫減算）
4. マイナス在庫チェック（IN取消時）
5. inventory_history に UNDO_OUT/UNDO_IN / CONFIRMED を INSERT
6. 発注品入庫(IN)のUNDO時は purchase_requests のステータスを ORDERED に戻す
```

### 6.6 ゲスト取消申請（`process_undo_pending()`）

- 10 分制限あり
- 在庫は変更しない
- PENDING として履歴記録

### 6.7 数量バリデーション定数

| 定数 | 値 | 説明 |
|---|---|---|
| `outbound_max` | 1,000 | 1 回の出庫数量上限 |
| `inbound_max` | 10,000 | 1 回の入庫数量上限 |
| `warning_threshold` | 100 | 数量警告閾値 |

---

## 7. 発注フロー

### 7.1 ステータス遷移

```
PENDING → APPROVED → ORDERED → RECEIVED
       ↘ ON_HOLD ↗
       ↘ REJECTED ↗
```

- ORDERED 以降はステータスを戻せない
- 論理削除は ORDERED 以外で可能

### 7.2 発注申請（USER / ADMIN）

`create_purchase_request()` → PENDING 状態で登録

### 7.3 承認フロー（ADMIN）

| 操作 | 関数 | 遷移 |
|---|---|---|
| 承認 | `approve_purchase_request()` | → APPROVED |
| 保留 | `hold_purchase_request()` | → ON_HOLD（コメント必須） |
| 却下 | `reject_purchase_request()` | → REJECTED（コメント必須） |
| PENDING 戻し | `reset_purchase_request_to_pending()` | → PENDING |
| 論理削除 | `delete_purchase_request()` | `deleted_at` 設定（ORDERED 不可） |

### 7.4 発注書作成

1. 承認済み申請を選択
2. `build_purchase_order_payloads()` で vendor 別 payload 生成
3. 出力形式選択:
   - **メール文面**: `generate_email_text()` — AI / テンプレート切替
   - **PDF**: `render_pdf()` — fpdf2、NotoSansJP フォント（`fonts/NotoSansJP-Regular.ttf` 必須）
   - **Excel**: `render_excel()` — openpyxl、業者別シート
4. 発注確定: `mark_requests_ordered()` → ORDERED + ORDER 履歴記録

### 7.5 発注書 payload 構造

```json
{
  "vendor": "業者名",
  "subject": "発注書",
  "to": "業者名 御中",
  "ordered_at": "YYYY-MM-DD",
  "requester": {
    "department": "部署名",
    "name": "発注者名"
  },
  "items": [
    {
      "item_name": "品目名",
      "item_code": "品目コード",
      "vendor_part_no": "",
      "quantity": 10,
      "unit_price": 100.0,
      "subtotal": 1000.0,
      "notes": "備考"
    }
  ],
  "total": 1000.0,
  "has_unpriced_items": false
}
```

- `unit_price` が NULL/0 の場合: `subtotal = null`, `total = null`, `has_unpriced_items = true`

### 7.6 発注品入庫

`receive_purchase_order()`:
1. purchase_requests ステータスを RECEIVED に更新
2. 在庫加算（inventory.quantity += received_qty）
3. inventory_history に IN / CONFIRMED を INSERT
4. history_id を返却（取消用）

### 7.7 発注候補自動算出

`get_reorder_candidates()`:
- 対象: 消耗品（is_asset=0）、在庫 ≤ 発注点、直近 30 日出庫 > 0
- 推奨数量 = `(30日出庫量 × 2) - 現在庫`
- `sync_purchase_candidates()` で purchase_candidates テーブルに UPSERT
- 在庫ゼロ → `urgent` + 自動選択

---

## 8. 廃棄フロー

### 8.1 ステータス遷移

```
PENDING → APPROVED（在庫減算+DISPOSE履歴）
       ↘ REJECTED
```

### 8.2 処理詳細

- `create_disposal_request()`: 廃棄申請作成（在庫超過チェック）
- `approve_disposal_request()`: 承認 → 在庫減算 + DISPOSE 履歴記録（冪等性確保）
- `reject_disposal_request()`: 却下（理由入力）

---

## 9. 状態管理（session_state）

### 9.1 認証・初期化

| キー | 型 | 説明 |
|---|---|---|
| `logged_in` | bool | ログイン状態 |
| `current_user` | dict | 現在ユーザー情報（id, username, display_name, department, department_id, user_role） |
| `initialized` | bool | アプリ初期化済み |
| `db_check_done` | bool | DB 複数存在チェック済み |
| `display_size` | str | 表示サイズ（小 / 中 / 大、デフォルト: 中） |
| `refresh_token` | float | キャッシュバイパス用タイムスタンプ |

### 9.2 メニュー・ナビゲーション

| キー | 型 | 説明 |
|---|---|---|
| `menu_id` | str | 現在のメニュー ID |
| `pending_menu_id` | str | 遷移先メニュー ID |
| `sb_menu` | str | サイドバー radio の Streamlit 管理キー |
| `menu` | str | 旧日本語ラベル（互換性、自動移行対象） |
| `current_page` | int | ページネーション現在ページ（遷移時リセット） |

### 9.3 出庫関連

| キー | 説明 |
|---|---|
| `last_outbound_success` | 出庫成功データ dict |
| `outbound_success_display` | 成功カード表示用 |
| `outbound_form_success` | フォーム直下の短い通知 |
| `outbound_button_disabled` | 連打防止フラグ |
| `last_undo_outbound_success` | 取消成功メッセージ |
| `last_undo_outbound_error` | 取消エラーメッセージ |
| `quick_outbound_success` | クイック出庫成功件数 |
| `confirm_undo_out_{id}` | 取消確認ダイアログ状態 |
| `confirm_cancel_pending_{id}` | PENDING 取り下げ確認 |
| `cancel_success_message` | 取り下げ成功メッセージ |
| `cancel_error_message` | 取り下げエラーメッセージ |

### 9.4 入庫関連

| キー | 説明 |
|---|---|
| `last_inbound_success` | 入庫成功データ dict |
| `inbound_success_display` | 成功カード表示用 |
| `inbound_form_success` | フォーム直下の短い通知 |
| `inbound_button_disabled` | 連打防止フラグ |
| `last_undo_inbound_success` | 取消成功メッセージ |
| `last_undo_inbound_error` | 取消エラーメッセージ |
| `confirm_undo_in_{id}` | 取消確認ダイアログ状態 |
| `receive_success_message` | 発注品入庫成功メッセージ |

### 9.5 在庫調整

| キー | 説明 |
|---|---|
| `last_adjust_success` | 調整成功データ dict |

### 9.6 承認管理

| キー | 説明 |
|---|---|
| `approval_success_message` | 承認成功メッセージ |
| `approval_error_message` | 承認エラーメッセージ |
| `processing_approval_{id}` | 二重実行防止 |
| `processing_reject_{id}` | 却下二重実行防止 |

### 9.7 ユーザー管理

| キー | 説明 |
|---|---|
| `user_page` | 一覧ページ番号 |
| `user_prev_filters` | フィルタ変更検知 |
| `user_selected_id` | 選択ユーザー ID |

### 9.8 物品マスター管理

| キー | 説明 |
|---|---|
| `item_page` | 一覧ページ番号 |
| `viewing_item_id` | 詳細表示中の物品 ID |
| `editing_item_id` | 編集中の物品 ID |
| `form_reset_counter` | フォームリセットカウンター |
| `item_register_success` | 登録成功メッセージ |

### 9.9 業者管理

| キー | 説明 |
|---|---|
| `vendor_page` | 一覧ページ番号 |
| `vendor_prev_filters` | フィルタ変更検知 |
| `vendor_selected_id` | 選択業者 ID |
| `vendor_register_success` | 登録成功メッセージ |
| `vendor_form_reset_counter` | フォームリセットカウンター |

### 9.10 部署管理

| キー | 説明 |
|---|---|
| `dept_page` | 一覧ページ番号 |
| `dept_prev_filters` | フィルタ変更検知 |
| `dept_selected_id` | 選択部署 ID |

### 9.11 廃棄申請

| キー | 説明 |
|---|---|
| `prefill_disposal_item_id` | アラートからのプリセット物品 ID |
| `prefill_disposal_quantity` | プリセット数量 |
| `prefill_disposal_reason` | プリセット理由 |
| `last_disposal_success` | 申請成功フラグ |
| `last_disposal_request_hash` | 重複申請チェック用ハッシュ |
| `show_reject_{id}` | 却下フォーム表示フラグ |

### 9.12 発注申請

| キー | 説明 |
|---|---|
| `prefill_purchase_item_id` | アラートからのプリセット物品 ID |
| `prefill_purchase_quantity` | プリセット数量 |
| `prefill_purchase_reason` | プリセット理由 |
| `pr_prefill_item_id` | 出庫ページからのプリセット物品 ID |
| `pr_prefill_qty` | 出庫ページからのプリセット数量 |
| `last_purchase_request_success` | 申請成功データ |
| `purchase_request_success_display` | 成功カード表示用 |
| `last_pr_submission` | 二重送信チェック `(time, hash)` |

### 9.13 発注申請管理（ADMIN）

| キー | 説明 |
|---|---|
| `pr_dept_filter` | 部署フィルタ状態 |
| `selected_request_ids` | 選択申請 ID リスト |
| `show_order_creation` | 発注書作成画面表示フラグ |
| `show_hold_form` | 一括保留フォーム表示 |
| `show_reject_form` | 一括却下フォーム表示 |
| `order_creation_request_ids` | 発注書作成対象 ID |
| `order_draft_text` | 発注文案テキスト |
| `order_payloads` | 発注 payload データ |
| `po_generated` | 発注書生成済みフラグ |
| `last_output_channel` | 最後の出力形式 (email/pdf/excel) |
| `last_document_name` | 最後の出力ファイル名 |
| `order_finalized` | 発注確定済みフラグ |
| `email_output` / `pdf_output` / `excel_output` | 生成データ |

### 9.14 CSV 取り込み

| キー | 説明 |
|---|---|
| `csv_validation_done` | バリデーション完了フラグ |
| `csv_validation_results` | バリデーション結果 |
| `csv_data` | 取り込み DataFrame |
| `csv_error_count` | エラー行数 |

### 9.15 AI アシスタント

| キー | 説明 |
|---|---|
| `ai_chat_history` | チャット履歴リスト |

### 9.16 デモモード

| キー | 説明 |
|---|---|
| `demo_reset_confirm` | リセット確認フラグ |

---

## 10. バリデーション

### 10.1 共通バリデーション基盤（`utils/validation.py`）

#### 正規化処理

| 関数 | 処理内容 |
|---|---|
| `normalize_to_halfwidth()` | 全角英数字・記号 → 半角変換 |
| `normalize_number_string()` | 全角→半角 + カンマ除去 |
| `clean_string()` | None/空白統一 + トリム |
| `is_empty()` | None / "" / 空白のみ判定 |

#### 数値バリデーション

| 関数 | 制約 |
|---|---|
| `validate_integer()` | 整数変換、min/max 範囲チェック |
| `validate_positive_integer()` | 1 以上の正整数 |
| `validate_non_negative_integer()` | 0 以上の整数 |
| `validate_float()` | 小数対応、通貨記号（¥/円）自動除去 |
| `to_int_safe()` | 現場向けシンプル API（整数安全変換） |
| `to_float_safe()` | 現場向けシンプル API（小数安全変換、通貨記号自動除去） |

#### 文字列バリデーション

| 関数 | 制約 |
|---|---|
| `validate_required_string()` | 必須、最小/最大文字数、半角正規化 |
| `validate_optional_string()` | 任意、最大文字数、半角正規化 |
| `validate_alphanumeric()` | 英数字のみ（ユーザー ID 用） |
| `validate_required_text()` | 必須テキストのエイリアス |

#### 日付バリデーション

| 関数 | 処理 |
|---|---|
| `validate_date_string()` | YYYY-MM-DD 形式チェック、スラッシュ→ハイフン変換、全角ハイフン各種変換（全角ハイフン/長音/マイナス/ノンブレーキングハイフン/エヌダッシュ/エムダッシュ） |

#### 補正検出ヘルパー

| 関数 | 処理 |
|---|---|
| `has_currency_symbols()` | 通貨記号（¥/円）検出 |
| `has_fullwidth_chars()` | 全角数字/カンマ/スペース検出 |
| `needs_correction_warning()` | 補正必要性判定+警告メッセージ生成 |

#### 複合バリデーション

- `ValidationResult` クラス: `errors[]` + `values{}` を管理
- `show_validation_errors()`: Streamlit 上にエラー一覧表示
- `validate_form_and_show_errors()`: 結果チェック+表示の一括処理

### 10.2 各フォーム固有の検証

| フォーム | 検証内容 |
|---|---|
| ログイン | ユーザー ID/パスワード空チェック |
| 出庫 | 数量 ≥ 1（`to_int_safe`）、GUEST は出庫者名必須（`validate_required_text`）、在庫不足チェック |
| 入庫 | 数量 ≥ 1（`to_int_safe`） |
| 在庫調整 | 理由必須、差分 ≠ 0 |
| 物品登録 | 品目名必須、カテゴリ必須、単価（`to_float_safe`）、品目コード重複/業者品番重複チェック |
| ユーザー作成 | ID英数字（`validate_alphanumeric`）、パスワード 4 文字以上、確認一致 |
| 廃棄申請 | 理由 5 文字以上、在庫超過チェック、重複ハッシュチェック |
| 発注申請 | 数量 ≥ 1、日付形式（`validate_date_string`、任意）、二重送信（3 秒+ハッシュ） |
| 業者登録 | 業者コード・業者名必須 |
| CSV 取り込み | 行単位バリデーション（ハードエラー+ソフト警告の 2 段階） |

---

## 11. CSV 入出力

### 11.1 出力（ダウンロード）

全出力は **UTF-8 BOM** エンコーディング。

| 画面 | 内容 |
|---|---|
| 在庫一覧 | フィルタ条件反映の在庫 CSV |
| 履歴 | 期間・種別フィルタ反映の履歴 CSV |
| 廃棄承認 | 処理済み（承認+却下）廃棄一覧 CSV |
| 集計（月別） | 月別出庫サマリ CSV |
| 集計（部署×月） | 部署別×月別クロス集計 CSV |
| 集計（廃棄） | カテゴリ別廃棄集計 CSV |
| 発注申請管理 | 各ステータスタブの申請一覧 CSV |
| メンテナンス | 履歴バックアップ CSV |

### 11.2 入力（取り込み）

**物品マスター CSV 一括取り込み**（6 ステップ）:

1. **サンプル CSV ダウンロード**: テンプレートファイル（UTF-8 BOM）
2. **ファイルアップロード**: UTF-8 / BOM 対応
3. **プレビュー**: 先頭行表示
4. **設定**: 初期在庫数・閾値の指定
5. **検証**: 行単位バリデーション（ハードエラー/ソフト警告の 2 段階表示）
6. **実行**: `insert_item()` で登録

#### サンプル CSV 列

```
item_name, category_name, vendor_name, unit_price, item_code,
vendor_part_no, department_tags, reorder_point, expiry_date,
is_active, notes
```

---

## 12. AI 機能

### 12.1 AI アシスタント（チャット）

- `ai_chat_history` にチャット履歴を保持
- コンテキスト自動取得: 在庫情報 / アラート / 月別集計
- 操作系キーワード安全チェック（`check_safety_request()`）
- OpenAI API 呼び出し（`call_openai_chat()`、temperature=0.7、max_tokens=2000）

### 12.2 発注書 AI 生成

- `generate_purchase_order_text()`: 発注情報を元にビジネス文を生成
- AI 利用不可時はテンプレート生成にフォールバック（`_generate_template_order()`）
- システムプロンプトで件名/宛先/明細/合計/締め文の構成を指定

### 12.3 フォールバック

- API キー未設定 / openai 未インストール / API エラー → テンプレート生成に自動切替

---

## 13. ログ機能

### 13.1 ログ設定（`utils/logger.py`）

| 項目 | 値 |
|---|---|
| 出力先 | コンソール + ファイル（`logs/app_YYYY-MM-DD.log`） |
| コンソールレベル | INFO |
| ファイルレベル | DEBUG |
| フォーマット | `%(asctime)s - %(name)s - %(levelname)s - %(message)s` |
| タイムゾーン | JST |

### 13.2 ログ関数

| 関数 | 用途 |
|---|---|
| `log_info()` | 一般情報ログ |
| `log_warning()` | 警告ログ |
| `log_error()` | エラーログ |
| `log_debug()` | デバッグログ |
| `log_inbound()` | 入庫操作ログ |
| `log_outbound()` | 出庫操作ログ |
| `log_adjust()` | 在庫調整ログ |
| `log_approve()` | 承認ログ |
| `log_reject()` | 却下ログ |
| `log_login()` | ログインログ（成功/失敗） |

---

## 14. 既知仕様・制約・注意点

### 14.1 データベース

- SQLite シングルファイル（`inventory.db`）— 同時書き込みはロック制御
- DB 複数存在チェック機能あり（起動時にプロジェクト内を走査し警告）
- マイグレーションは `ALTER TABLE ADD COLUMN` + `try/except` で既存カラムをスキップ
- `get_db_connection()` は `@contextmanager` でトランザクション管理（成功時 commit / 例外時 rollback）

### 14.2 日時管理

- DB 保存フォーマット: `YYYY-MM-DD HH:MM:SS`（基本 UTC 想定）
- 表示時: `parse_db_ts_to_jst()` で UTC → JST 変換
- 一部処理では `datetime('now', '+09:00')` で直接 JST を DB に保存（混在あり）
- `get_jst_now_str()` は JST 文字列を直接返す

### 14.3 パスワード

- 新規作成: SHA-256 + salt 形式（`hash_password()`）
- 検証: bcrypt 形式（`$2a$`/`$2b$`）と SHA-256+salt の両方に自動対応

### 14.4 UI 表示

- `layout="wide"` 固定（フル幅）
- 表示サイズ 3 段階（小: 13px / 中: 16px / 大: 22px）CSS 変数ベース
- サイドバータイトルは固定サイズ（1.6rem）
- `st.cache_data` / `st.cache_resource` 使用 → `refresh_data()` でクリア

### 14.5 部署フィルタ

- GUEST ユーザーは `department_tags` カラムのカンマ区切り値で部署フィルタ
- `(',' || department_tags || ',') LIKE '%,部署名,%'` パターンで一致判定
- `department_tags` が NULL / 空文字の物品は全ユーザーに表示
- `全社` タグが含まれる物品は全ユーザーに表示

### 14.6 取消制限

- デフォルト 10 分以内（`can_undo_history(minutes=10)`）
- 取消済みチェック: `UNDO` を含む note パターンで判定（`is_history_undone()`）
- 発注品入庫の取消時は purchase_requests を ORDERED に戻す

### 14.7 連打防止

- `outbound_button_disabled` / `inbound_button_disabled` で出庫/入庫ボタンの二重押し防止
- 承認処理: `processing_approval_{id}` / `processing_reject_{id}` で二重実行防止
- 発注申請: 3 秒間隔 + ハッシュ一致チェック（`last_pr_submission`）
- 廃棄申請: ハッシュチェック（`last_disposal_request_hash`）

### 14.8 冪等性

- 廃棄承認/却下: `WHERE status='PENDING'` + `rowcount=0` で処理済み判定
- 発注申請承認: ORDERED/APPROVED 済みはエラー返却

### 14.9 PDF 出力

- フォント: `fonts/NotoSansJP-Regular.ttf` 必須（システムフォントへのフォールバック廃止済み）
- フォントファイル不在時は `FileNotFoundError` 送出

### 14.10 期限アラート

- `YYYY-MM` 形式: 月初日（1 日）として解釈
- `YYYY-MM-DD` 形式: そのまま使用
- 「期限切れ」: 現在日を過ぎた物品
- 「期限間近」: 30 日以内に期限を迎える物品

### 14.11 発注候補推奨数量

- 推奨数量 = `(直近30日出庫量 × 2) − 現在庫`
- 対象: 消耗品のみ（`is_asset=0`）、在庫 ≤ 発注点、30 日出庫 > 0

### 14.12 CSV エンコーディング

- 出力: UTF-8 BOM（Excel での文字化け防止）
- 入力: UTF-8 / BOM 対応
