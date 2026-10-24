FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 依存はハッシュ付きロックから入れる（公開7日未満の版を拾わない・すり替えを検出する）。
# ロックの作り直しは pyproject.toml の先頭コメント参照。psycopg / bcrypt 等はビルド済みの wheel を使う。
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY fonts ./fonts

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# 起動: Alembic マイグレーション + Uvicorn（Render 等 PaaS では 0.0.0.0 にバインド）
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
