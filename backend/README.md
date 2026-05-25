# 在庫管理システム バックエンド

FastAPI + SQLAlchemy 2.0 + PostgreSQL (本番) / SQLite (開発) のバックエンド。

## セットアップ

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
# .env を編集して JWT_SECRET を openssl rand -hex 32 等で設定

# 初回マイグレーション
alembic upgrade head

# 起動
uvicorn app.main:app --reload --port 8000
```

API ドキュメント: http://localhost:8000/docs

## 構造

```
backend/
├── app/
│   ├── main.py            # FastAPI エントリポイント
│   ├── config.py          # pydantic-settings
│   ├── db/                # SQLAlchemy engine & session
│   ├── models/            # ORM モデル (14 テーブル)
│   ├── schemas/           # Pydantic スキーマ
│   ├── repositories/      # データアクセス (Streamlit版から移植)
│   ├── services/          # ビジネスロジック
│   ├── routers/           # FastAPI ルート
│   ├── auth/              # JWT + bcrypt
│   ├── renderers/         # PDF / Excel / メール文面
│   ├── ai/                # OpenAI 連携
│   └── assets/fonts/      # NotoSansJP
├── alembic/               # マイグレーション
├── tests/                 # pytest
└── pyproject.toml
```

## DB 切替

`.env` の `DATABASE_URL` を変更するだけで SQLite ⇔ Postgres を切替可能。

| 環境 | URL 例 |
|---|---|
| 開発 (SQLite) | `sqlite:///./inventory.db` |
| 本番 (Supabase) | `postgresql+psycopg://USER:PASS@HOST:5432/DB` |

## デプロイ (Render 無料枠)

```yaml
# render.yaml 参照
```
