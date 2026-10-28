# 在庫管理システム

物品・在庫を一元管理する Web アプリケーション。入出庫・申請と承認・発注・**棚卸し（差異を在庫に反映）**・統計まで、
1つの事業所で最初から最後まで使えることを目標にしている。

## 技術スタック

| レイヤ | 技術 |
|---|---|
| バックエンド | Python 3.11 / FastAPI / SQLAlchemy 2.1 / Alembic / PyJWT |
| データベース | PostgreSQL（本番） / SQLite（開発・テスト） |
| フロントエンド | TypeScript / Next.js 16（App Router）/ React 19 / Tailwind CSS 4 / TanStack Query |
| テスト | pytest（API・マイグレーション・依存のルール）／ Playwright（画面の E2E） |
| 認証 | JWT（httpOnly Cookie）+ bcrypt。30分でアクセス用が切れても画面が自動で更新する |
| AI | OpenAI（任意・既定は無効） |

## 依存のルール（公開7日未満の版は使わない）

- **npm**：`~/.npmrc` の `min-release-age=7` で機械的に守られる。`package.json` は版を固定。
- **Python**：`uv` の `exclude-newer = "7 days"` で作った**ハッシュ付きロック**から入れる。
  ロックの作り直し（`backend/` で）：

  ```powershell
  uv pip compile pyproject.toml --universal --generate-hashes --exclude-newer "7 days" -o requirements.lock
  uv pip compile pyproject.toml --universal --generate-hashes --exclude-newer "7 days" --extra dev -o requirements-dev.lock
  ```

  `tests/test_supply_chain.py` がこのルールを確かめる（ロックが7日ルールなしで作られていたら失敗する）。

## セットアップ

### バックエンド

```powershell
cd backend
python -m venv .venv
uv pip sync requirements-dev.lock --python .venv\Scripts\python.exe
copy .env.example .env   # JWT_SECRET 等を設定
.venv\Scripts\alembic upgrade head
.venv\Scripts\python scripts\seed_demo.py   # デモデータ（任意）
.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

API ドキュメント: http://localhost:8000/docs

初期管理者は `admin / admin123`。**初回ログイン時にパスワードの変更が必須**。
デモデータを入れた場合の利用者：管理者 `admin/admin123`、一般 `U001〜U007/pass1234`、ゲスト `G001〜G003/pass1234`。

### 役割と部署（受け入れ条件 I 章）

| 役割 | 想定 | 見える範囲（開いたとき） | できること（主なもの） |
|---|---|---|---|
| ゲスト | アルバイト | 自分の部署の物品＋全社共通の物品だけ（切り替えなし）。単価・業者は出ない | 出庫の申請（同じ部署の正社員か管理者が承認）・「これ廃棄が要りそう」の部署への連絡 |
| 一般 | 正社員 | 自分の部署＋共通（「全部署」に切り替えられる） | 入出庫・発注申請・廃棄申請・棚卸しの入力・**同じ部署のゲストの出庫承認**・部署への連絡を廃棄申請に上げる |
| 管理者 | 在庫管理者（総務など） | 全部署（「自分の部署＋共通」に切り替えられる） | 全部の承認・同じ物品の申請のまとめ・発注書・マスタ・ユーザー |

物品には「所属部署」と「全社共通」がある（どちらか一方は必ず）。所属部署の無い既存の物品は、マイグレーション 0004 で全社共通になる。

### フロントエンド

```powershell
cd frontend
npm ci
copy .env.local.example .env.local   # NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
npm run dev
```

画面: http://localhost:3000

## テスト

```powershell
# バックエンド（API・マイグレーション・依存のルール）
cd backend; .venv\Scripts\python -m pytest -q; .venv\Scripts\ruff check app tests alembic

# フロントエンド
cd frontend; npm run typecheck; npm run lint; npm run build

# 画面の E2E（初回だけ npm run e2e:install）
cd frontend; npm run e2e
```

E2E は毎回ゼロから実行する：API（8100）を**空の SQLite → マイグレーション → デモデータ**の順で作り直し、
画面（3100）を立ち上げてから、ロールごとにブラウザを操作する。開発中のサーバー（3000 / 8000）とはぶつからない。

受け入れ条件（何を正解とするか）は [docs/REVIEW_2026-10-23.md](docs/REVIEW_2026-10-23.md)、
テスト設計表（反映・権限・境界値）は [docs/TEST_DESIGN.md](docs/TEST_DESIGN.md)。テスト名に番号（例 `D-02`・`P-05`・`R45`・`X-06`）が入っている。

| テスト | 何を確かめるか |
|---|---|
| `test_propagation.py` | 操作の前後で全部の見える場所（在庫・KPI・アラート・履歴・統計・処理待ち・CSV）を取り、**変わった所が表のとおりで、ほかは変わらない** |
| `test_permissions.py` | **全 API** をログインなし／ゲスト／本人／他人／管理者で呼び、表のとおり「できる・403・401」になる。API を足して表に書かないと落ちる |
| `test_departments.py` | 部署の観点：人（部署）× 切り替えで見える物品・履歴・申請、同じ部署だけの承認と連絡、ゲストに単価・業者を出さない、申請のまとめと発注書 |
| `test_boundaries.py` | 在庫ちょうど・上限ちょうど・上限+1・小数・文字・巨大な数・変な日付・スクリプト文字列など |
| `test_concurrency.py` | 2人の操作を確実に重ねて（途中でわざと待たせて）、在庫の取り合い・二重承認・二重取消が起きない |
| `scripts/mutation_check.py` | **テストが本当に効いているか**：決めごとをコードの1か所ずつわざと壊し（約140か所）、テストが赤になるかを見る。大きな変更の後に手で回す（1時間ほど） |

## ディレクトリ構成

```
zaikokanri_agent/
├── backend/        # FastAPI（routers / services / models / schemas）・alembic・tests・scripts
├── frontend/       # Next.js（src/app / components / lib）・e2e（Playwright）
├── docs/           # 受け入れ条件・旧仕様
├── ERRORS.md       # エラー台帳（同じミスを二度しない）
├── render.yaml     # Render デプロイ Blueprint（backend）
└── .github/        # CI（lint・型・pytest・build・E2E。監査ツールの指摘だけは止めない）
```

## 社内の1台の PC で使う（オンプレ・SQLite）

PostgreSQL が要るのは、Web アプリとしてクラウド（Render など）に置くときだけ。社内の1台の PC で動かすなら
**SQLite のまま使える**（`DATABASE_URL` を設定しなければ `backend/zaiko_app.db` を使う。テストも SQLite と PostgreSQL の両方で同じ結果）。

- その PC でバックエンド（8000）とフロントエンド（3000）を動かし、ほかの人は同じ社内ネットワークのブラウザから `http://<PCの名前>:3000` を開く。
- 向いている規模：1事業所・同時に操作する人が十数人程度まで。SQLite は書き込みを1件ずつ順番に処理するので、二重の承認などは条件付き更新で防いでいる。
- **バックアップ**：`zaiko_app.db` が全データ。毎日、別の場所へコピーする（アプリを止めてからコピーするか、`sqlite3 zaiko_app.db ".backup 'backup.db'"`）。
- 社内 LAN の http で `APP_ENV=production` にする場合は、`COOKIE_SECURE=false` のままにする（https でないと Cookie が送られない）。起動時に警告が出るが、閉じた社内ネットワークなら想定どおり。外から入れるなら https にする。
- あとで PostgreSQL へ移すときは `DATABASE_URL` を変えて `alembic upgrade head`。既存データの移し替えは `scripts/migrate_sqlite_to_postgres.py`（旧版向けに作られたもの。今の構成で使えるかは移す前に確認すること）。

## セキュリティ

確認項目と対応は [docs/REVIEW_2026-10-23.md](docs/REVIEW_2026-10-23.md) の「G. セキュリティ」。主なもの：

- ログインは httpOnly Cookie。同じアカウントで10回続けて失敗すると15分ロック（管理者が解除できる）。パスワードを変える・リセットすると、ほかの端末のログインは無効になる。
- 初期管理者・管理者が作ったユーザーは、初回ログインでパスワード変更が必須。パスワードは8文字以上・72バイト以内。
- CSV / Excel の出力は、`=` などで始まる値を数式として実行させない（CSV インジェクション対策）。
- 画面・API ともにセキュリティヘッダー（CSP・クリックジャッキング対策など）。他サイトからの書き込みは拒否。
- ログイン失敗・ロック・パスワード変更・権限変更は `security` ロガーに記録（パスワードは残さない）。
- 依存は公開7日以上の版をハッシュ付きで固定。CI で pip-audit / npm audit を実行（指摘は止めずにログで確認）。

## デプロイ

- **バックエンド**: Render（[render.yaml](render.yaml)、Docker。依存はハッシュ付きロックから入れる。起動時に `alembic upgrade head`）
- **フロントエンド**: Vercel（[frontend/vercel.json](frontend/vercel.json)。`/api/*` を Render へ転送するので Cookie は同じオリジン）

環境変数（`JWT_SECRET` / `DATABASE_URL` / `OPENAI_API_KEY` / `CORS_ORIGINS` 等）は各ホスティング側で設定する。
本番では `APP_ENV=production`（API ドキュメントを閉じ、JWT_SECRET の強さを確認する）。
