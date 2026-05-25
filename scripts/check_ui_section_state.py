"""
UIセクション状態保持チェック

目的:
- `st.tabs(...)` を使ったページで `st.rerun()` が走ると、
  セクションが先頭に戻る不具合が再発しやすいため、
  ui/pages 配下で tabs 利用が再導入されていないかを検査する。

使い方:
    python scripts/check_ui_section_state.py

終了コード:
- 0: 問題なし
- 1: tabs 利用あり（要修正）
"""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
UI_PAGES_DIR = ROOT / "ui" / "pages"


def find_tab_usages() -> list[tuple[Path, int, str]]:
    results: list[tuple[Path, int, str]] = []
    for path in UI_PAGES_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "st.tabs(" in line:
                rel = path.relative_to(ROOT)
                results.append((rel, line_no, line.strip()))
    return results


def main() -> int:
    usages = find_tab_usages()
    if not usages:
        print("✅ OK: ui/pages 配下に st.tabs の利用はありません")
        return 0

    print("❌ NG: st.tabs の利用が検出されました（rerun時の戻り不具合リスク）")
    for rel, line_no, code in usages:
        print(f"- {rel}:{line_no}  {code}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
