"""E2E テスト用のバックエンドを起動する（Playwright の webServer から呼ばれる）。

毎回「空の SQLite → マイグレーション → デモデータ → 起動」の順で作り直す。
前回のテスト結果は残さない（毎回ゼロから実行する）。

    python scripts/e2e_server.py            # 127.0.0.1:8100 で起動
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DB_FILE = BACKEND / "e2e.db"
PORT = int(os.environ.get("E2E_API_PORT", "8100"))
FRONT_ORIGIN = os.environ.get("E2E_FRONT_ORIGIN", "http://127.0.0.1:3100")


def main() -> None:
    for suffix in ("", "-journal", "-wal", "-shm"):
        Path(f"{DB_FILE}{suffix}").unlink(missing_ok=True)
    os.environ.update(
        {
            "DATABASE_URL": f"sqlite:///{DB_FILE.as_posix()}",
            "APP_ENV": "test",
            "JWT_SECRET": "e2e-only-secret-not-for-production-0123456789",
            "RATE_LIMIT_LOGIN": "10000/minute",
            "CORS_ORIGINS": FRONT_ORIGIN,
            "AI_ENABLED": "false",
            "DEMO_MODE": "false",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True)
    subprocess.run([sys.executable, "scripts/seed_demo.py"], cwd=BACKEND, check=True)

    sys.path.insert(0, str(BACKEND))
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
