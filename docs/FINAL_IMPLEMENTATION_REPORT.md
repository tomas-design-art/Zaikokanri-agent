# 在庫管理システム リアーキテクト 最終実装レポート

**目的**: Streamlit 製モノリス（`app.py` 等）から FastAPI + Next.js への完全リプレース。  
**期間**: Phase 0 〜 Phase 10（本ドキュメントで完了報告）  
**ステータス**: ✅ 全 Phase 完了 / pytest 21 件全パス / ruff クリーン / TypeScript エラー無し

---

## 1. 採用スタック（最終形）

| レイヤ | 技術 | 補足 |
|---|---|---|
| バックエンド | FastAPI 0.110+ / Python 3.11 | 非同期対応、Pydantic v2 |
| ORM | SQLAlchemy 2.0 (Mapped style) | `with_for_update()` で在庫ロック |
| マイグレーション | Alembic | Dockerfile で `alembic upgrade head` を自動実行 |
| DB | PostgreSQL 15 (本番) / SQLite (開発・テスト) | `migrate_sqlite_to_postgres.py` で移行可能 |
| 認証 | JWT (httpOnly Cookie `zk_access` / `zk_refresh`) + bcrypt | 旧 SHA-256 ハッシュは初回ログインで自動再ハッシュ |
| 帳票 | fpdf2 (NotoSansJP) + openpyxl | pandas 非依存 |
| フロント | Next.js 14 (App Router) + TanStack Query + Zustand + Tailwind | RSC 未使用、すべて client component |
| バリデーション | Zod (フロント) / Pydantic (バック) | スキーマ二重防御 |
| 通知 UI | Sonner | トースト統一 |
| レート制限 | slowapi (`/auth/login` に既定 5/分) | 環境変数 `RATE_LIMIT_LOGIN` で上書き可 |
| AI | OpenAI Responses API (任意・既定 OFF) | `AI_ENABLED=false` で完全無効化 |
| CI | GitHub Actions (ruff / pytest / tsc / next build / gitleaks) | `.github/workflows/ci.yml` |
| デプロイ | Render (バックエンド + Postgres) / Vercel (フロント) | `render.yaml`, `frontend/vercel.json` |

---

## 2. ディレクトリ構成（新規部分のみ）

```
backend/
├── app/
│   ├── main.py                # FastAPI エントリ・67 ルート登録
│   ├── settings.py            # pydantic-settings, env 読込
│   ├── db.py                  # engine / SessionLocal / get_db
│   ├── auth/
│   │   ├── hashing.py         # bcrypt + 旧SHA-256 移行
│   │   ├── jwt.py             # access/refresh トークン
│   │   └── deps.py            # CurrentUser / require_admin / require_user
│   ├── models/                # SQLAlchemy 2.0 Mapped 定義
│   ├── schemas/               # Pydantic v2 IO スキーマ
│   ├── routers/               # 21 ルーター（下記）
│   ├── services/
│   │   ├── stock_service.py   # 在庫増減（行ロック）
│   │   ├── order_service.py   # 発注書ペイロード/PDF/Excel/メール
│   │   └── stocktake_export.py# 棚卸 Excel
│   └── alembic/               # マイグレーション
├── tests/                     # pytest 21 テスト
├── fonts/NotoSansJP-Regular.ttf
├── Dockerfile                 # alembic upgrade head + 0.0.0.0 バインド
├── pyproject.toml             # ruff/pytest 設定込み
└── scripts/migrate_sqlite_to_postgres.py

frontend/
├── src/app/
│   ├── login/                 # 公開ログイン
│   └── (app)/                 # 認証必須セグメント
│       ├── dashboard/         # KPI + アラート
│       ├── inventory/         # 在庫一覧
│       ├── items/             # 物品マスタ CRUD
│       ├── inbound/, outbound/# 入庫・出庫
│       ├── purchase-requests/ # 発注申請 + 発注書発行 (Phase 6)
│       ├── approvals/         # 承認待ち一覧
│       ├── disposal/          # 廃棄申請
│       ├── stocktake/         # 棚卸 + Excel 出力 (Phase 6)
│       ├── history/           # 履歴
│       ├── alerts/            # 在庫アラート
│       ├── stats/             # 統計
│       ├── ai/                # AI アシスタント
│       ├── maintenance/       # メンテ
│       ├── masters/           # マスタ管理
│       └── users/             # ユーザー管理（ADMIN）
├── src/lib/api.ts             # apiFetch / apiBlob / downloadBlob
└── vercel.json
```

### バックエンド API ルーター（21）

`adjust / ai / alerts / approvals / auth / categories / demo / departments / disposal_requests / history / inbound / inventory / items / maintenance / orders / outbound / purchase_requests / stats / stocktake / users / vendors`

合計 **67 エンドポイント** が `app.main` に登録されている（OpenAPI で確認可）。

---

## 3. Phase 別 成果サマリ

| Phase | 内容 | 主成果物 |
|---|---|---|
| 0 | 要件整理 / 既存 Streamlit 仕様棚卸 | `docs/CURRENT_SPEC.md` |
| 1 | バックエンド土台 | `app/main.py`, `db.py`, `settings.py`, JWT, 認証 |
| 2 | モデル + Alembic | 15 テーブル、初回マイグレーション |
| 3 | コア API | items/inventory/inbound/outbound/history/categories/vendors/departments |
| 4 | フロント土台 + ログイン + ダッシュボード | 16 ページ骨格 |
| 5 | UI 仕上げ（debounce 検索、編集モーダル等） | 各ページのフォーム強化 |
| 6 | **帳票** | PDF/Excel/メール本文（発注書）+ 棚卸 Excel |
| 7 | **SQLite → Postgres 移行スクリプト** | `migrate_sqlite_to_postgres.py`（dry-run / truncate 対応） |
| 8 | **pytest 自動テスト** | conftest + 21 ケース（auth / inventory / orders / RBAC） |
| 9 | **CI/CD** | GitHub Actions（ruff / pytest / tsc / next build / gitleaks） |
| 10 | **デプロイ設定 + 最終レポート** | `render.yaml` / `vercel.json` / Dockerfile fonts COPY |

---

## 4. 品質指標（最終）

```text
# バックエンド
$ ruff check app tests
All checks passed!

$ pytest -W ignore::DeprecationWarning
tests\test_auth.py ......                                                [ 28%]
tests\test_inventory.py ......                                           [ 57%]
tests\test_orders.py .....                                               [ 80%]
tests\test_rbac.py ....                                                  [100%]
============================= 21 passed in 15.56s =============================

# フロントエンド
$ npm run typecheck   # tsc --noEmit
（エラー無し）
```

### Phase 8 で発見・修正した実装バグ

1. **`StockResult` が `@dataclass(slots=True)` で `__dict__` を持たない**  
   → `routers/inbound.py`, `routers/outbound.py` の `StockResultOut(**result.__dict__)` が `AttributeError` で 500 に。  
   修正: `stock_service.py` から `slots=True` を除去。

2. **PDF/Excel ダウンロードで日本語ベンダー名を `Content-Disposition: filename=...` に直書き**  
   → Starlette が `latin-1` で header をエンコードして `UnicodeEncodeError`。  
   修正: `routers/orders.py` で RFC 5987 形式 `filename=order.pdf; filename*=UTF-8''<percent-encoded>` に。

これらは本番運用前にテストが捕捉した。CI で再発防止される。

---

## 5. RBAC 仕様（実装どおり）

| 機能 | ADMIN | USER | GUEST |
|---|---|---|---|
| 在庫閲覧 | ✅ | ✅ | ✅ |
| 入庫 | ✅ | ✅ | ❌ |
| 出庫（即時反映） | ✅ | ✅ | ❌ |
| 出庫（承認待ち pending） | – | – | ✅ |
| 物品マスタ編集 | ✅ | ❌ | ❌ |
| 発注申請 作成 | ✅ | ✅ | ❌ |
| 発注 承認 / 発注書発行 | ✅ | ❌ | ❌ |
| ユーザー管理 | ✅ | ❌ | ❌ |
| 棚卸 セッション作成・確定 | ✅ | ❌ | ❌ |

---

## 6. 主要セキュリティ対策

- **httpOnly + SameSite Cookie + CSRF回避設計**: JS から JWT を読めない。本番では `COOKIE_SECURE=true`, `SAMESITE=none` 推奨。
- **bcrypt + 旧ハッシュ移行**: 旧 Streamlit DB のユーザもログイン時に bcrypt 再ハッシュ。
- **slowapi レート制限**: `/auth/login` に既定 5/分。テストでは `RATE_LIMIT_LOGIN=10000/minute` でバイパス。
- **RBAC 集中管理**: `require_admin` / `require_user` で各ルーターに明示的に依存注入。
- **SQL Injection**: ORM 経由のみ。AI ルーターの SQL 実行は `_FORBIDDEN_RE` で DDL/DML 拒否＋ `;` 分割禁止＋ `SELECT` のみ許可。
- **行ロック**: 出庫処理で `Inventory` 行を `with_for_update()` → 在庫不整合を排除（Postgres 本番で有効）。
- **CORS**: `CORS_ORIGINS` を環境変数で明示列挙、ワイルドカード禁止。
- **gitleaks**: CI で毎 PR スキャン。
- **個人情報**: ログにユーザー名以外の機微情報を残さない設計（`/health` は無情報、`/auth/login` は 401 のみ）。

---

## 7. デプロイ手順（要約）

### バックエンド（Render）

1. GitHub リポジトリを Render に接続  
2. `New > Blueprint` で本リポジトリの [render.yaml](render.yaml) を読み込ませる  
3. 環境変数に以下を設定（Render Dashboard）  
   - `JWT_SECRET`: `generateValue: true` で自動生成済み  
   - `CORS_ORIGINS`: Vercel デプロイ後の URL を CSV で  
   - `OPENAI_API_KEY`: AI を使うなら設定し `AI_ENABLED=true`  
4. Deploy → Dockerfile が `alembic upgrade head` を実行してから Uvicorn を `0.0.0.0:$PORT` で起動

### フロントエンド（Vercel）

1. Vercel に `frontend/` ディレクトリを指定してインポート  
2. 環境変数 `NEXT_PUBLIC_API_BASE` を Render バックエンドの URL に設定（`/api` で proxy しない場合）  
3. または [frontend/vercel.json](frontend/vercel.json) の `rewrites` で `/api/*` をバックエンドへ転送  
4. `npm run build` 成功で公開

### 既存 SQLite から Postgres へデータ移行

```bash
cd backend
export SOURCE_SQLITE=sqlite:///./inventory.db
export TARGET_DATABASE_URL=postgresql+psycopg://...
python scripts/migrate_sqlite_to_postgres.py --dry-run    # 確認
python scripts/migrate_sqlite_to_postgres.py --truncate   # 本番投入
```

---

## 8. 既知の TODO / 将来拡張

- fpdf2 の `ln=` パラメータは deprecation 警告のみ（描画は正常）。将来 `new_x/new_y` API に書き換え推奨。
- AI ルーターは現状 OFF。`AI_ENABLED=true` + `OPENAI_API_KEY` で `/ai/*` 有効化。
- メール送信はテキスト/HTML 本文を返すのみ（SMTP 送信は未実装）。クライアントがメーラーを開く想定。
- 監査ログ（admin の操作履歴）は `inventory_history` で在庫増減のみ。マスタ変更ログは未実装。

---

## 9. 旧 Streamlit からの機能網羅性チェック

| 旧 `app.py` 機能 | 新システム | 場所 |
|---|---|---|
| ログイン / ロール | ✅ | `/login`, `auth/deps.py` |
| 在庫一覧 / 検索 | ✅ | `/inventory` |
| 物品マスタ CRUD | ✅ | `/items` |
| 入庫 / 出庫 | ✅ | `/inbound`, `/outbound` |
| 出庫承認待ち（GUEST） | ✅ | `/approvals` |
| 廃棄申請 | ✅ | `/disposal` |
| 発注申請・承認 | ✅ | `/purchase-requests`, `/approvals` |
| 発注書 PDF / Excel / メール | ✅ | `/purchase-requests`（「発注書を発行」モーダル） |
| 棚卸 セッション・差異記録・Excel 出力 | ✅ | `/stocktake` |
| 在庫履歴 | ✅ | `/history` |
| アラート（閾値割れ） | ✅ | `/alerts` + ダッシュボード |
| 統計（部署別・カテゴリ別） | ✅ | `/stats` |
| ユーザー管理 | ✅ | `/users` |
| 部署 / カテゴリ / 取引先マスタ | ✅ | `/masters` |
| AI 在庫アシスタント | ✅（任意） | `/ai` |
| メンテナンス（DB ダンプ等） | ✅ | `/maintenance` |
| デモモード | ✅ | `DEMO_MODE=true` + `demo` ルーター |

→ **旧機能は全て移植済み**。

---

## 10. 結論

- 旧 Streamlit モノリスを **FastAPI + Next.js** へ完全リプレース。  
- **67 API エンドポイント / 16 画面** を実装。  
- **CI 全グリーン**（ruff / pytest 21 件 / tsc / next build）。  
- **Phase 8 のテストが本番障害となり得たバグ 2 件**（slots dataclass、ヘッダ Latin-1）を早期検出・修正。  
- Render + Vercel への **Blueprint 一発デプロイ**が可能な状態。Dockerfile は alembic 自動実行 + 0.0.0.0 バインド済みで本番安全。

実装は完了し、本番リリース可能なステージにあります。
