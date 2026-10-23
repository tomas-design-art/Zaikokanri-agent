# 在庫管理システム バックエンド

FastAPI + SQLAlchemy 2.1 + PostgreSQL（本番）/ SQLite（開発・テスト）。セットアップと依存のルールはリポジトリ直下の README を参照。

## 構造

```
backend/
├── app/
│   ├── main.py            # エントリポイント（エラーの日本語化・/healthz・/readyz）
│   ├── config.py          # pydantic-settings（環境変数 / .env）
│   ├── errors.py          # 入力エラー・重複・予期せぬエラーを日本語の一文にする
│   ├── auth/              # JWT（PyJWT）・bcrypt・ロール判定・パスワード変更必須
│   ├── db/                # engine / session
│   ├── models/            # ORM モデル
│   ├── schemas/           # Pydantic スキーマ（空文字→None、日付の形式チェック）
│   ├── services/          # 業務ロジック
│   │   ├── stock_service.py      # 在庫を動かす処理はすべてここ（履歴と同じトランザクション）
│   │   ├── stocktake_service.py  # 棚卸し（数えた時点の帳簿数・確定で差異を在庫へ）
│   │   ├── workflow.py           # 申請の二重処理を防ぐ条件付き UPDATE
│   │   ├── ai_query.py           # AI が作った SQL の安全な実行（判定はコードのルール）
│   │   └── order_service.py ほか # 発注書（PDF / Excel / メール本文）
│   ├── routers/           # API（画面ごと）
│   └── utils/             # JST の日付・文字列
├── alembic/               # マイグレーション（0001 初期 / 0002 初期データ / 0003 改修）
├── scripts/               # seed_demo.py（デモデータ）・e2e_server.py（E2E 用の起動）・旧版からの移行
├── tests/                 # pytest（受け入れ条件の番号つき）
├── requirements.lock      # 本番の依存（ハッシュ付き・公開7日以上）
└── requirements-dev.lock  # 開発・テストの依存
```

## DB 切替

`.env` の `DATABASE_URL` を変えるだけで SQLite ⇔ PostgreSQL を切り替えられる。
`postgresql://` / `postgres://` は自動で psycopg3 用の書き方に直す。

| 環境 | URL 例 |
|---|---|
| 開発 (SQLite) | `sqlite:///./zaiko_app.db` |
| 本番 (PostgreSQL) | `postgresql://USER:PASS@HOST:5432/DB?sslmode=require` |
