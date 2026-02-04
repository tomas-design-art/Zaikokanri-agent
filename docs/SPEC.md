在庫管理アプリ 仕様書（AI機能ON/OFF対応版・最新版）

1. 目的

社内の物品（事務用品・薬品など）を一元管理し、
各部署の使用実績・在庫状況・発注判断を効率化する。

生成AIは
👉「読む・提案・書類作成」のみ
👉 在庫操作・発注確定は必ず人が行う

AI機能は 無効化可能（ON/OFF切替） とする。

2. 想定環境

Python + Streamlit

SQLite（ローカルDB）

将来：社内サーバーにDB移設可能

同時利用：1〜5人程度

3. ユーザー区分

ログイン機能を導入したい。ログイン者は名前と部署が、在庫処理等に反映される。

管理者

部署マスター管理

物品マスター管理

ゲストID管理

承認処理

発注・廃棄判断

一般ユーザー（部署担当）

出庫入力（−）

入庫入力（＋）

在庫確認

ゲストユーザー（現場用）

出庫仮入力のみ

氏名入力必須

承認待ち状態で保存

4. 物品の考え方
共通物品

事務用品など

全社一元管理

部署限定物品

薬品など

タグ（部署/係）で表示制御

ユニーク管理

原則：品目コード

無い場合：
業者名＋業者品番でユニーク化

5. 物品属性

品目名

品目コード（任意）

業者名

業者品番

カテゴリ（事務用品・薬品など）

管理部署タグ

単価

消耗品 or 資産（5万円以上）

使用頻度タグ（高頻度など）

期限（任意・薬品のみ）

6. 在庫処理フロー
入庫

管理者または担当が＋入力

出庫（通常）

担当者が−入力

出庫（ゲスト）

ゲストIDでログイン

氏名必須入力

仮入力として保存

管理者が承認すると本反映

7. 廃棄管理（薬品）

廃棄申請（担当）

承認（管理者）

廃棄履歴保存

将来：廃棄書自動生成

8. アラート機能

在庫閾値下回り

期限接近

高頻度タグ品目

9. AI機能（オプション）

※ AI_ENABLED=true/false で切替可能

9-1 AIができること

在庫検索

使用状況要約

発注候補提案

廃棄書・発注書の文章生成

例：
「今月の造影剤の使用状況」
「発注が必要な物品を一覧にして」

9-2 AIができないこと（重要）

❌ 在庫を増減しない
❌ 発注を確定しない
❌ DBを書き換えない

👉 出力は必ず人が確認

10. AI無効時の挙動

AIボタン・チャット非表示

通常の検索・一覧・集計画面のみ

全機能は使用可能

11. デモモード

ダミーデータ自動投入

本番DBとは切替式

プレゼン・検証用

12. 設計方針

【開発方針】
・初心者にも分かる構成
・ファイル構成も提案
・最小構成から開始
・ステップごとに拡張

【お願い】
・一気に完成コードを出さない
・段階的に作る
・各ステップで次の作業を提示

13. 技術方針

DBアクセス層とAI層は分離

AI無しでも動く構造

設定は .env で管理

14. 将来拡張

音声入力

発注メール送信

CSV出力

グラフ可視化

✅ この仕様は
・AIありでも
・AIなしでも
運用可能であること

---

## 追加仕様: 認証・ユーザー管理（将来導入）

### 15. ログイン機能の概要

**目的:**
- ログインユーザーの名前と部署を在庫処理に自動反映
- ユーザー区分（管理者・一般・ゲスト）による権限制御
- ゲストユーザーの出庫仮入力と承認フロー

**設計方針:**
- 段階的な導入（既存機能との互換性維持）
- SQLiteベースの認証（将来的に外部認証も検討）
- パスワードは必ずハッシュ化（平文保存禁止）

### 16. テーブル設計

#### 16.1 新規テーブル: users（ユーザーマスター）

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,           -- ログインID（英数字）
    password_hash TEXT NOT NULL,              -- パスワードハッシュ（bcrypt推奨）
    display_name TEXT NOT NULL,               -- 表示名（正規職員は個人名、ゲストは"ゲストさん"等）
    department TEXT NOT NULL,                 -- 所属部署（全ユーザー必須）
    user_role TEXT NOT NULL,                  -- 'ADMIN', 'USER', 'GUEST'
    is_active INTEGER DEFAULT 1,              -- 有効/無効フラグ
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_role ON users(user_role);
CREATE INDEX idx_users_department ON users(department);
```

**ユーザー区分:**
- **ADMIN（管理者）**: 全操作可能、承認処理、ユーザー管理
  - 例：username: `admin`, display_name: "管理者", department: "総務部"
- **USER（一般ユーザー）**: 出庫・入庫、即座に反映
  - 例：username: `yamada`, display_name: "山田太郎", department: "営業部"
- **GUEST（ゲストユーザー）**: 出庫仮入力のみ、承認待ち
  - **部署単位でゲストIDを作成**
  - 例：username: `guest_nursing`, display_name: "ゲストさん", department: "看護係"
  - 例：username: `guest_pharmacy`, display_name: "ゲストさん", department: "薬剤部"
  - 想定: アルバイト、実習生など現場実務者が部署内で共有使用

#### 16.2 既存テーブル修行: inventory_history

```sql
-- user_id カラムを追加（段階的移行）
ALTER TABLE inventory_history ADD COLUMN user_id INTEGER;
ALTER TABLE inventory_history ADD FOREIGN KEY (user_id) REFERENCES users(id);

-- 移行期間は user_name を残して互換性維持
-- 表示優先順位: user_id → user_name
```

**移行方針:**
1. Phase 1: user_id カラム追加、user_name は残す
2. Phase 2: 新規データは user_id を使用
3. Phase 3: 旧データ移行後、user_name 削除検討

#### 16.3 新規テーブル: approval_queue（承認待ちキュー）

```sql
CREATE TABLE approval_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    history_id INTEGER NOT NULL,              -- inventory_history の ID
    requested_by_user_id INTEGER NOT NULL,    -- 申請者（ゲストユーザー）
    requested_at TEXT DEFAULT CURRENT_TIMESTAMP,
    approved_by_user_id INTEGER,              -- 承認者（管理者）
    approved_at TEXT,
    approval_status TEXT DEFAULT 'PENDING',   -- 'PENDING', 'APPROVED', 'REJECTED'
    rejection_reason TEXT,
    FOREIGN KEY (history_id) REFERENCES inventory_history(id),
    FOREIGN KEY (requested_by_user_id) REFERENCES users(id),
    FOREIGN KEY (approved_by_user_id) REFERENCES users(id)
);

CREATE INDEX idx_approval_status ON approval_queue(approval_status);
CREATE INDEX idx_approval_requested_by ON approval_queue(requested_by_user_id);
```

### 17. 認証フロー

#### 17.1 ログイン処理

```
【ログイン画面】
  ↓ ログインID・パスワード入力
【認証処理】
  1. username でユーザー検索
  2. パスワードハッシュ照合
  3. is_active チェック
  ↓
【session_state に保存】
  user_id, username, display_name, department, role
  ↓
【メイン画面へ遷移】
```

#### 17.2 セッション管理

- Streamlit の `st.session_state` を活用
- ページリロード時も保持
- ログアウト時は `st.session_state.clear()`

#### 17.3 権限チェック

各ページで必ず権限確認を実施：
- 未ログイン → ログイン画面へリダイレクト
- 権限不足 → エラー表示

### 18. ユーザー区分別の動作

#### 18.1 管理者（ADMIN）

**可能な操作:**
- 物品マスター管理
- ユーザー管理
- 入庫・出庫（即座に反映）
- **承認処理**（ゲストの仮出庫を承認/却下）
- 廃棄申請・承認
- 全データ閲覧

**出庫時:**
```
物品選択 → 数量入力 → [出庫を実行]
  ↓
user_id: 自動取得（ログイン中の管理者）
user_name: 自動取得（display_name: "管理者"）
department: 自動取得（department: "総務部"）
status: 'CONFIRMED'（即座に在庫減）
```

**画面表示:**
```
ログイン中: 管理者（総務部）[ログアウト]

物品選択: [____▼]
出庫数量: [____]
備考:     [____]
（出庫者名・部署は自動取得のため入力欄なし）

[✅ 出庫を実行]
```

#### 18.2 一般ユーザー（USER）

**可能な操作:**
- 入庫・出庫（即座に反映）
- 在庫確認
- 自分の履歴閲覧

**出庫時:**
```
物品選択 → 数量入力 → [出庫を実行]
  ↓
user_id: 自動取得（ログイン中のユーザー）
user_name: 自動取得（display_name: "山田太郎"）
department: 自動取得（department: "営業部"）
status: 'CONFIRMED'（即座に在庫減）
```

**画面表示:**
```
ログイン中: 山田太郎（営業部）[ログアウト]

物品選択: [____▼]
出庫数量: [____]
備考:     [____]
（出庫者名・部署は自動取得のため入力欄なし）

[✅ 出庫を実行]
```

#### 18.3 ゲストユーザー（GUEST）

**メニュー制限:**
- **表示されるメニュー:** 「➖ 出庫（申請）」のみ
- **非表示のメニュー:** 📦 在庫一覧、➕ 入庫、📋 履歴、🔧 在庫調整、👥 ユーザー管理、🏢 部署管理

**可能な操作:**
- 出庫仮入力のみ（承認待ち）
- 自分の申請状況確認（出庫ページ内のPENDINGセクション）
- 申請の取り下げ（PENDING状態のみ）
- **部署限定物品のみ表示**（将来実装：自部署のタグが付いた物品のみ）

**特徴:**
- 部署単位でゲストIDを作成（例：guest_nursing, guest_pharmacy）
- ログインIDに部署情報が紐付いている
- 出庫時に**個人名のみ手入力**、部署名は自動取得

**出庫時:**
```
ゲストIDでログイン（例：guest_nursing）
  ↓
display_name: "ゲストさん"
department: "看護係" を自動取得
  ↓
物品一覧に「看護係」タグの物品のみ表示
  ↓
物品選択 → 数量入力 → 個人名入力（必須）→ [出庫を申請]
  ↓
user_id: 自動取得（例：guest_nursing）
user_name: 手入力した個人名（例："田中一郎"）
department: 自動取得（"看護係"）
status: 'PENDING'（在庫は減らない）
  ↓
approval_queue に登録
  ↓
管理者が承認画面で確認
  ↓
【承認時】status → 'CONFIRMED'、在庫減算
【却下時】status → 'REJECTED'、在庫そのまま
```

**画面表示:**
```
ログイン中: ゲストさん（看護係）[ログアウト]

【表示物品】看護係タグの物品のみ

物品選択: [____▼]  ← 部署限定物品のみ表示
出庫数量: [____]
出庫者名: [____]    ← 個人名のみ手入力必須
備考:     [____]
（部署名は自動取得のため入力欄なし）

[📝 出庫を申請]
```

**ゲストID管理例:**
```
username: guest_nursing    → department: "看護係"
username: guest_pharmacy   → department: "薬剤部"
username: guest_radiology  → department: "放射線科"
username: guest_lab        → department: "検査室"
```

### 19. 既存機能への影響

#### 19.1 出庫ページ

**変更点:**

| 項目 | 現在 | ログイン導入後（正規職員） | ログイン導入後（ゲスト） |
|------|------|--------------------------|------------------------|
| 出庫者名 | 手入力 | **自動取得**（display_name） | **手入力**（個人名のみ） |
| 部署名 | 手入力（任意） | **自動取得**（department） | **自動取得**（department） |
| 物品表示 | 全物品 | 全物品 | **部署限定物品のみ** |
| 実行ボタン | [出庫を実行] | [出庫を実行] | [出庫を申請] |
| 処理結果 | 即座に在庫減 | 即座に在庫減 | 承認待ち |

**重要な設計ポイント:**
- **ゲストユーザー = 部署単位でID作成**
  - 部署名は自動取得（手入力不要）
  - 個人名のみ手入力
  - 部署限定物品のみ表示（タグによる制御）
- **正規職員 = 完全自動**
  - 個人名・部署名とも自動取得
  - 全物品表示
- 既存の出庫画面UI構造はゲスト用として活用可能（部署名入力欄を削除）

**部署限定物品の表示制御:**
```sql
-- ゲストユーザーの場合
SELECT * FROM items 
WHERE department_tags LIKE '%' || ログイン中のdepartment || '%'
   OR department_tags = '全社'

-- 正規職員の場合  
SELECT * FROM items  -- 全物品表示
```

#### 19.2 入庫ページ（今後実装）

同様に出庫者・部署を自動取得

#### 19.3 履歴ページ（今後実装）

- 管理者: 全履歴表示
- 一般ユーザー: 自分の部署の履歴
- ゲストユーザー: 自分の申請のみ

#### 19.4 承認画面（新規・管理者専用）

- 承認待ち一覧（status='PENDING'）
- 申請者名、物品、数量、日時
- [承認] / [却下] ボタン

### 20. セキュリティ考慮事項

#### 20.1 パスワード管理

- 平文保存禁止（bcrypt または hashlib でハッシュ化）
- デフォルトパスワードは初回ログイン時に変更を促す
- 最低8文字（将来的に強化）
- **ゲストIDは共有パスワード**（現場で共有使用を想定）

#### 20.2 ゲストユーザーの運用

- 部署単位でゲストIDを作成（例：guest_nursing, guest_pharmacy）
- 各ゲストIDに部署名を紐付け
- パスワードは簡易なもの（例：nursing123, pharmacy123 等）
- 個人名は出庫時に手入力で記録
- 部署名は自動取得（手入力不要）
- 承認フローで管理者がチェック

**ゲストID作成例:**
```
ユーザー名: guest_nursing
表示名: ゲストさん
部署: 看護係
パスワード: nursing123

ユーザー名: guest_pharmacy
表示名: ゲストさん
部署: 薬剤部
パスワード: pharmacy123
```

#### 20.2 セッション管理

- Streamlit の session_state を使用
- タイムアウト（将来検討）
- CSRF対策（Streamlit標準機能）

#### 20.3 権限チェック

- 各ページで必ず権限確認
- DB層でも二重チェック

### 21. 実装ステップ（段階的導入）

**Phase 1: テーブル準備**
- users テーブル作成
- approval_queue テーブル作成
- inventory_history に user_id カラム追加
- ダミーユーザー投入

**Phase 2: 認証機能**
- ログイン画面実装
- セッション管理
- ログアウト機能

**Phase 3: 出庫機能の改修**
- 出庫者・部署の自動取得
- ゲストユーザーの仮入力対応
- 既存機能の互換性維持

**Phase 4: 承認機能**
- 承認待ち一覧画面
- 承認/却下処理

**Phase 5: 権限制御**
- ページごとのアクセス制御
- データ表示の制御（部署限定など）

### 22. 仕様整合性チェック

| 項目 | 第3章・第4章・第6章との整合性 | 備考 |
|------|----------------|------|
| ユーザー区分 | ✅ 管理者・一般・ゲスト | user_role で区別 |
| ゲストの氏名入力必須 | ✅ 個人名のみ手入力 | **部署名は自動取得** |
| ゲストの出庫仮入力 | ✅ status='PENDING' | 個人名を手入力、部署は自動 |
| 承認待ち状態で保存 | ✅ approval_queue | approval_queue で管理 |
| 管理者が承認すると本反映 | ✅ 承認機能 | approval_queue 経由 |
| 部署限定物品（第4章） | ✅ タグで表示制御 | ゲストは自部署の物品のみ |
| 正規職員の自動反映 | ✅ display_name/department | ADMIN/USER は完全自動 |
| 段階的な作る | ✅ Phase 1〜5 | 既存機能維持しつつ拡張 |
| AI機能ON/OFF | ✅ 影響なし | 認証とAIは独立 |

**設計の要点:**
- ゲストユーザー（guest_nursing等）: **部署単位ID**、個人名のみ手入力、部署は自動
- 正規職員（yamada等）: 個人ID、名前・部署とも自動反映
- 部署限定物品: ゲストは自部署タグの物品のみ表示（将来実装）
- 承認フロー: ゲストの出庫のみ、正規職員は即座に反映

**出庫フロー比較:**
```
【ゲストユーザー（guest_nursing）】
ログイン → 看護係タグの物品のみ表示（将来実装） → 物品選択 → 数量入力 
→ 個人名入力（例："田中一郎"） → [出庫を申請] → 承認待ち

【正規職員（yamada）】
ログイン → 全物品表示 → 物品選択 → 数量入力 
→ [出庫を実行] → 即座に在庫減
```

✅ **既存仕様との矛盾なし**
✅ **段階的導入により既存機能は維持**
✅ **SPECに記載された要件をすべて満たす設計**
✅ **部署限定物品の表示制御により使いやすさ向上**
✅ **個人名のみ手入力で作業効率化**

---

## 21. 将来拡張：部署ごとの物品フィルタリング

### 21.1 設計コンセプト

**目的:** 部署ごとに閲覧・出庫可能な物品を制限し、GUESTユーザーが不要な物品を見ないようにする

**現状（最小実装）:**
- `get_all_items_for_outbound()`、`get_all_items_for_inbound()` に `department_id` パラメータを追加済み
- フィルタリング処理はコメントアウト状態（TODOとして保留）
- 全物品がすべてのユーザーに表示される

### 21.2 将来実装案

**案1: department_items テーブル（N:N関連）**
```sql
CREATE TABLE department_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    department_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    FOREIGN KEY (department_id) REFERENCES departments(id),
    FOREIGN KEY (item_id) REFERENCES items(id),
    UNIQUE(department_id, item_id)
);
```

**案2: items テーブルに department_id カラム追加**
```sql
ALTER TABLE items ADD COLUMN department_id INTEGER;
-- NULLの場合は全部署共通
```

**案3: カテゴリベースのフィルタリング**
```sql
CREATE TABLE department_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    department_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    FOREIGN KEY (department_id) REFERENCES departments(id),
    UNIQUE(department_id, category)
);
```

### 21.3 実装時の修正箇所

1. **db.py / app.py の物品取得関数:**
   - `get_all_items_for_outbound()` のTODOコメントを有効化
   - `get_all_items_for_inbound()` のTODOコメントを有効化

2. **出庫ページ:**
   - `show_outbound_page()` でGUESTの場合は `department_id` を渡す

3. **管理画面:**
   - 部署ごとの物品割り当て管理UIを追加

---

## 22. 権限制御と申請取消

### 22.1 申請取り下げ権限

**GUEST（ゲストユーザー）:**
- 取り下げ可能条件: `guest_user_id 一致` AND `actor_name 一致`
- UI: 取り下げボタン押下後、申請時の名前を再入力させて照合
- DB: `cancel_pending_transaction()` で二重チェック

**USER/ADMIN:**
- GUESTの申請に対して取り下げボタンは**表示しない**
- 承認管理ページで「✅ 承認」または「❌ 却下」のみ可能
- 申請の削除（物理削除）は行わない

### 22.2 承認管理での操作

| 操作 | 説明 | 使用場面 |
|------|------|----------|
| ✅ 承認 | 申請を承認し在庫に反映 | 正当な申請 |
| ❌ 却下 | 申請を却下（理由必須） | 不正な申請、数量ミス等 |

**注意:** 在庫の直接修正が必要な場合は「🔧 在庫調整」機能を使用

---

## 23. 数量上限と異常値警告（将来の自動発注用フック）

### 23.1 設定値

```python
QUANTITY_LIMITS = {
    "outbound_max": 1000,      # 1回の出庫数量上限
    "inbound_max": 10000,      # 1回の入庫数量上限
    "warning_threshold": 100,  # 警告を出す閾値
}
```

### 23.2 バリデーション関数

`validate_quantity_for_order()` - 数量の妥当性チェック

**チェック項目:**
- 出庫/入庫の上限超過 → エラー（処理拒否）
- 閾値超え → 警告（処理は続行可能）

### 23.3 将来の自動発注連携（TODO）

```python
# validate_quantity_for_order() 内のTODO
# - 在庫が閾値以下になったら発注フラグを立てる
# - 発注推奨数量を計算
# - 外部システム連携（API呼び出し等）
```