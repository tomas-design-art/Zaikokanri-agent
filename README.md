# 在庫管理システム

物品・在庫を一元管理する Web アプリケーション（AI 機能 ON/OFF 対応）。

> **構成変更について**: 旧 Streamlit モノリスは廃止しました。現在は **FastAPI バックエンド + Next.js フロントエンド** の 2 層構成です。

## 技術スタック

| レイヤ | 技術 |
|---|---|
| バックエンド | Python 3.11 / FastAPI / SQLAlchemy 2.0 / Alembic |
| データベース | PostgreSQL（本番） / SQLite（開発） |
| フロントエンド | TypeScript / Next.js / Tailwind CSS |
| 認証 | JWT + bcrypt（Cookie ベース） |
| AI | OpenAI（任意・ON/OFF 切替可能） |

## ディレクトリ構成

```
zaikokanri_agent/
├── backend/        # FastAPI アプリ（API・DB・認証・AI・帳票生成）
│   ├── app/        # ルーター / サービス / リポジトリ / モデル / スキーマ
│   ├── alembic/    # DB マイグレーション
│   └── tests/      # pytest
├── frontend/       # Next.js アプリ（画面・コンポーネント）
│   └── src/
├── docs/           # 仕様・各種ドキュメント
├── render.yaml     # Render デプロイ Blueprint（backend）
└── .github/        # CI（backend lint/test, frontend build, secret scan）
```

## セットアップ

### バックエンド

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env   # JWT_SECRET 等を設定
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

API ドキュメント: http://localhost:8000/docs

詳細は [backend/README.md](backend/README.md) を参照。

### フロントエンド

```powershell
cd frontend
npm install
# .env.local に NEXT_PUBLIC_API_BASE=http://localhost:8000 を設定
npm run dev
```

画面: http://localhost:3000

## テスト

```powershell
# バックエンド
cd backend; pytest

# フロントエンド
cd frontend; npm run typecheck; npm run build
```

## デプロイ

- **バックエンド**: Render（[render.yaml](render.yaml) の Blueprint、Docker ビルド）
- **フロントエンド**: Vercel（[frontend/vercel.json](frontend/vercel.json)）

環境変数（`JWT_SECRET` / `DATABASE_URL` / `OPENAI_API_KEY` / `CORS_ORIGINS` 等）は各ホスティング側で設定します。

## 仕様

機能仕様は [SPEC.md](SPEC.md) および [docs/](docs/) を参照してください。
