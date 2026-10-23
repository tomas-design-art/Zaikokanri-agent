"""セキュリティに関わる出来事の記録（G-11）。

ログイン失敗・ロック・パスワード変更・権限変更などを `security` ロガーに1行で残す。
パスワードやトークンそのものは決して渡さないこと。
"""
from __future__ import annotations

import logging

log = logging.getLogger("security")


def security_event(event: str, **fields: object) -> None:
    detail = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    log.info("%s %s", event, detail)
