# ERRORS.md — エラー台帳（このプロジェクト）

開発中に出たエラーをその場で追記する。**同じエラーの2回目を踏んだら昇格**（L2＝CLAUDE.md に手順で書く／L3＝テスト・lint・hooks に降ろす）。
L3 に降ろせたものはここから消す。

| 日付 | 何が起きたか | 原因 | 対処 | 段階 |
|---|---|---|---|---|
| 2026-10-23 | **空の PostgreSQL に `alembic upgrade head` すると 0002 で失敗**（＝本番の Docker が起動しない） | 0002 が `exec_driver_sql` に `:n` 形式の値を渡していた。psycopg3 は `%(n)s` 形式なので構文エラー。テストは SQLite だけで見えなかった | `sa.text()` で書き直し。CI に PostgreSQL 15 で upgrade/downgrade/upgrade と全テストを流すジョブを追加 | L3 |
| 2026-10-23 | **PostgreSQL で出庫・入庫が必ず 500**（`FOR UPDATE cannot be applied to the nullable side of an outer join`） | 在庫モデルが物品を `lazy="joined"`（外部結合）で読み込み、そこに `with_for_update()` を付けていた。元のコードから同じ | `with_for_update(of=Inventory)` でロック対象を在庫の表だけにした。上の PostgreSQL ジョブで捕まる | L3 |
| 2026-10-23 | **CI の pytest が `ModuleNotFoundError: No module named 'app'`** で全滅（手元は緑） | 手元の仮想環境にはバックエンドを `pip install -e .` で入れていて、`python -m pytest` で流していた。CI はロックの依存だけを入れて `pytest` を直接呼ぶ＝**手元と CI の環境が違い、手元で再現できていなかった** | `pyproject.toml` の pytest 設定に `pythonpath = ["."]`。手元も README どおり `uv pip sync` の状態（パッケージは入れない）にそろえ、`pytest` を直接呼んで確かめる | L3 |
| 2026-10-23 | `scripts/seed_demo.py` を出力リダイレクト付きで動かすと `UnicodeEncodeError: 'cp932'` で落ちる | 日本語 Windows の標準出力が cp932 で、print の絵文字を表せない | スクリプト側で `sys.stdout.reconfigure(encoding="utf-8")`、E2E 起動時は `PYTHONIOENCODING=utf-8` | L1 |
| 2026-10-23 | E2E で `getByRole("alert")` が2つに当たって失敗 | Next.js が画面に置く読み上げ用の要素（route announcer）も `role="alert"` | `getByRole("alert").filter({ hasText })` で中身まで指定する | L1 |
| 2026-10-23 | `next dev` を動かすと `next-env.d.ts` が `.next/dev/types` を参照する形に書き換わる（CI の型チェックで見つからなくなる） | Next 16 は `next-env.d.ts` を毎回生成する | `next-env.d.ts` は Git に入れない。型チェックは `next typegen && tsc --noEmit`（package.json の typecheck） | L3 |
| 2026-10-23 | 棚卸しのテスト（D-02）が失敗 | **テスト側の計算ミス**（45＋10＝55 を 54 と書いた）。コードは正しかった | 期待値は「業務上の正解（実数＋数えた後の入出庫）」から導く。テストを直すときは、コードの出力に合わせたのではないことを説明できるようにする | L1 |
